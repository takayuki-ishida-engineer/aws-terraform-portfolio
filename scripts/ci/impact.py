#!/usr/bin/env python3
"""Fail-closed impact analysis for PR Safety CI (Owner decision 2026-11-23).

A pull request's changed files select the Full CI steps that verify them. Each
changed file is mapped by:

1. its Terraform configuration (``configurations`` in impact_map.json) and, for
   Terraform-relevant files, every configuration that sources it through a module
   ``source`` or a test ``module { source }`` block, transitively;
2. step inputs: the paths a Full CI or offline-contracts step names in its
   commands, the Python files it runs or imports and, transitively, their imports
   and path literals (over-approximated: imports by module name, literals by path
   suffix or by name next to the file);
3. the explicit ``rules`` in the map;
4. a changed step definition in the Full CI or offline-contracts workflow.

The check fails closed (exit 1) when a changed file maps to nothing, when the
pull request changes more files than GitHub path filters evaluate, when the
checkout is not the merge commit of the expected HEAD, when a module source is
not a local configuration, when a workflow or Python file cannot be parsed, and
when the map does not match the workflows. Prerequisite and companion steps are
added and the always-on steps are kept. High-risk paths report that Full CI is
required. Nothing here calls AWS, Kubernetes or any network service.
"""
import argparse
import ast
import collections
import functools
import json
import os
import posixpath
import re
import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True
REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "kubernetes/vendor/pyyaml"))
import yaml  # noqa: E402

MAP_FILE = "scripts/ci/impact_map.json"
SHA = re.compile(r"^[0-9a-f]{40}$")
LITERAL = re.compile(r"[A-Za-z0-9_.@+/-]+")
TOKEN = re.compile(r"[A-Za-z0-9_.@+/${}-]+")
SOURCE = re.compile(r'^\s*source\s*=\s*"([^"]*)"', re.M)
PROVIDER_SOURCE = re.compile(r"^(?:[a-z0-9-]+(?:\.[a-z0-9-]+)+/)?[a-z0-9-]+/[a-z0-9-]+$")
STEP_IMPORT = re.compile(r"^\s*(?:import\s+([A-Za-z_][\w, ]*)|from\s+([A-Za-z_]\w*)\s+import\b)", re.M)
WORKSPACE = ("$GITHUB_WORKSPACE/", "${GITHUB_WORKSPACE}/")
PR_SAFETY_OWN_STEPS = ("checkout", "impact", "changed_files")


class ImpactError(Exception):
    """The impact cannot be determined safely: fail closed."""


def require(condition, message):
    if not condition:
        raise ImpactError(message)


def git(*args, cwd=REPO, binary=False):
    process = subprocess.run(["git", *args], cwd=cwd, capture_output=True, check=False)
    require(process.returncode == 0, "git_failed:" + " ".join(args[:3]) + ":"
            + process.stderr.decode("utf-8", "replace").strip()[:300])
    return process.stdout if binary else process.stdout.decode("utf-8")


@functools.lru_cache(maxsize=None)
def glob_regex(pattern):
    """GitHub path-filter globs: ** crosses directories, * and ? do not."""
    out, index = [], 0
    while index < len(pattern):
        if pattern.startswith("**/", index):
            out.append("(?:.*/)?")
            index += 3
        elif pattern.startswith("**", index):
            out.append(".*")
            index += 2
        elif pattern[index] == "*":
            out.append("[^/]*")
            index += 1
        elif pattern[index] == "?":
            out.append("[^/]")
            index += 1
        else:
            out.append(re.escape(pattern[index]))
            index += 1
    return re.compile("^" + "".join(out) + "$")


def matches(path, patterns):
    return any(glob_regex(pattern).match(path) for pattern in patterns)


class Tree:
    """Tracked files of one git revision, or of the index and working tree (rev None)."""

    def __init__(self, rev=None, cwd=REPO, names=None, overrides=None):
        self.rev, self.cwd = rev, Path(cwd)
        if names is None:
            listing = git("ls-files", "-z", cwd=cwd) if rev is None else git("ls-tree", "-r", "-z", "--name-only", rev, cwd=cwd)
            names = [name for name in listing.split("\0") if name]
        self.overrides = dict(overrides or {})
        self.files = sorted(names)
        self.fileset = set(self.files)
        self.dirs = set()
        for name in self.files:
            parent = posixpath.dirname(name)
            while parent:
                self.dirs.add(parent)
                parent = posixpath.dirname(parent)
        self.children = collections.defaultdict(set)
        for name in self.files:
            parent = posixpath.dirname(name)
            while parent:
                self.children[parent].add(name)
                parent = posixpath.dirname(parent)
        self.suffix_files = collections.defaultdict(set)
        self.suffix_dirs = collections.defaultdict(set)
        for collection, index in ((self.files, self.suffix_files), (sorted(self.dirs), self.suffix_dirs)):
            for name in collection:
                parts = name.split("/")
                for start in range(len(parts)):
                    index["/".join(parts[start:])].add(name)
        self._text = {}

    def with_files(self, changes):
        """A copy with files replaced or added (text) or removed (None); used by the tests."""
        names = (self.fileset - {path for path, text in changes.items() if text is None}) | {path for path, text in changes.items() if text is not None}
        overrides = {**self.overrides, **{path: text for path, text in changes.items() if text is not None}}
        return Tree(self.rev, self.cwd, names=sorted(names), overrides=overrides)

    def read(self, path):
        require(path in self.fileset, "not_tracked:" + path)
        if path in self.overrides:
            return self.overrides[path]
        if path not in self._text:
            data = (self.cwd / path).read_bytes() if self.rev is None else git("show", self.rev + ":" + path, cwd=self.cwd, binary=True)
            try:
                self._text[path] = data.decode("utf-8")
            except UnicodeDecodeError as error:
                raise ImpactError("not_utf8:" + path) from error
        return self._text[path]

    def under(self, directory):
        return set(self.children.get(directory, ()))


def load_map(tree):
    try:
        mapping = json.loads(tree.read(MAP_FILE))
    except json.JSONDecodeError as error:
        raise ImpactError("impact_map_unparsable:" + str(error)) from error
    require(mapping.get("schema") == 1, "impact_map_schema")
    return mapping


def raw_step_blocks(text, job):
    """Exact text of each step of one job (the generator copies these verbatim)."""
    lines = text.split("\n")
    try:
        start = lines.index("  " + job + ":")
        steps_at = next(index for index in range(start + 1, len(lines)) if lines[index] == "    steps:")
    except (ValueError, StopIteration) as error:
        raise ImpactError("workflow_steps_not_found:" + job) from error
    blocks, current = [], None
    for line in lines[steps_at + 1:]:
        if line.startswith("      - "):
            current = [line]
            blocks.append(current)
        elif line.strip() == "" or line.startswith("        "):
            require(current is not None, "workflow_step_layout:" + job)
            current.append(line)
        else:
            break
    return ["\n".join(block).rstrip("\n").rstrip() for block in blocks]


def workflow_steps(tree, path, job):
    text = tree.read(path)
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as error:
        raise ImpactError("workflow_unparsable:" + path) from error
    require(isinstance(data, dict) and job in (data.get("jobs") or {}), "workflow_job_missing:" + path + ":" + job)
    steps = data["jobs"][job].get("steps") or []
    blocks = raw_step_blocks(text, job)
    require(len(blocks) == len(steps), "workflow_step_layout:" + path)
    result = []
    for step, block in zip(steps, blocks):
        require(isinstance(step, dict), "workflow_step_not_mapping:" + path)
        result.append({"id": step.get("id"), "name": step.get("name"), "run": step.get("run") or "",
                       "wd": step.get("working-directory"), "uses": step.get("uses"), "if": step.get("if"),
                       "raw": block})
    return data, result


class Steps:
    """Full CI and offline-contracts steps under the ids the map assigns."""

    def __init__(self, tree, mapping):
        _data, full = workflow_steps(tree, mapping["full_ci"]["workflow"], mapping["full_ci"]["job"])
        ids = [step["id"] for step in full]
        require(all(isinstance(value, str) and value for value in ids), "full_ci_step_without_id")
        require(len(set(ids)) == len(ids), "full_ci_duplicate_step_id")
        _data, contracts = workflow_steps(tree, mapping["contracts"]["workflow"], mapping["contracts"]["job"])
        named = mapping["contracts"]["steps"]
        runs = [step for step in contracts if step["run"]]
        require([step["name"] for step in runs] == list(named), "contracts_steps_do_not_match_map")
        require(all(step["uses"] for step in contracts if not step["run"]), "contracts_step_without_run_or_uses")
        for step in runs:
            step["id"] = named[step["name"]]
        self.full = full
        self.contracts = runs
        self.by_id = {step["id"]: step for step in full + runs}
        self.order = [step["id"] for step in full] + [step["id"] for step in runs]


class PythonIndex:
    """Python imports and path literals, resolved against the tracked files."""

    def __init__(self, tree):
        self.tree = tree
        self.by_stem = collections.defaultdict(set)
        for name in tree.files:
            if name.endswith(".py"):
                stem = posixpath.basename(name)[:-3]
                if stem == "__init__":
                    package = posixpath.dirname(name)
                    self.by_stem[posixpath.basename(package)] |= tree.under(package)
                else:
                    self.by_stem[stem].add(name)
        self._deps = {}

    def literal(self, path, value):
        """Tracked files a path literal names: (code it may run, data it may read).

        A literal naming one Python file is code (loaded or executed); every other
        file, and every file under a named directory, is data and is not followed."""
        code, data = self.literal_files(path, value)
        return code | data

    def literal_files(self, path, value):
        value = value.strip()
        if not value or len(value) > 300 or not LITERAL.fullmatch(value):
            return set(), set()
        if value.startswith("./"):
            value = value[2:]
        value = value.strip("/")
        if value in ("", ".", ".."):
            return set(), set()
        tree = self.tree
        if "/" in value:
            files = set(tree.suffix_files.get(value, ()))
            directories = set(tree.suffix_dirs.get(value, ()))
        else:
            base = posixpath.dirname(path)
            candidate = posixpath.join(base, value) if base else value
            files = {candidate} if candidate in tree.fileset else set()
            directories = {candidate} if candidate in tree.dirs else set()
        data = set()
        for directory in directories:
            data |= tree.under(directory)
        code = {name for name in files if name.endswith(".py")}
        return code, (files - code) | data

    def deps(self, path):
        """(code, data): imported or literally named Python files, and data files."""
        if path in self._deps:
            return self._deps[path]
        try:
            module = ast.parse(self.tree.read(path), filename=path)
        except SyntaxError as error:
            raise ImpactError("python_unparsable:" + path + ":" + str(error.lineno)) from error
        skip = set()
        for node in ast.walk(module):
            body = getattr(node, "body", None)
            if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and body:
                first = body[0]
                if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
                    skip.add(id(first.value))
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in ("insert", "append", "extend")
                    and isinstance(node.func.value, ast.Attribute) and node.func.value.attr == "path"
                    and isinstance(node.func.value.value, ast.Name) and node.func.value.value.id == "sys"):
                for argument in node.args:
                    skip.update(id(child) for child in ast.walk(argument))
        code, data = set(), set()
        for node in ast.walk(module):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    code |= self.by_stem.get(alias.name.split(".")[0], set())
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    package = posixpath.dirname(path)
                    for _ in range(node.level - 1):
                        package = posixpath.dirname(package)
                    code |= {name for name in self.tree.under(package) if name.endswith(".py")} if package else set()
                elif node.module:
                    code |= self.by_stem.get(node.module.split(".")[0], set())
            elif isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in skip:
                named_code, named_data = self.literal_files(path, node.value)
                code |= named_code
                data |= named_data
        code.discard(path)
        self._deps[path] = (code, data - code)
        return self._deps[path]

    def closure(self, code_entries, data_entries=()):
        """Entries, the Python they import or name (followed) and the data they name (not followed)."""
        seen, data, queue = set(), set(data_entries), list(code_entries)
        while queue:
            current = queue.pop()
            if current in seen:
                continue
            seen.add(current)
            if current.endswith(".py"):
                code, named = self.deps(current)
                data |= named
                queue.extend(code - seen)
        return seen | data


def step_inputs(tree, index, step):
    """Files a step reads: named paths and the closure of the Python it runs or imports."""
    run = re.sub(r"sys\.path\.insert\([^)]*\)", " ", step["run"])
    work = step["wd"]
    named, data = set(), set()
    for token in TOKEN.findall(run):
        candidates = []
        workspace = next((prefix for prefix in WORKSPACE if token.startswith(prefix)), None)
        if workspace:
            candidates = [token[len(workspace):]]
        elif "$" not in token and "{" not in token:
            candidates = ([posixpath.normpath(posixpath.join(work, token))] if work else []) + [posixpath.normpath(token)]
        for candidate in candidates:
            candidate = candidate.rstrip("/")
            if candidate in tree.fileset:
                named.add(candidate)
                break
            if candidate in tree.dirs:
                # A directory the step runs in (cd) or names: its Python checkers are followed.
                data |= tree.under(candidate)
                named |= {name for name in tree.under(candidate) if name.endswith(".py")}
                break
    for match in STEP_IMPORT.finditer(run):
        for name in (match.group(1) or match.group(2)).split(","):
            named |= index.by_stem.get(name.strip().split(" ")[0], set())
    return index.closure({name for name in named if name.endswith(".py")}, data | {name for name in named if not name.endswith(".py")})


class Terraform:
    """Configurations and the module sources between them."""

    def __init__(self, tree, mapping):
        self.configurations = sorted({posixpath.dirname(name) for name in tree.files
                                      if name.startswith("infra/") and name.endswith(".tf")})
        require(self.configurations == sorted(mapping["configurations"]),
                "configurations_do_not_match_map:" + ",".join(sorted(set(self.configurations) ^ set(mapping["configurations"]))))
        self.dependents = collections.defaultdict(set)
        for config in self.configurations:
            for name in tree.under(config):
                if not (name.endswith(".tf") or name.endswith(".tf.json") or name.endswith(".tftest.hcl")):
                    continue
                base = config if name.endswith(".tftest.hcl") else posixpath.dirname(name)
                for value in SOURCE.findall(tree.read(name)):
                    if value.startswith("./") or value.startswith("../"):
                        target = posixpath.normpath(posixpath.join(base, value))
                        require(target in self.configurations, "module_source_not_a_configuration:" + name + ":" + value)
                        if target != config:
                            self.dependents[target].add(config)
                    else:
                        require(PROVIDER_SOURCE.match(value), "unsupported_module_source:" + name + ":" + value)

    def configuration_of(self, path):
        owners = [config for config in self.configurations if path.startswith(config + "/")]
        return owners[0] if owners else None

    def all_dependents(self, config):
        seen, queue = set(), list(self.dependents.get(config, ()))
        while queue:
            current = queue.pop()
            if current not in seen:
                seen.add(current)
                queue.extend(self.dependents.get(current, ()))
        return seen


def terraform_relevant(config, path):
    """Files a dependent configuration loads: not tests, test files or Markdown."""
    relative = path[len(config) + 1:]
    return not (relative.startswith("tests/") or relative.endswith(".tftest.hcl") or relative.endswith(".md"))


def changed_step_definitions(head_steps, base_tree, mapping, selectable):
    """Full CI and contracts steps whose definition differs from the base workflow."""
    if base_tree is None:
        return set(), []
    base_by_key = {}
    try:
        for key in ("full_ci", "contracts"):
            if mapping[key]["workflow"] not in base_tree.fileset:
                continue
            _data, base_steps = workflow_steps(base_tree, mapping[key]["workflow"], mapping[key]["job"])
            for step in base_steps:
                if step["id"]:
                    base_by_key[("id", step["id"])] = step["raw"]
                if step["name"]:
                    base_by_key[("name", step["name"])] = step["raw"]
    except ImpactError:
        return set(selectable), ["base workflow not comparable: every selectable step"]
    changed = set()
    for step in head_steps.full + head_steps.contracts:
        old = base_by_key.get(("id", step["id"]), base_by_key.get(("name", step["name"])))
        if old != step["raw"] and step["id"] in selectable:
            changed.add(step["id"])
    if not base_by_key:
        return set(selectable), ["base workflow missing: every selectable step"]
    return changed, []


class Analysis:
    def __init__(self, head_tree, base_tree=None):
        self.head, self.base = head_tree, base_tree
        self.mapping = load_map(head_tree)
        self.steps = Steps(head_tree, self.mapping)
        self.terraform = Terraform(head_tree, self.mapping)
        self.check_map()
        self.inputs = {}
        for tree in [tree for tree in (head_tree, base_tree) if tree is not None]:
            index = PythonIndex(tree)
            for step_id in self.selectable:
                self.inputs.setdefault(step_id, set()).update(step_inputs(tree, index, self.steps.by_id[step_id]))

    def check_map(self):
        mapping, steps = self.mapping, self.mapping["steps"]
        always, full_only, selectable = steps["always"], steps["full_only"], steps["selectable"]
        self.always, self.selectable = list(always), list(selectable)
        classified = list(always) + list(full_only) + list(selectable)
        require(len(set(classified)) == len(classified), "step_classified_twice")
        require(set(classified) == set(self.steps.order), "steps_do_not_match_map:"
                + ",".join(sorted(set(classified) ^ set(self.steps.order))))
        known = set(selectable)
        references = list(mapping["companions"]) + [item for items in mapping["companions"].values() for item in items]
        references += list(mapping["prerequisites"]) + [item for items in mapping["prerequisites"].values() for item in items]
        references += [item for items in mapping["configurations"].values() for item in items]
        references += [item for rule in mapping["rules"] for item in rule["steps"]]
        require(set(references) <= known, "map_references_unknown_step:" + ",".join(sorted(set(references) - known)))
        position = {step_id: number for number, step_id in enumerate(self.steps.order)}
        for step_id, needed in mapping["prerequisites"].items():
            require(all(position[item] < position[step_id] for item in needed), "prerequisite_after_step:" + step_id)
        for rule in mapping["rules"]:
            require(set(rule) <= {"id", "paths", "exclude", "steps", "reason"} and rule["paths"] and rule["reason"], "rule_shape:" + str(rule.get("id")))
        require(isinstance(mapping["max_changed_files"], int) and 0 < mapping["max_changed_files"] <= 300, "max_changed_files")

    def map_file(self, path):
        """Steps and reasons for one path; an empty reason list means unmapped."""
        steps, reasons = set(), []
        config = self.terraform.configuration_of(path)
        if config and not path.endswith(".md"):
            steps.update(self.mapping["configurations"][config])
            reasons.append("configuration " + config)
            if terraform_relevant(config, path):
                for dependent in sorted(self.terraform.all_dependents(config)):
                    steps.update(self.mapping["configurations"][dependent])
                    reasons.append("sourced by " + dependent)
        inputs = sorted(step_id for step_id in self.selectable if path in self.inputs.get(step_id, ()))
        if inputs:
            steps.update(inputs)
            reasons.append("input of " + ", ".join(inputs))
        for rule in self.mapping["rules"]:
            if matches(path, rule["paths"]) and not matches(path, rule.get("exclude", [])):
                steps.update(rule["steps"])
                reasons.append("rule " + rule["id"])
        return steps, reasons

    def high_risk(self, path):
        return sorted(category for category, patterns in self.mapping["high_risk"].items() if matches(path, patterns))

    def expand(self, steps):
        selected = set(steps)
        for step_id in list(selected):
            selected.update(self.mapping["companions"].get(step_id, ()))
        queue = list(selected)
        while queue:
            for needed in self.mapping["prerequisites"].get(queue.pop(), ()):
                if needed not in selected:
                    selected.add(needed)
                    queue.append(needed)
        return [step_id for step_id in self.steps.order if step_id in selected]

    def select(self, changes):
        require(len(changes) <= self.mapping["max_changed_files"],
                "too_many_changed_files:%d>%d (GitHub path filters evaluate at most 300; split the pull request)"
                % (len(changes), self.mapping["max_changed_files"]))
        rows, unmapped, chosen, risks = [], [], set(), collections.defaultdict(list)
        for status, path in changes:
            steps, reasons = self.map_file(path)
            if not reasons:
                unmapped.append(path)
            chosen |= steps
            categories = self.high_risk(path)
            for category in categories:
                risks[category].append(path)
            rows.append({"path": path, "status": status, "steps": sorted(steps), "reasons": reasons, "high_risk": categories})
        require(not unmapped, "unmapped_paths (add a configuration, rule or step input to scripts/ci/impact_map.json):"
                + ",".join(unmapped))
        changed_paths = {path for _status, path in changes}
        definitions, notes = set(), []
        workflows = {self.mapping["full_ci"]["workflow"], self.mapping["contracts"]["workflow"]}
        if changed_paths & workflows:
            definitions, notes = changed_step_definitions(self.steps, self.base, self.mapping, self.selectable)
            chosen |= definitions
        selected = self.expand(chosen)
        return {"selected": selected, "always": self.always,
                "skipped": [step_id for step_id in self.selectable if step_id not in selected],
                "changed": rows, "changed_step_definitions": sorted(definitions), "notes": notes,
                "high_risk": dict(sorted(risks.items())), "full_ci_required": bool(risks)}

    def coverage(self):
        unmapped = [path for path in self.head.files if not self.map_file(path)[1]]
        require(not unmapped, "tracked_files_unmapped:" + ",".join(unmapped))
        reachable = set()
        for path in self.head.files:
            reachable |= self.map_file(path)[0]
        orphans = [step_id for step_id in self.selectable if step_id not in set(self.expand(reachable))]
        require(not orphans, "steps_never_selected:" + ",".join(orphans))
        return len(self.head.files)


def merge_changes(head_sha_expected):
    """Changed files of the checked-out pull request merge commit against its first parent."""
    parents = git("rev-list", "--parents", "-n", "1", "HEAD").split()
    require(len(parents) == 3, "checkout_is_not_a_merge_commit")
    require(SHA.match(head_sha_expected or ""), "event_head_sha_invalid")
    require(parents[2:3] == [head_sha_expected], "merge_commit_does_not_contain_event_head:" + " ".join(parents[2:]))
    return parents[1], parents[0]


def diff(base, head):
    output = git("diff", "--name-status", "--no-renames", "-z", base, head)
    fields = [field for field in output.split("\0") if field]
    require(len(fields) % 2 == 0, "diff_unparsable")
    changes = [(fields[index], fields[index + 1]) for index in range(0, len(fields), 2)]
    require(all(status in ("A", "M", "D", "T") for status, _path in changes), "diff_status_unexpected")
    return changes


def summary(report):
    lines = ["## PR Safety CI impact", "",
             f"Base `{report['base']}` -> head `{report['head']}`; {len(report['changed'])} changed files.", "",
             "| Changed file | Status | Selected Full CI steps | Why | High risk |", "| --- | --- | --- | --- | --- |"]
    for row in report["changed"]:
        lines.append("| `{}` | {} | {} | {} | {} |".format(row["path"], row["status"], ", ".join(row["steps"]) or "always-on only",
                                                       "; ".join(row["reasons"]), ", ".join(row["high_risk"]) or "-"))
    lines += ["", "Always-on: " + ", ".join(report["always"]), "",
              "Selected (with prerequisites): " + (", ".join(report["selected"]) or "none"), "",
              "Not selected: " + (", ".join(report["skipped"]) or "none")]
    if report["changed_step_definitions"]:
        lines += ["", "Changed step definitions: " + ", ".join(report["changed_step_definitions"])]
    if report["full_ci_required"]:
        lines += ["", "**FULL CI REQUIRED** (high-risk: " + ", ".join(report["high_risk"]) + "). Full CI must succeed on this exact HEAD "
                  "before merge approval; PR Safety CI PASS is not Full CI PASS."]
    else:
        lines += ["", "No high-risk path changed. Full CI runs only when the Owner designates a milestone (FULL CI NOT RUN otherwise)."]
    return "\n".join(lines) + "\n"


def verify(report_path, workflow_path, results):
    """Every selected and always-on step succeeded and every other generated step was skipped."""
    require(Path(report_path).is_file(), "impact_report_missing (the impact step did not complete)")
    report = json.loads(Path(report_path).read_text(encoding="utf-8"))
    data = yaml.safe_load(Path(workflow_path).read_text(encoding="utf-8"))
    generated = [step.get("id") for step in data["jobs"]["pr-safety"]["steps"] if step.get("id")]
    expected = set(report["selected"]) | set(report["always"]) | set(PR_SAFETY_OWN_STEPS)
    problems = []
    for step_id in generated:
        outcome = (results.get(step_id) or {}).get("outcome")
        wanted = "success" if step_id in expected else "skipped"
        if outcome != wanted:
            problems.append(f"{step_id}: {outcome} (expected {wanted})")
    missing = sorted(expected - set(generated))
    require(not missing, "selected_steps_missing_from_workflow:" + ",".join(missing))
    require(not problems, "step_outcomes:" + "; ".join(problems))
    return generated


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    select = commands.add_parser("select", help="map the changed files of a pull request (fail closed)")
    select.add_argument("--event-head", help="pull_request.head.sha; HEAD must be its merge commit")
    select.add_argument("--base", help="explicit base revision (local use)")
    select.add_argument("--head", help="explicit head revision (local use)")
    select.add_argument("--report", required=True)
    select.add_argument("--github", action="store_true", help="write GITHUB_OUTPUT and the job summary")
    commands.add_parser("check", help="map consistency and coverage of every tracked file")
    explain = commands.add_parser("explain", help="show how paths map")
    explain.add_argument("paths", nargs="+")
    verify_parser = commands.add_parser("verify", help="check generated step outcomes (STEP_RESULTS)")
    verify_parser.add_argument("--report", required=True)
    verify_parser.add_argument("--workflow", default=".github/workflows/pr-safety-ci.yml")
    args = parser.parse_args(argv)
    try:
        if args.command == "select":
            if args.base or args.head:
                require(args.base and args.head and not args.event_head, "select_needs_base_and_head")
                base = git("rev-parse", "--verify", args.base + "^{commit}").strip()
                head = git("rev-parse", "--verify", args.head + "^{commit}").strip()
            else:
                base, head = merge_changes(args.event_head)
            analysis = Analysis(Tree(head), Tree(base))
            report = {"base": base, "head": head, **analysis.select(diff(base, head))}
            Path(args.report).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
            text = summary(report)
            print(text)
            if args.github:
                with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as output:
                    output.write("selected=" + json.dumps(report["selected"]) + "\n")
                    output.write("full_ci_required=" + ("true" if report["full_ci_required"] else "false") + "\n")
                with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as output:
                    output.write(text)
        elif args.command == "check":
            analysis = Analysis(Tree())
            print(json.dumps({"status": "passed", "tracked_files_mapped": analysis.coverage(),
                              "configurations": len(analysis.terraform.configurations),
                              "selectable_steps": len(analysis.selectable), "always_steps": len(analysis.always)}))
        elif args.command == "explain":
            analysis = Analysis(Tree())
            for path in args.paths:
                steps, reasons = analysis.map_file(path)
                print(json.dumps({"path": path, "steps": analysis.expand(steps), "reasons": reasons or ["UNMAPPED"],
                                  "high_risk": analysis.high_risk(path)}))
        else:
            results = json.loads(os.environ.get("STEP_RESULTS") or "{}")
            generated = verify(args.report, args.workflow, results)
            print(json.dumps({"status": "passed", "verified_steps": len(generated)}))
    except ImpactError as error:
        print("PR Safety CI impact check failed closed: " + str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
