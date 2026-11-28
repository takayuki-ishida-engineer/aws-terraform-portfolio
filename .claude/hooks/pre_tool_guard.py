#!/usr/bin/env python3
"""Deterministic PreToolUse guard for Claude Code sessions in this repository.

Reads one hook event (JSON object) on stdin and prints nothing for a call that may fall
through to the normal permission system. Otherwise it prints one official PreToolUse
decision: "deny" for absolute prohibitions, malformed or ambiguous input and unknown
tools, and "ask" for scoped governance-file changes, which still need the exact
Owner-approved scope. It never prints "allow", so it never overrides native permissions.

The repository root comes from this file's location, never from the event. The event cwd
is used only to resolve relative tool paths. Standard library only; no network, no LLM
call and no reading of file contents. This is defense in depth, not a sandbox: the
Bash checks are conservative text rules, not a shell parser.

    python3 .claude/hooks/pre_tool_guard.py --self-test
"""
import fnmatch
import json
import os
import re
import shlex
import sys
from pathlib import Path, PurePosixPath

REPO = Path(__file__).resolve().parents[2]

# Sensitive file names: never read, written or handed to a shell command.
SENSITIVE_NAMES = ("*.tfstate", "*.tfstate.*", "*.tfplan", "*.tfplan.*", "tfplan", "planout", "plan.out",
                   ".terraform.tfstate.lock.info", "local.auto.tfvars", "local.auto.tfvars.json",
                   "*.local.tfvars", "*.local.tfvars.json", "*.tfbackend", "backend_override.tf",
                   "backend_override.tf.json", ".env", ".env.*", "*.pem", "*.key", "*.p12", "*.pfx", "*.jks",
                   "*.keystore", "id_rsa", "id_ed25519", "id_ecdsa", ".netrc", ".git-credentials")
SENSITIVE_DIRS = (".aws", ".ssh", ".gnupg", ".docker", ".kube", ".config/gh")  # under the home directory

# Governance files: file-tool edits ASK (exact scoped approval); shell mutation is DENIED.
PROTECTED = ("AGENTS.md", "CLAUDE.md", ".claude/**", ".github/**", "scripts/ci/**",
             "scripts/repository-hygiene/**", "scripts/local-workflow/**", "scripts/emulator-verification/**",
             "scripts/emulator-rehearsal/**", "scripts/emulator-evidence/**", "scripts/aws-policy-validation/**",
             "scripts/terraform-testing/isolated_root.py", "tests/expected-counts.json",
             "docs/portfolio-verification-policy.md", "docs/policy-v14-2-alignment.md",
             "docs/step1-audit-report.md", "docs/step2-emulator-rehearsals.md", "docs/step3/**",
             "docs/evidence/**", ".terraform.lock.hcl", "**/.terraform.lock.hcl", "kubernetes/dependencies.lock.json",
             "kubernetes/images.lock.json", "kubernetes/vendor/**", ".gitignore", ".gitattributes",
             ".editorconfig")
EVIDENCE = "docs/evidence/**"  # append-only: an existing file is never edited

EDIT_TOOLS = {"Edit": "file_path", "Write": "file_path", "MultiEdit": "file_path", "NotebookEdit": "notebook_path"}
READ_TOOLS = {"Read", "Grep", "Glob"}
KNOWN_TOOLS = set(EDIT_TOOLS) | READ_TOOLS | {"Bash"}

SEG = r"(?:^|[;&|(`]|\n|\$\()\s*(?:sudo\s+|command\s+|exec\s+|time\s+|nohup\s+)*"
SECRET_VAR = re.compile(r"\$\{?[A-Za-z0-9_]*(?:SECRET|TOKEN|PASSWORD|PASSWD|ACCESS_KEY|SESSION|API_KEY|CREDENTIAL)"
                        r"[A-Za-z0-9_]*\b|\$\{?AWS_[A-Z0-9_]+")
BASH_DENY = (
    (re.compile(r"\bgit\s+push\b[^;&|\n]*(?:\s|:)(?:refs/heads/)?main(?:\s|$|[;&|)])"), "push to main"),
    (re.compile(r"\bgit\s+push\b[^;&|\n]*(?:\s--force(?:-with-lease|-if-includes)?\b|\s-[a-zA-Z]*f\b|\s\+\S)"),
     "force push (including force-with-lease)"),
    (re.compile(r"\bgit\s+push\b[^;&|\n]*(?:\s--delete\b|\s-d\b|\s:\S)"), "remote branch or tag deletion"),
    (re.compile(SEG + r"gh\s+(?:pr\s+merge|repo\s+(?:delete|edit|rename|archive)|release\s+delete|secret|variable|"
                r"ruleset|auth\s+token)\b"), "Owner-only GitHub operation or credential access"),
    (re.compile(SEG + r"gh\s+api\b[^;&|\n]*(?:-X|--method)\s*(?!GET\b)[A-Z]"), "mutating GitHub API call"),
    (re.compile(SEG + r"git\s+(?:reset\s+--hard|clean\s+-[a-zA-Z]*[fdx]|branch\s+-[a-zA-Z]*[dD]\b|tag\s+-d\b|"
                r"update-ref\s+-d|reflog\s+(?:expire|delete)|filter-branch|filter-repo|gc\s+--prune)"),
     "destructive Git operation"),
    (re.compile(SEG + r"(?:aws|aws-vault|aws-sso|sam|cdk|eksctl|copilot)\s"), "real AWS / AWS SSO / STS / API operation"),
    (re.compile(r"\bboto3\b|\bbotocore\b"), "direct AWS SDK use"),
    (re.compile(SEG + r"(?:terraform|tofu)\b[^;&|\n]*\s(?:plan|apply|destroy|import|refresh|taint|untaint|"
                r"force-unlock|state|output|console|login|logout)\b"), "Terraform plan/apply/destroy/import or State access"),
    (re.compile(SEG + r"kubectl\b(?![^;&|\n]*\s--client\b)"), "Kubernetes / EKS cluster operation"),
    (re.compile(SEG + r"helm\s+(?:install|upgrade|uninstall|delete|rollback|push|test|registry)\b"),
     "Helm cluster or registry operation"),
    (SECRET_VAR, "credential or secret environment value"),
    (re.compile(SEG + r"(?:printenv|env|set|export\s+-p|declare\s+-x)\s*(?:$|[;&|)])"), "environment dump"),
    (re.compile(r"/proc/[^\s/]+/environ|\.aws/credentials|\.aws/config|\.config/gh|\.git-credentials|\.netrc|"
                r"\bgit\s+credential\b|\.ssh/"), "credential store access"),
    (re.compile(SEG + r"rm\s+-[a-zA-Z]*[rRf][a-zA-Z]*\s+(?:--\s+)?(?:/|~|\$HOME|\.|\.\.|\*)\s*(?:$|[;&|)])"),
     "recursive delete of a root, home or working directory"),
)
BASH_ASK = (
    (re.compile(SEG + r"(?:git\s+(?:apply|am)\b|patch\b)"), "opaque patch application; confirm the exact target files"),
)
# Commands that can read file contents (used with sensitive names) or mutate files (used with protected paths).
READERS = r"(?:cat|tac|less|more|head|tail|cp|mv|scp|rsync|base64|xxd|od|hexdump|strings|grep|egrep|rg|awk|sed|cut|" \
          r"sort|uniq|diff|cmp|jq|yq|tar|zip|gzip|openssl|curl|wget|nc|vi|vim|nano|source|\.|python3?|perl|ruby|node|php)"
MUTATORS = r"(?:rm|mv|cp|ln|install|rsync|tee|truncate|dd|chmod|chown|touch|unlink|shred|mkdir|rmdir|sed\s+[^;&|\n]*-i|" \
           r"perl\s+[^;&|\n]*-[a-zA-Z]*i|git\s+(?:rm|mv|checkout\s+[^;&|\n]*--|restore|update-index))"
INTERP_INLINE = r"(?:python3?|perl|ruby|node|php|bash|sh|zsh)\s+(?:-[a-zA-Z]*[ce]\b|-\s|<<|$)"


def decision(kind, reason):
    return kind, "repository guard: " + reason


def is_sensitive(path):
    name = PurePosixPath(path).name
    if any(fnmatch.fnmatchcase(name, pattern) for pattern in SENSITIVE_NAMES):
        return True
    home = os.path.expanduser("~")
    return any(path == os.path.join(home, d) or path.startswith(os.path.join(home, d) + os.sep) for d in SENSITIVE_DIRS)


def protected(rel):
    return any(fnmatch.fnmatchcase(rel, pattern) or (pattern.endswith("/**") and rel == pattern[:-3])
               for pattern in PROTECTED)


def repo_relative(path):
    try:
        return Path(path).relative_to(REPO).as_posix()
    except ValueError:
        return None


def resolve_paths(raw, cwd):
    """Return (lexical, resolved) absolute paths; raise ValueError when invalid or ambiguous."""
    if not isinstance(raw, str) or not raw or "\x00" in raw or len(raw) > 4096:
        raise ValueError("invalid path")
    expanded = os.path.expanduser(raw)
    if not os.path.isabs(expanded):
        if not isinstance(cwd, str) or not os.path.isabs(cwd) or "\x00" in cwd:
            raise ValueError("relative path without an absolute cwd")
        expanded = os.path.join(cwd, expanded)
    lexical = os.path.normpath(expanded)
    resolved = str(Path(expanded).resolve(strict=False))  # resolve symlinks before collapsing parent traversal
    return lexical, resolved


def classify_path(tool, raw, cwd):
    lexical, resolved = resolve_paths(raw, cwd)
    if is_sensitive(lexical) or is_sensitive(resolved):
        return decision("deny", "state, plan, key, credential or local value file: " + PurePosixPath(raw).name)
    if tool in READ_TOOLS:
        return None
    for candidate in (lexical, resolved):
        rel = repo_relative(candidate)
        if rel is None:
            continue
        if fnmatch.fnmatchcase(rel, EVIDENCE) and os.path.lexists(candidate):
            return decision("deny", "existing evidence is append-only: " + rel)
    for candidate in (lexical, resolved):
        rel = repo_relative(candidate)
        if rel is not None and protected(rel):
            return decision("ask", "protected governance file " + rel + "; proceed only within the exact "
                            "Owner-approved scope (approval is not a policy waiver)")
    return None


def shell_paths(words, cwds):
    """Conservative literal candidates, not shell expansion or a shell parser."""
    for word in words:
        if not word or word.startswith("-") or word in (";", "&&", "||", "|", "&"):
            continue
        for cwd in cwds:
            yield from resolve_paths(word, cwd)


def protected_path(paths):
    for path in paths:
        rel = repo_relative(path)
        if rel is not None and protected(rel):
            return rel
    return None


def git_push_boundary(words):
    """Recognize explicit literal git push forms; native permissions still apply."""
    separators = (";", "&&", "||", "|", "&", "(", ")", ">", ">>", "<", "\n")
    for i, word in enumerate(words):
        if PurePosixPath(word).name != "git":
            continue
        segment = []
        for token in words[i + 1:]:
            if token in separators:
                break
            segment.append(token)
        # Skip recognized global options and their values. An unrecognized global
        # option is ambiguous and is not accepted for a detected push operation.
        j = 0
        while j < len(segment) and segment[j].startswith("-"):
            option = segment[j]
            if option in ("-C", "-c", "--git-dir", "--work-tree", "--namespace", "--config-env"):
                j += 2
            elif option in ("--no-pager", "--paginate", "--literal-pathspecs", "--no-optional-locks") or option.startswith(("--git-dir=", "--work-tree=", "--namespace=", "--config-env=")):
                j += 1
            else:
                if "push" in segment[j:]:
                    return decision("deny", "unrecognized git push option")
                break
        if j >= len(segment) or segment[j] != "push":
            continue
        if any(a in ("-c", "--config-env", "--namespace", "--git-dir", "--work-tree") or
               a.startswith(("--config-env=", "--namespace=", "--git-dir=", "--work-tree=")) for a in segment[:j]):
            return decision("deny", "git push cannot override repository or Git configuration")
        args = segment[j + 1:]
        if any(a.startswith(("+", ":", "--force", "--delete", "--all", "--mirror", "--tags", "--follow-tags", "--prune")) or
               a.startswith("-") and not a.startswith("--") and any(c in a[1:] for c in "fd") for a in args):
            return decision("deny", "force, delete or broad git push")
        supported = {"-u", "--set-upstream", "-n", "--dry-run", "--porcelain", "-v", "--verbose",
                     "-q", "--quiet", "--atomic", "--progress"}
        if any(a.startswith("-") and a not in supported for a in args):
            return decision("deny", "unsupported git push option")
        positional = [a for a in args if not a.startswith("-")]
        if len(positional) != 2:
            return decision("deny", "git push requires one explicit remote and destination ref")
        ref = positional[1]
        destination = ref.rsplit(":", 1)[-1]
        if (destination in ("main", "refs/heads/main", "HEAD", "@") or not destination or
                (destination.startswith("refs/") and not destination.startswith("refs/heads/")) or
                any(c in ref for c in "$`*?[]{}") or ref.count(":") > 1):
            return decision("deny", "protected or ambiguous git push destination")
    return None


def classify_bash(command, cwd):
    if not isinstance(command, str) or not command.strip() or "\x00" in command:
        raise ValueError("missing or invalid command")
    if not isinstance(cwd, str) or not os.path.isabs(cwd) or "\x00" in cwd:
        raise ValueError("invalid Bash cwd")
    for pattern, reason in BASH_DENY:
        if pattern.search(command):
            return decision("deny", reason)
    lexer = shlex.shlex(command, posix=True, punctuation_chars=";&|<>()")
    lexer.whitespace_split = True
    lexer.commenters = ""
    words = list(lexer)
    git_result = git_push_boundary(words)
    if git_result:
        return git_result
    # The regex supplements shlex for literal paths embedded in inline source.
    # No shell expansion is performed. Include literal cd destinations as possible
    # working directories; unknown destinations cannot authorize a file mutation.
    names = words + re.findall(r"[A-Za-z0-9_./~${}\-]+", command)
    mutates = bool(re.search(SEG + MUTATORS, command) or re.search(SEG + INTERP_INLINE, command) or
                   re.search(SEG + r"find\b[^;&|\n]*(?:-delete|-exec(?:dir)?)\b", command))
    reads = bool(re.search(SEG + READERS + r"\b", command))
    redirect_ops = {">", ">>", ">|", "&>", "&>>", ">&", "<", "<>", "<&"}
    cwds = {cwd}
    for i, word in enumerate(words):
        if word not in ("cd", "pushd", "popd"):
            continue
        target = words[i + 1] if i + 1 < len(words) else ""
        if word == "popd" or not target or target.startswith("-") or any(c in target for c in "$`*?[]{}"):
            if mutates or reads or redirect_ops.intersection(words):
                return decision("deny", "ambiguous shell working directory for file operation")
            continue
        cwds.update(path for path in shell_paths([target], tuple(cwds)))
        if len(cwds) > 32:
            return decision("deny", "too many possible shell working directories")
    for i, word in enumerate(words):
        if word not in redirect_ops:
            continue
        target = words[i + 1] if i + 1 < len(words) else ""
        if word in (">&", "<&") and (target.isdecimal() or target == "-"):
            continue
        if not target or target in redirect_ops or any(c in target for c in "$`*?[]{}"):
            return decision("deny", "ambiguous shell redirection target")
        paths = list(shell_paths([target], cwds))
        if any(is_sensitive(path) for path in paths):
            return decision("deny", "sensitive shell redirection target")
        if word not in ("<", "<&") and protected_path(paths):
            return decision("deny", "shell write to protected file (use a file-edit tool within approved scope)")
    if mutates or reads:
        paths = list(shell_paths(names, cwds))
        if any(is_sensitive(path) for path in paths):
            return decision("deny", "state, plan, key, credential or local value file in a shell command")
        if mutates and protected_path(paths):
            return decision("deny", "shell mutation of protected file (use a file-edit tool within approved scope)")
    for pattern, reason in BASH_ASK:
        if pattern.search(command):
            return decision("ask", reason)
    return None

def decide(event):
    if not isinstance(event, dict):
        raise ValueError("event is not an object")
    tool, data = event.get("tool_name"), event.get("tool_input")
    if not isinstance(tool, str) or not tool or not isinstance(data, dict):
        raise ValueError("missing tool_name or tool_input")
    if tool not in KNOWN_TOOLS:
        return decision("deny", "unknown tool routed to the guard: " + tool[:64])
    cwd = event.get("cwd", str(REPO))
    if tool == "Bash":
        return classify_bash(data.get("command"), cwd)
    if tool in EDIT_TOOLS:
        return classify_path(tool, data.get(EDIT_TOOLS[tool]), cwd)
    if tool == "Read":
        return classify_path(tool, data.get("file_path"), cwd)
    if tool == "Grep":
        if not isinstance(data.get("pattern"), str):
            raise ValueError("missing Grep pattern")
        glob = data.get("glob")
        if glob is not None and (not isinstance(glob, str) or is_sensitive(glob) or any(
                fnmatch.fnmatchcase(PurePosixPath(glob).name, s) or s.lstrip("*") in glob for s in SENSITIVE_NAMES
                if s.startswith("*."))):
            return decision("deny", "search targets state, plan, key or credential files")
        return classify_path(tool, data["path"], cwd) if data.get("path") is not None else None
    if not isinstance(data.get("pattern"), str):  # Glob
        raise ValueError("missing Glob pattern")
    return None  # Glob lists names only


def evaluate(text):
    try:
        return decide(json.loads(text))
    except Exception as error:  # malformed, ambiguous or unexpected input never falls through
        return decision("deny", "invalid or unverifiable hook input (" + type(error).__name__ + ")")


def emit(result):
    if result:
        kind, reason = result
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": kind,
                                                 "permissionDecisionReason": reason}}))


def self_test():
    root, out = str(REPO), "/tmp/claude-guard-self-test"
    cases = [
        ({"tool_name": "Bash", "tool_input": {"command": "git push -u origin claude/harness-optimization"}}, None),
        ({"tool_name": "Bash", "tool_input": {"command": "git push origin HEAD:main"}}, "deny"),
        ({"tool_name": "Bash", "tool_input": {"command": "git push --force-with-lease origin x"}}, "deny"),
        ({"tool_name": "Bash", "tool_input": {"command": "cd a && gh pr merge 1"}}, "deny"),
        ({"tool_name": "Bash", "tool_input": {"command": "terraform apply"}}, "deny"),
        ({"tool_name": "Bash", "tool_input": {"command": "terraform test -no-color"}}, None),
        ({"tool_name": "Bash", "tool_input": {"command": "aws s3 ls"}}, "deny"),
        ({"tool_name": "Bash", "tool_input": {"command": "env"}}, "deny"),
        ({"tool_name": "Bash", "tool_input": {"command": "head x/terraform.tfstate"}}, "deny"),
        ({"tool_name": "Bash", "tool_input": {"command": "tee CLAUDE.md < x"}}, "deny"),
        ({"tool_name": "Bash", "tool_input": {"command": "python3 scripts/ci/impact.py check"}}, None),
        ({"tool_name": "Bash", "tool_input": {"command": "git diff --cached --name-status"}}, None),
        ({"tool_name": "Bash", "tool_input": {"command": "git apply x.patch"}}, "ask"),
        ({"tool_name": "Edit", "tool_input": {"file_path": "AGENTS.md"}, "cwd": root}, "ask"),
        ({"tool_name": "Edit", "tool_input": {"file_path": "../CLAUDE.md"}, "cwd": root + "/docs"}, "ask"),
        ({"tool_name": "Edit", "tool_input": {"file_path": root + "/docs/evidence/emulator-runs/index.md"}}, "deny"),
        ({"tool_name": "Write", "tool_input": {"file_path": root + "/infra/a/local.auto.tfvars"}}, "deny"),
        ({"tool_name": "Edit", "tool_input": {"file_path": root + "/infra/modules/vpc/main.tf"}}, None),
        ({"tool_name": "Write", "tool_input": {"file_path": out + "/notes.md"}}, None),
        ({"tool_name": "Read", "tool_input": {"file_path": out + "/.env"}}, "deny"),
        ({"tool_name": "Read", "tool_input": {"file_path": root + "/AGENTS.md"}}, None),
        ({"tool_name": "Grep", "tool_input": {"pattern": "x", "glob": "**/*.tfstate"}}, "deny"),
        ({"tool_name": "Edit", "tool_input": {"file_path": "x"}, "cwd": "relative"}, "deny"),
        ({"tool_name": "Mystery", "tool_input": {}}, "deny"),
    ]
    failures = [(event, expected, got) for event, expected in cases
                for got in [evaluate(json.dumps(event))] if (got[0] if got else None) != expected]
    for raw, expected in (("", "deny"), ("[]", "deny"), ("{", "deny")):
        got = evaluate(raw)
        if (got[0] if got else None) != expected:
            failures.append((raw, expected, got))
    for failure in failures:
        print("FAIL", failure)
    total = len(cases) + 3
    print("self-test: %d cases, %d failures" % (total, len(failures)))
    return 1 if failures else 0


def main():
    if sys.argv[1:] == ["--self-test"]:
        return self_test()
    emit(evaluate(sys.stdin.read()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
