#!/usr/bin/env python3
"""Offline tests for mirror_images.py (finding F18, B3).

Fake ``aws``, ``skopeo`` and ``terraform`` executables simulate the upstream
registries and the private ECR repositories in a JSON state file, and record every
call. No network, registry, AWS API or real image is used: ``plan`` is run with
process creation and sockets disabled, and ``mirror`` only ever reaches the fakes.

The scenarios check the copy plan and its exact skopeo arguments, digest, platform
and child manifest verification, upstream tag moves, immutable tag conflicts,
unexpected images, partial failures, account, Region, project and repository
mismatches, idempotent re-runs, the ECR token (never in an argument or output, the
authfile deleted on success and failure) and the refusal in CI and cloud sessions.
``MutationTests`` applies source mutations to mirror_images.py, each removing one
guard, and requires the matching scenario to detect it.
"""
import contextlib
import copy
import hashlib
import importlib.util
import io
import json
import os
import socket
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import mirror_images  # noqa: E402
import preflight  # noqa: E402

PROJECT = "acme"
ACCOUNT = "444455556666"
HOST = f"{ACCOUNT}.dkr.ecr.ca-central-1.amazonaws.com"
# A synthetic ECR login password: long enough that it would also be caught by redaction.
TOKEN = "fake-ecr-login-" + "0123456789abcdef" * 6
LOCK = json.loads((preflight.REPOSITORY / "kubernetes/images.lock.json").read_text())
RAW = {item["purpose"]: (preflight.REPOSITORY / item["manifest_file"]).read_bytes() for item in LOCK["images"]}
PURPOSES = sorted(RAW)
# Written independently of mirror_images.COPY_OPTIONS.
EXPECTED_COPY_OPTIONS = ["--all", "--preserve-digests", "--src-no-creds", "--src-tls-verify=true",
                         "--dest-tls-verify=true"]
ALLOWED_AWS = {("--version",), ("sts", "get-caller-identity"), ("ecr", "describe-repositories"),
               ("ecr", "describe-images"), ("ecr", "get-login-password")}

FAKE_SKOPEO = textwrap.dedent("""\
    import base64, hashlib, json, os, sys
    args = sys.argv[1:]
    password = sys.stdin.read() if "--password-stdin" in args else None
    for arg in args:
        if arg.startswith("--password="):
            password = arg.split("=", 1)[1]
    entry = {"tool": "skopeo", "argv": args}
    if password is not None:
        entry["password_sha256"] = hashlib.sha256(password.encode()).hexdigest()
    with open(os.environ["FAKE_LOG"], "a") as log:
        log.write(json.dumps(entry) + "\\n")
    state_path = os.environ["FAKE_STATE"]
    state = json.load(open(state_path))
    def save():
        json.dump(state, open(state_path, "w"))
    def fail(message):
        sys.stderr.write(message + "\\n")
        sys.exit(1)
    def sha(text):
        return "sha256:" + hashlib.sha256(text.encode()).hexdigest()
    def authorized(flag, host):
        path = args[args.index(flag) + 1] if flag in args else None
        if not path or not os.path.isfile(path):
            return False
        auth = json.load(open(path)).get("auths", {}).get(host, {}).get("auth", "")
        return base64.b64decode(auth).decode() == "AWS:" + state["token"]
    def split(reference):
        rest = reference[len("docker://"):]
        if "@" in rest:
            name, digest = rest.split("@")
            return name, None, digest
        name, tag = rest.rsplit(":", 1)
        return name, tag, None
    if any("tls-verify=false" in arg for arg in args):
        fail("TLS verification disabled")
    policy = None
    if args[:1] == ["--policy"]:
        policy, args = args[1], args[2:]
    command = args[0]
    if command == "--version":
        print("skopeo version 1.16.1")
    elif command == "login":
        authfile, host = args[args.index("--authfile") + 1], args[-1]
        if password is None or password.strip() != state["token"]:
            fail("Error: authentication required")
        state["login_dir_mode"] = oct(os.stat(os.path.dirname(authfile)).st_mode & 0o777)
        with open(authfile, "w") as handle:
            json.dump({"auths": {host: {"auth": base64.b64encode(("AWS:" + state["token"]).encode()).decode()}}}, handle)
        save()
        print("Login Succeeded!")
    elif command == "inspect":
        name, tag, digest = split(args[-1])
        if ".dkr.ecr." in name:
            host, repository = name.split("/", 1)
            if not authorized("--authfile", host):
                fail("unauthorized")
            for image_digest, image in state["repositories"].get(repository, {}).get("images", {}).items():
                if (tag and tag in image["tags"]) or image_digest == digest:
                    if image.get("raw") is None:
                        fail("manifest unknown")
                    sys.stdout.write(image["raw"])
                    sys.exit(0)
            fail("manifest unknown")
        if "--no-creds" not in args:
            fail("credentials sent upstream")
        upstream = state["upstream"][name]
        raw = upstream["tags"].get(tag) if tag else upstream["digests"].get(digest)
        if raw is None:
            fail("manifest unknown")
        sys.stdout.write(raw)
    elif command == "copy":
        source, target = args[-2], args[-1]
        name, source_tag, digest = split(source)
        rules = json.load(open(policy)) if policy else {}
        if rules.get("default") != [{"type": "reject"}] or name not in rules.get("transports", {}).get("docker", {}):
            fail("Source image rejected: Running image is rejected by policy")
        if "--src-no-creds" not in args:
            fail("credentials sent upstream")
        target_name, tag, _ = split(target)
        host, repository = target_name.split("/", 1)
        if not authorized("--dest-authfile", host):
            fail("unauthorized")
        if digest is None:
            fail("source must be pinned by digest")
        raw = state["upstream"][name]["digests"][digest]
        index = json.loads(raw)
        images = state["repositories"][repository]["images"]
        mode = os.environ.get("FAKE_COPY_MODE", "")
        children = []
        if "--all" in args and mode != "single":
            children = [(child["digest"], child["mediaType"]) for child in index["manifests"]]
            if mode == "drop_child":
                children = children[:1]
            stored = raw if "--preserve-digests" in args and mode != "convert" else json.dumps(index, indent=2)
            tagged = (sha(stored), index["mediaType"], stored)
        else:
            amd64 = next(c for c in index["manifests"] if c["platform"]["architecture"] == "amd64")
            stored = json.dumps({"schemaVersion": 2, "mediaType": amd64["mediaType"], "layers": []})
            tagged = (sha(stored), amd64["mediaType"], stored)
        for child_digest, media_type in children:
            images.setdefault(child_digest, {"tags": [], "media_type": media_type, "raw": None})
        if os.environ.get("FAKE_FAIL_COPY") == repository:
            save()
            fail("Error writing manifest: connection reset by peer")
        for image_digest, image in images.items():
            if tag in image["tags"] and image_digest != tagged[0]:
                fail("ImageTagAlreadyExistsException: the repository is immutable")
        image = images.setdefault(tagged[0], {"tags": [], "media_type": tagged[1], "raw": tagged[2]})
        if tag not in image["tags"]:
            image["tags"].append(tag)
        save()
        print("Writing manifest list to image destination")
    else:
        fail("unsupported skopeo command")
    """)
FAKE_AWS = textwrap.dedent("""\
    import json, os, sys
    args = sys.argv[1:]
    with open(os.environ["FAKE_LOG"], "a") as log:
        log.write(json.dumps({"tool": "aws", "argv": args}) + "\\n")
    state = json.load(open(os.environ["FAKE_STATE"]))
    def fail(message, code=254):
        sys.stderr.write(message + "\\n")
        sys.exit(code)
    def value(flag):
        return args[args.index(flag) + 1]
    if args == ["--version"]:
        print("aws-cli/2.35.0 Python/3.13")
        sys.exit(0)
    if value("--region") != "ca-central-1":
        fail("wrong Region")
    key = tuple(args[:2])
    repositories = state["repositories"]
    if key == ("sts", "get-caller-identity"):
        print(json.dumps({"Account": state["caller_account"], "Arn": "arn:aws:iam::" + state["caller_account"]
                          + ":user/operator", "UserId": "operator"}))
    elif key == ("ecr", "get-login-password"):
        print(state["token"])
    elif key == ("ecr", "describe-repositories"):
        start = args.index("--repository-names") + 1
        names = []
        for arg in args[start:]:
            if arg.startswith("--"):
                break
            names.append(arg)
        missing = [name for name in names if name not in repositories]
        if missing:
            fail("An error occurred (RepositoryNotFoundException) when calling the DescribeRepositories operation: "
                 "The repository with name '" + missing[0] + "' does not exist")
        print(json.dumps({"repositories": [repositories[name]["meta"] for name in names]}))
    elif key == ("ecr", "describe-images"):
        name = value("--repository-name")
        if name not in repositories:
            fail("An error occurred (RepositoryNotFoundException) when calling the DescribeImages operation")
        details = []
        for digest, image in repositories[name]["images"].items():
            detail = {"registryId": state["registry_account"], "repositoryName": name, "imageDigest": digest,
                      "imageManifestMediaType": image["media_type"]}
            if image["tags"]:
                detail["imageTags"] = image["tags"]
            details.append(detail)
        print(json.dumps({"imageDetails": details}))
    else:
        fail("unsupported aws command", 2)
    """)
FAKE_TERRAFORM = textwrap.dedent("""\
    import json, os, sys
    with open(os.environ["FAKE_LOG"], "a") as log:
        log.write(json.dumps({"tool": "terraform", "argv": sys.argv[1:]}) + "\\n")
    print(json.dumps(json.load(open(os.environ["FAKE_STATE"]))["terraform_output"]))
    """)


def digest_of(raw):
    return "sha256:" + hashlib.sha256(raw if isinstance(raw, bytes) else raw.encode()).hexdigest()


class Fixture:
    """Fake tools, a synthetic registry root and a state file in a temporary directory."""

    def __init__(self, case):
        self.base = Path(tempfile.mkdtemp(prefix="mirror-images-test-"))
        case.addCleanup(lambda: __import__("shutil").rmtree(self.base, ignore_errors=True))
        bin_dir = self.base / "bin"
        bin_dir.mkdir()
        for name, source in (("skopeo", FAKE_SKOPEO), ("aws", FAKE_AWS), ("terraform", FAKE_TERRAFORM)):
            path = bin_dir / name
            path.write_text("#!" + sys.executable + "\n" + source)
            path.chmod(0o755)
        self.skopeo, self.aws, self.terraform = (str(bin_dir / name) for name in ("skopeo", "aws", "terraform"))
        self.tmp = self.base / "tmp"
        self.tmp.mkdir()
        self.services = self.base / "services"
        (self.services / "registry").mkdir(parents=True)
        self.write_local(PROJECT, ACCOUNT)
        self.log = self.base / "calls.jsonl"
        self.state_file = self.base / "state.json"
        upstream = {}
        for item in LOCK["images"]:
            raw = RAW[item["purpose"]].decode()
            upstream[item["source"]] = {"tags": {item["tag"]: raw}, "digests": {item["digest"]: raw}}
        repositories, output = {}, {}
        for purpose in PURPOSES:
            name = f"{PROJECT}-dev-ecr-{purpose}"
            repositories[name] = {"meta": {
                "repositoryArn": f"arn:aws:ecr:ca-central-1:{ACCOUNT}:repository/{name}", "registryId": ACCOUNT,
                "repositoryName": name, "repositoryUri": f"{HOST}/{name}", "imageTagMutability": "IMMUTABLE",
                "imageScanningConfiguration": {"scanOnPush": False},
                "encryptionConfiguration": {"encryptionType": "AES256"}}, "images": {}}
            output[purpose] = {"name": name, "arn": f"arn:aws:ecr:ca-central-1:{ACCOUNT}:repository/{name}",
                               "repository_url": f"{HOST}/{name}"}
        self.save({"token": TOKEN, "caller_account": ACCOUNT, "registry_account": ACCOUNT, "upstream": upstream,
                   "repositories": repositories, "terraform_output": {"host": HOST, "repositories": output}})
        self.env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": str(self.base),
                    "TMPDIR": str(self.tmp), "FAKE_STATE": str(self.state_file), "FAKE_LOG": str(self.log)}

    def write_local(self, project, account):
        (self.services / "registry/local.auto.tfvars").write_text(
            f'project        = "{project}"\naws_account_id = "{account}"\n')

    def state(self):
        return json.loads(self.state_file.read_text())

    def save(self, state):
        self.state_file.write_text(json.dumps(state))

    def edit(self, change):
        state = self.state()
        change(state)
        self.save(state)

    def calls(self, tool=None):
        if not self.log.exists():
            return []
        entries = [json.loads(line) for line in self.log.read_text().splitlines()]
        return [entry for entry in entries if tool is None or entry["tool"] == tool]

    def copies(self):
        return [entry["argv"] for entry in self.calls("skopeo") if "copy" in entry["argv"]]

    def images(self, purpose):
        return self.state()["repositories"][f"{PROJECT}-dev-ecr-{purpose}"]["images"]

    def clear_log(self):
        if self.log.exists():
            self.log.unlink()


def run(module, fixture, confirm=PROJECT, project=PROJECT, account=ACCOUNT, purposes=None, env=None):
    output = []
    environment = dict(fixture.env, **(env or {}))

    def answer(_prompt):
        if confirm is None:
            raise AssertionError("confirmation requested although nothing needs copying")
        return confirm
    try:
        code = module.mirror(project, account, purposes, aws=fixture.aws, skopeo=fixture.skopeo,
                             terraform=fixture.terraform, services=fixture.services, env=environment, confirm=answer,
                             out_fn=output.append)
        message = ""
    except (module.MirrorError, preflight.PreflightError) as error:
        code, message = 2, str(error)
    return code, "\n".join(output), message


def assert_complete(case, fixture, purposes=PURPOSES):
    """Each repository holds exactly the locked index, tagged, and every child manifest with its media type."""
    for item in LOCK["images"]:
        if item["purpose"] not in purposes:
            continue
        images = fixture.images(item["purpose"])
        expected = {child["digest"]: child["media_type"] for child in item["platforms"].values()}
        expected[item["digest"]] = item["media_type"]
        case.assertEqual({digest: image["media_type"] for digest, image in images.items()}, expected)
        case.assertEqual(images[item["digest"]]["tags"], [item["tag"]])
        case.assertEqual(images[item["digest"]]["raw"].encode(), RAW[item["purpose"]])


def assert_no_writes(case, fixture):
    case.assertEqual(fixture.copies(), [])
    for purpose in PURPOSES:
        case.assertEqual(fixture.images(purpose), {})


# ---------- scenarios (shared by the tests and the mutation checks) ----------

def scenario_mirror_all(case, module):
    fixture = Fixture(case)
    code, output, message = run(module, fixture)
    case.assertEqual((code, message), (0, ""))
    copies = fixture.copies()
    case.assertEqual(len(copies), 3)
    for item, argv in zip(sorted(LOCK["images"], key=lambda i: i["purpose"]), copies):
        case.assertEqual(argv[0], "--policy")
        case.assertEqual(argv[2:3] + argv[3:8], ["copy"] + EXPECTED_COPY_OPTIONS)
        case.assertEqual(argv[8], "--dest-authfile")
        case.assertEqual(argv[10:], [f"docker://{item['source']}@{item['digest']}",
                                     f"docker://{HOST}/{PROJECT}-dev-ecr-{item['purpose']}:{item['tag']}"])
    assert_complete(case, fixture)
    aws_commands = {tuple(entry["argv"][:2]) if entry["argv"] != ["--version"] else ("--version",)
                    for entry in fixture.calls("aws")}
    case.assertTrue(aws_commands <= ALLOWED_AWS, aws_commands)
    for entry in fixture.calls("skopeo"):
        joined = " ".join(entry["argv"])
        case.assertNotIn("tls-verify=false", joined)
        case.assertNotIn("insecure-policy", joined)
        if entry["argv"][:1] == ["inspect"]:
            case.assertIn("--tls-verify=true", entry["argv"])
    case.assertEqual(output.count("copied and verified"), 3)
    case.assertIn("Mirrored 3 image(s)", output)
    case.assertEqual(os.listdir(fixture.tmp), [])


def scenario_idempotent(case, module):
    fixture = Fixture(case)
    case.assertEqual(run(module, fixture)[0], 0)
    fixture.clear_log()
    code, output, message = run(module, fixture, confirm=None)
    case.assertEqual((code, message), (0, ""))
    case.assertEqual(fixture.copies(), [])
    case.assertEqual(output.count("already present, verified"), 3)
    assert_complete(case, fixture)


def scenario_upstream_moved(case, module):
    fixture = Fixture(case)

    def move(state):
        source = next(i["source"] for i in LOCK["images"] if i["purpose"] == "istio-proxy")
        state["upstream"][source]["tags"]["1.32.0"] += "\n"
    fixture.edit(move)
    code, _output, message = run(module, fixture)
    case.assertEqual(code, 2)
    case.assertTrue(message.startswith("upstream_tag_moved:istio-proxy now sha256:"), message)
    assert_no_writes(case, fixture)


def scenario_tag_conflict(case, module):
    fixture = Fixture(case)
    other = "sha256:" + "0" * 64
    fixture.edit(lambda s: s["repositories"][f"{PROJECT}-dev-ecr-lbc"]["images"].update(
        {other: {"tags": ["v3.6.2"], "media_type": LOCK["images"][2]["media_type"], "raw": "{}"}}))
    code, _output, message = run(module, fixture)
    case.assertEqual(code, 2)
    case.assertTrue(message.startswith("destination_tag_conflict:lbc"), message)
    case.assertEqual(fixture.copies(), [])
    case.assertEqual(list(fixture.images("lbc")), [other])


def scenario_unexpected_image(case, module):
    fixture = Fixture(case)
    stray = "sha256:" + "1" * 64
    fixture.edit(lambda s: s["repositories"][f"{PROJECT}-dev-ecr-istio-pilot"]["images"].update(
        {stray: {"tags": [], "media_type": "application/vnd.oci.image.manifest.v1+json", "raw": None}}))
    code, _output, message = run(module, fixture)
    case.assertEqual(code, 2)
    case.assertEqual(message, "destination_unexpected_image:istio-pilot")
    case.assertEqual(fixture.copies(), [])
    case.assertEqual(list(fixture.images("istio-pilot")), [stray])


def scenario_partial_failure(case, module):
    fixture = Fixture(case)
    code, output, message = run(module, fixture, env={"FAKE_FAIL_COPY": f"{PROJECT}-dev-ecr-istio-proxy"})
    case.assertEqual((code, message), (2, "copy_failed:istio-proxy"))
    case.assertIn("Not mirrored: istio-proxy failed; verified: istio-pilot; not attempted: lbc. Nothing was deleted.",
                  output)
    assert_complete(case, fixture, ["istio-pilot"])
    proxy = fixture.images("istio-proxy")
    case.assertTrue(proxy and all(not image["tags"] for image in proxy.values()))
    case.assertEqual(fixture.images("lbc"), {})
    case.assertEqual(os.listdir(fixture.tmp), [])
    fixture.clear_log()
    code, output, message = run(module, fixture)
    case.assertEqual((code, message), (0, ""))
    case.assertEqual(len(fixture.copies()), 2)
    case.assertIn("istio-pilot: already present, verified", output)
    assert_complete(case, fixture)


def scenario_converted(case, module):
    fixture = Fixture(case)
    code, output, message = run(module, fixture, env={"FAKE_COPY_MODE": "convert"})
    case.assertEqual(code, 2)
    case.assertTrue(message.startswith("destination_digest_mismatch:istio-pilot holds sha256:"), message)
    case.assertIn("Not mirrored: istio-pilot failed", output)
    case.assertNotIn("Mirrored", output.replace("Not mirrored", ""))


def scenario_single_platform(case, module):
    fixture = Fixture(case)
    code, _output, message = run(module, fixture, env={"FAKE_COPY_MODE": "single"})
    case.assertEqual(code, 2)
    case.assertTrue(message.startswith("destination_digest_mismatch:istio-pilot"), message)


def scenario_children_missing(case, module):
    fixture = Fixture(case)
    code, _output, message = run(module, fixture, env={"FAKE_COPY_MODE": "drop_child"})
    case.assertEqual((code, message), (2, "destination_children_missing:istio-pilot"))


def scenario_caller_account_mismatch(case, module):
    fixture = Fixture(case)
    fixture.edit(lambda s: s.update(caller_account="777788889999"))
    case.assertEqual(run(module, fixture)[::2], (2, "caller_account_mismatch"))
    case.assertEqual(fixture.calls("skopeo")[1:], [])  # only --version: no login, inspect or copy
    assert_no_writes(case, fixture)


def scenario_registry_values_mismatch(case, module):
    fixture = Fixture(case)
    fixture.write_local("other", ACCOUNT)
    code, _output, message = run(module, fixture)
    case.assertEqual(code, 2)
    case.assertTrue(message.startswith("registry_root_values_mismatch"), message)
    assert_no_writes(case, fixture)


def scenario_registry_output_mismatch(case, module):
    fixture = Fixture(case)
    fixture.edit(lambda s: s["terraform_output"]["repositories"].update(
        {"busybox": {"name": f"{PROJECT}-dev-ecr-busybox", "arn": "x", "repository_url": "y"}}))
    case.assertEqual(run(module, fixture)[::2], (2, "registry_output_mismatch:repositories"))
    other = Fixture(case)
    other.edit(lambda s: s["terraform_output"].update(host="777788889999.dkr.ecr.ca-central-1.amazonaws.com"))
    case.assertEqual(run(module, other)[::2], (2, "registry_output_mismatch:host"))
    assert_no_writes(case, fixture)


def scenario_region_env(case, module):
    fixture = Fixture(case)
    for key in ("AWS_REGION", "AWS_DEFAULT_REGION"):
        code, output, _message = run(module, fixture, env={key: "us-east-1"})
        case.assertEqual(code, 1)
        case.assertTrue(output.startswith("Refused (live_refused_region:" + key + ")"), output)
    case.assertEqual(fixture.calls(), [])


def scenario_repository_identity(case, module):
    fixture = Fixture(case)
    name = f"{PROJECT}-dev-ecr-lbc"
    fixture.edit(lambda s: s["repositories"][name]["meta"].update(
        repositoryArn=f"arn:aws:ecr:us-east-1:{ACCOUNT}:repository/{name}"))
    case.assertEqual(run(module, fixture)[::2], (2, "repository_identity_mismatch:" + name))
    assert_no_writes(case, fixture)


def scenario_repository_missing(case, module):
    fixture = Fixture(case)
    fixture.edit(lambda s: s["repositories"].pop(f"{PROJECT}-dev-ecr-lbc"))
    code, _output, message = run(module, fixture)
    case.assertEqual(code, 2)
    case.assertTrue(message.startswith("repository_missing"), message)
    case.assertFalse([e for e in fixture.calls("aws") if "create-repository" in e["argv"]])
    case.assertEqual(fixture.calls("skopeo")[1:], [])
    case.assertNotIn(f"{PROJECT}-dev-ecr-lbc", fixture.state()["repositories"])


def scenario_repository_mutable(case, module):
    fixture = Fixture(case)
    name = f"{PROJECT}-dev-ecr-lbc"
    fixture.edit(lambda s: s["repositories"][name]["meta"].update(imageTagMutability="MUTABLE"))
    case.assertEqual(run(module, fixture)[::2], (2, "repository_not_immutable:" + name))
    assert_no_writes(case, fixture)


def scenario_token_hidden(case, module):
    for env in ({}, {"FAKE_FAIL_COPY": f"{PROJECT}-dev-ecr-lbc"}):
        fixture = Fixture(case)
        code, output, message = run(module, fixture, env=env)
        case.assertEqual(code, 2 if env else 0, message)
        everything = json.dumps(fixture.calls()) + output + message
        case.assertNotIn(TOKEN, everything)
        logins = [e for e in fixture.calls("skopeo") if e["argv"][:1] == ["login"]]
        case.assertEqual(len(logins), 1)
        case.assertIn("--password-stdin", logins[0]["argv"])
        case.assertEqual(logins[0]["password_sha256"], hashlib.sha256(TOKEN.encode()).hexdigest())
        case.assertEqual(fixture.state()["login_dir_mode"], "0o700")
        authfiles = {e["argv"][e["argv"].index(flag) + 1] for e in fixture.calls("skopeo")
                     for flag in ("--authfile", "--dest-authfile") if flag in e["argv"]}
        case.assertEqual(len(authfiles), 1)
        authfile = Path(authfiles.pop())
        case.assertTrue(fixture.tmp in authfile.parents)
        case.assertFalse(authfile.exists())
        case.assertEqual(os.listdir(fixture.tmp), [])


def scenario_refused_in_ci(case, module):
    fixture = Fixture(case)
    for extra in ({"GITHUB_ACTIONS": "true"}, {"CI": "true"}, {"CLAUDE_CODE_REMOTE": "true"},
                  {"CODEX_SANDBOX": "seatbelt"}, {"AWS_ACCESS_KEY_ID": "proxy-injected"},
                  {"AWS_ENDPOINT_URL": "https://localhost:4566"}):
        code, output, _message = run(module, fixture, env=extra)
        case.assertEqual(code, 1, extra)
        case.assertTrue(output.startswith("Refused (live_refused_"), output)
    case.assertEqual(fixture.calls(), [])


def scenario_placeholders(case, module):
    fixture = Fixture(case)
    for project, account, code_name in (("project", ACCOUNT, "placeholder_project"),
                                        ("myproj", ACCOUNT, "placeholder_project"),
                                        (PROJECT, "123456789012", "placeholder_account_id"),
                                        (PROJECT, "000000000000", "placeholder_account_id"),
                                        ("Acme", ACCOUNT, "invalid_project"),
                                        ("awsproj", ACCOUNT, "invalid_project"),
                                        (PROJECT, "12345", "invalid_account_id")):
        code, output, _message = run(module, fixture, project=project, account=account)
        case.assertEqual((code, output.split(")")[0]), (1, "Refused (" + code_name), (project, account))
    case.assertEqual(fixture.calls(), [])


def scenario_wrong_confirmation(case, module):
    fixture = Fixture(case)
    code, output, _message = run(module, fixture, confirm="yes")
    case.assertEqual(code, 1)
    case.assertIn("Not confirmed; nothing was copied.", output)
    assert_no_writes(case, fixture)
    case.assertEqual(os.listdir(fixture.tmp), [])


def scenario_guards(case, module):
    for arguments in (["skopeo", "copy", "--dest-tls-verify=false"], ["skopeo", "--insecure-policy", "copy"],
                      ["skopeo", "copy", "--dest-compress-format=zstd"], ["skopeo", "login", "--password=x"],
                      ["skopeo", "copy", "--format", "oci"], ["skopeo", "copy", "--remove-signatures"]):
        with case.assertRaises(module.MirrorError) as raised:
            module.check_arguments(arguments)
        case.assertEqual(str(raised.exception), "unsafe_argument")
    for command in (["ecr", "create-repository"], ["ecr", "batch-delete-image"], ["ecr", "put-image"],
                    ["ecr", "delete-repository"], ["ecr", "put-image-tag-mutability"]):
        with case.assertRaises(module.MirrorError) as raised:
            module.run_aws("/nonexistent/aws", command, {})
        case.assertEqual(str(raised.exception), "aws_command_not_allowed:" + " ".join(command))


def scenario_workdir_in_repository(case, module):
    fixture = Fixture(case)
    before = sorted(p.name for p in preflight.REPOSITORY.iterdir())
    code, _output, message = run(module, fixture, env={"TMPDIR": str(preflight.REPOSITORY)})
    case.assertEqual(code, 2)
    case.assertTrue(message.startswith("workdir_inside_repository"), message)
    case.assertEqual(sorted(p.name for p in preflight.REPOSITORY.iterdir()), before)
    case.assertFalse([e for e in fixture.calls("skopeo") if e["argv"][:1] == ["login"]])


class PlanTests(unittest.TestCase):
    def offline(self, argv):
        def blocked(*_args, **_kwargs):
            raise AssertionError("plan must not start a process or open a connection")
        buffer = io.StringIO()
        patches = [(subprocess, "run"), (subprocess, "Popen"), (os, "system"), (socket, "socket"),
                   (socket, "create_connection")]
        saved = [(owner, name, getattr(owner, name)) for owner, name in patches]
        try:
            for owner, name in patches:
                setattr(owner, name, blocked)
            with contextlib.redirect_stdout(buffer):
                code = mirror_images.main(argv)
        finally:
            for owner, name, value in saved:
                setattr(owner, name, value)
        return code, buffer.getvalue()

    def test_default_is_an_offline_plan_of_the_three_locked_images(self):
        code, output = self.offline([])
        self.assertEqual(code, 0)
        for item in LOCK["images"]:
            self.assertIn(f"- {item['purpose']}: docker://{item['source']}@{item['digest']} (the tag {item['tag']} must "
                          f"still resolve to it) -> docker://<account_id>.dkr.ecr.ca-central-1.amazonaws.com/"
                          f"<project>-dev-ecr-{item['purpose']}:{item['tag']}", output)
            for platform, child in item["platforms"].items():
                self.assertIn(f"{platform} {child['digest']}", output)
        self.assertEqual(output.count("copy " + " ".join(EXPECTED_COPY_OPTIONS)), 3)
        self.assertIn("it was not run", output)

    def test_plan_with_values_and_one_purpose(self):
        code, output = self.offline(["plan", "--project", PROJECT, "--account-id", ACCOUNT, "--purpose", "lbc"])
        self.assertEqual(code, 0)
        self.assertIn(f"docker://{HOST}/{PROJECT}-dev-ecr-lbc:v3.6.2", output)
        self.assertNotIn("istio", output)

    def test_unapproved_purpose_is_refused(self):
        with self.assertRaises(mirror_images.MirrorError) as raised:
            mirror_images.lock_plan(["busybox"])
        self.assertEqual(str(raised.exception), "unapproved_purpose:busybox")
        with contextlib.redirect_stderr(io.StringIO()) as error:
            self.assertEqual(mirror_images.main(["plan", "--purpose", "busybox"]), 2)
        self.assertIn("Stopped: unapproved_purpose:busybox", error.getvalue())

    def test_tampered_lock_or_manifest_is_refused(self):
        def read_with(purpose, data):
            return lambda path: data if path.endswith(purpose + ".index.json") \
                else (preflight.REPOSITORY / path).read_bytes()
        single = json.dumps({"schemaVersion": 2, "mediaType": "application/vnd.docker.distribution.manifest.v2+json",
                             "config": {}, "layers": []}).encode()

        def single_platform(lock):
            lock["images"][2]["digest"] = digest_of(single)
            lock["images"][2]["media_type"] = "application/vnd.docker.distribution.manifest.v2+json"
        cases = {
            "extra_image": (lambda lock: lock["images"].append(dict(lock["images"][0], purpose="busybox")), None),
            "changed_digest": (lambda lock: lock["images"][0].update(digest="sha256:" + "2" * 64), None),
            "dropped_platform": (lambda lock: lock["images"][1]["platforms"].pop("linux/arm64"), None),
            "changed_child": (lambda lock: lock["images"][1]["platforms"]["linux/amd64"].update(
                digest="sha256:" + "3" * 64), None),
            "tag_reference": (lambda lock: lock["registry"].update(reference="tag"), None),
            "other_source": (lambda lock: lock["images"][2].update(source="docker.io/library/busybox"), None),
            "manifest_edited": (lambda lock: None, read_with("istio-pilot", RAW["istio-pilot"] + b" ")),
            "single_platform_manifest": (single_platform, read_with("lbc", single)),
        }
        for name, (edit, read) in cases.items():
            lock = copy.deepcopy(LOCK)
            edit(lock)
            with self.subTest(name), self.assertRaises(mirror_images.MirrorError) as raised:
                mirror_images.lock_plan(None, lock, read)
            self.assertTrue(str(raised.exception).startswith("image_lock_invalid:"), name)


class MirrorTests(unittest.TestCase):
    def test_copies_the_three_images_by_digest_and_verifies_them(self):
        scenario_mirror_all(self, mirror_images)

    def test_rerun_skips_verified_images(self):
        scenario_idempotent(self, mirror_images)

    def test_moved_upstream_tag_stops_before_any_copy(self):
        scenario_upstream_moved(self, mirror_images)

    def test_immutable_tag_on_another_digest_stops(self):
        scenario_tag_conflict(self, mirror_images)

    def test_unexpected_destination_image_stops(self):
        scenario_unexpected_image(self, mirror_images)

    def test_partial_failure_is_not_success_and_a_rerun_recovers(self):
        scenario_partial_failure(self, mirror_images)

    def test_converted_manifest_is_not_success(self):
        scenario_converted(self, mirror_images)

    def test_single_platform_copy_is_not_success(self):
        scenario_single_platform(self, mirror_images)

    def test_missing_child_manifest_is_not_success(self):
        scenario_children_missing(self, mirror_images)

    def test_caller_account_mismatch_stops(self):
        scenario_caller_account_mismatch(self, mirror_images)

    def test_registry_root_values_and_output_must_match(self):
        scenario_registry_values_mismatch(self, mirror_images)
        scenario_registry_output_mismatch(self, mirror_images)

    def test_other_region_is_refused(self):
        scenario_region_env(self, mirror_images)

    def test_repositories_must_exist_and_match(self):
        scenario_repository_missing(self, mirror_images)
        scenario_repository_identity(self, mirror_images)
        scenario_repository_mutable(self, mirror_images)

    def test_token_never_exposed_and_authfile_deleted(self):
        scenario_token_hidden(self, mirror_images)

    def test_refused_in_ci_and_cloud_sessions_before_any_tool(self):
        scenario_refused_in_ci(self, mirror_images)

    def test_placeholder_and_invalid_values_are_refused(self):
        scenario_placeholders(self, mirror_images)

    def test_wrong_confirmation_copies_nothing(self):
        scenario_wrong_confirmation(self, mirror_images)

    def test_unsafe_arguments_and_write_commands_are_refused(self):
        scenario_guards(self, mirror_images)

    def test_work_directory_inside_repository_is_refused(self):
        scenario_workdir_in_repository(self, mirror_images)


class CommandLineTests(unittest.TestCase):
    def test_cli_refuses_mirror_in_ci_and_cloud_sessions(self):
        script = HERE / "mirror_images.py"
        for extra in ({"GITHUB_ACTIONS": "true"}, {"CLAUDE_CODE_REMOTE": "true"}):
            env = dict({"PATH": os.environ.get("PATH", ""), "PYTHONDONTWRITEBYTECODE": "1"}, **extra)
            process = subprocess.run([sys.executable, str(script), "mirror", "--project", PROJECT, "--account-id",
                                      ACCOUNT, "--aws", "/nonexistent/aws", "--skopeo", "/nonexistent/skopeo"],
                                     capture_output=True, text=True, env=env, check=False)
            self.assertEqual(process.returncode, 1)
            self.assertTrue(process.stdout.startswith("Refused (live_refused_"), process.stdout)

    def test_cli_plan_succeeds_without_tools(self):
        process = subprocess.run([sys.executable, str(HERE / "mirror_images.py")], capture_output=True, text=True,
                                 env={"PATH": "/nonexistent", "PYTHONDONTWRITEBYTECODE": "1"}, check=False)
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertEqual(process.stdout.count("--all --preserve-digests"), 3)


# Each mutation removes or weakens one guard in mirror_images.py; the scenario must fail.
MUTATIONS = [
    ("copy_without_all", '"--all", ', '', scenario_mirror_all),
    ("copy_without_preserve_digests", '"--preserve-digests", ', '', scenario_mirror_all),
    ("upstream_tag_unchecked", "    if observed != image.raw:\n", "    if False:\n", scenario_upstream_moved),
    ("tag_conflict_unchecked", "        if image.tag in tags and digest != image.digest:\n", "        if False:\n",
     scenario_tag_conflict),
    ("unexpected_image_allowed", "        if digest not in allowed:\n", "        if False:\n", scenario_unexpected_image),
    ("stored_bytes_unchecked", "    if stored != image.raw:\n", "    if False:\n", scenario_converted),
    ("children_unchecked", "    if present != set(expected):\n", "    if False:\n", scenario_children_missing),
    ("automation_not_refused", "    refusal = live_refusal(project, account_id, environment)\n",
     "    refusal = None\n", scenario_refused_in_ci),
    ("caller_account_unchecked", '    if identity.get("Account") != account_id:\n', "    if False:\n",
     scenario_caller_account_mismatch),
    ("registry_output_unchecked", '    if output.get("repositories") != expected_repositories:\n', "    if False:\n",
     scenario_registry_output_mismatch),
    ("registry_values_unchecked", '    if preflight.local_value(root, "project") != project or',
     '    if False and preflight.local_value(root, "project") != project or', scenario_registry_values_mismatch),
    ("mutable_repository_allowed", 'repository.get("imageTagMutability") != "IMMUTABLE"', "False",
     scenario_repository_mutable),
    ("repository_arn_unchecked", '!= f"arn:aws:ecr:{REGION}:{account_id}:repository/{name}"',
     '!= repository.get("repositoryArn")', scenario_repository_identity),
    ("token_in_arguments", '"--password-stdin",', '"--password", token,', scenario_token_hidden),
    ("authfile_kept", "    shutil.rmtree(workdir, ignore_errors=True)\n    if Path(workdir).exists():",
     "    pass\n    if Path(workdir).exists():", scenario_token_hidden),
    ("unsafe_arguments_allowed", "        if FORBIDDEN_ARGUMENT.search(str(argument)):\n", "        if False:\n",
     scenario_guards),
    ("write_commands_allowed", "    if tuple(arguments[:2]) not in READ_ONLY_AWS:\n", "    if False:\n",
     scenario_guards),
    ("confirmation_skipped", "            if answer.strip() != project:\n", "            if False:\n",
     scenario_wrong_confirmation),
    ("present_images_copied_again", '                if states[image.purpose] == "present":\n',
     "                if False:\n", scenario_idempotent),
    ("other_region_allowed", "        if env.get(key) and env[key] != REGION:\n", "        if False:\n",
     scenario_region_env),
    ("placeholder_account_allowed", "    if account_id in preflight.PLACEHOLDER_ACCOUNTS:\n", "    if False:\n",
     scenario_placeholders),
    ("workdir_in_repository_allowed", "    if base == preflight.REPOSITORY or preflight.REPOSITORY in base.parents:\n",
     "    if False:\n", scenario_workdir_in_repository),
]


def mutant(old, new):
    source = (HERE / "mirror_images.py").read_text()
    if source.count(old) != 1:
        raise AssertionError("mutation target not found exactly once: " + old.strip())
    spec = importlib.util.spec_from_loader("mirror_images_mutant", loader=None)
    module = importlib.util.module_from_spec(spec)
    module.__file__ = str(HERE / "mirror_images.py")
    exec(compile(source.replace(old, new), module.__file__, "exec"), module.__dict__)  # noqa: S102
    return module


class MutationTests(unittest.TestCase):
    def test_each_guard_mutation_is_detected(self):
        self.assertEqual(len(MUTATIONS), 22)
        undetected = []
        for name, old, new, scenario in MUTATIONS:
            module = mutant(old, new)
            try:
                with contextlib.redirect_stdout(io.StringIO()):
                    scenario(self, module)
            except AssertionError:
                continue
            undetected.append(name)
        self.assertEqual(undetected, [])


if __name__ == "__main__":
    unittest.main()
