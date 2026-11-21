#!/usr/bin/env python3
"""Mirror the pinned runtime images into the private ECR repositories (finding F18, B3).

``kubernetes/images.lock.json`` is the only image inventory: three upstream image
indexes, each pinned by the SHA-256 of its raw manifest, with every platform. The
``registry`` root (B1) creates one private repository per purpose; the renderer (B2)
pulls ``<account>.dkr.ecr.ca-central-1.amazonaws.com/<project>-dev-ecr-<purpose>@<digest>``.

- ``plan`` (the default) is fully offline. It re-proves the lock with the Kubernetes
  validator's own check (raw manifest bytes, digests, every platform and child
  manifest) and prints what ``mirror`` would copy. It runs no external command and
  makes no network, registry or AWS call.
- ``mirror`` runs only on the operator's workstation. It is refused in CI, in Claude
  Code or Codex cloud sessions, with the cloud session's placeholder credentials and
  with an AWS endpoint override. Before anything is copied it checks:
  - the project and account: not placeholders, equal to the registry root's
    ``local.auto.tfvars``, to its applied ``registry`` output, to the caller identity
    and to the repositories' registry ID, all in ca-central-1;
  - that the three repositories already exist (this script never creates one) and are
    private ``IMMUTABLE`` AES256 repositories with the expected ARN and URL;
  - that each upstream tag still resolves to the locked index, byte for byte;
  - what each repository already holds: the locked tag on the locked index is skipped,
    the tag on any other digest stops the run, and any image that is not the locked
    index or one of its child manifests stops the run (nothing is deleted or overwritten).
  It then copies by the locked digest, never by the tag, with
  ``skopeo copy --all --preserve-digests``, and verifies every repository afterwards:
  the raw index bytes read back from ECR must equal the committed manifest (so its
  SHA-256, media type, platforms and child digests equal the lock), and ECR must list
  exactly the index, tagged, and every child manifest with its media type.

The ECR token goes from ``aws ecr get-login-password`` through stdin into ``skopeo
login``, into an authfile in a private temporary directory outside the repository,
which is deleted when the run ends, also on failure. The token never appears in an
argument, in output, in Git or in Terraform. TLS verification stays on, and a
temporary skopeo policy accepts only the three locked upstream repositories. A
failed run leaves whatever was already copied; it is never reported as success, and a
re-run skips what is verified (README, "Image mirror").
"""
import argparse
import dataclasses
import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import handoff  # noqa: E402
import preflight  # noqa: E402

sys.path.insert(0, str(preflight.REPOSITORY / "kubernetes/tools"))
from validate import verify_image_lock  # noqa: E402  (vendored, integrity-checked libraries; offline)

REGION = preflight.REGION
LOCK_FILE = preflight.REPOSITORY / "kubernetes/images.lock.json"
# The DEV roots' project rule (kubernetes/tools/common.py PROJECT).
PROJECT = re.compile(r"[a-z]([a-z0-9-]{0,8}[a-z0-9])?")
ACCOUNT = re.compile(r"[0-9]{12}")
# Every platform of the index, byte-identical manifests, anonymous upstream, TLS verified.
COPY_OPTIONS = ("--all", "--preserve-digests", "--src-no-creds", "--src-tls-verify=true", "--dest-tls-verify=true")
READ_ONLY_AWS = {("sts", "get-caller-identity"), ("ecr", "describe-repositories"), ("ecr", "describe-images")}
# Options that would weaken TLS, the signature policy or byte identity; refused in every skopeo call.
FORBIDDEN_ARGUMENT = re.compile(r"tls-verify=false|insecure-policy|compress|--format|remove-signatures|--password=",
                                re.IGNORECASE)
LONG_TOKEN = re.compile(r"[A-Za-z0-9+/=_-]{40,}")
SECRET_WORD = re.compile(r"password|authorization|token|secret|credential", re.IGNORECASE)


class MirrorError(Exception):
    """A check failed; the message is a fixed code, never a credential."""


@dataclasses.dataclass(frozen=True)
class Image:
    purpose: str
    source: str
    tag: str
    digest: str
    media_type: str
    platforms: dict
    raw: bytes

    def expected(self):
        """Every manifest the repository must hold: the index and its child manifests, by digest."""
        children = {child["digest"]: child["media_type"] for child in self.platforms.values()}
        return dict(children, **{self.digest: self.media_type})


@dataclasses.dataclass(frozen=True)
class Plan:
    images: tuple
    host_template: str
    repository_template: str
    all_purposes: tuple

    def host(self, account_id):
        return self.host_template.replace("${account_id}", account_id)

    def repository(self, project, image):
        return self.repository_template.replace("${project}", project).replace("${purpose}", image.purpose)


def lock_plan(purposes=None, lock=None, read=None):
    """Re-prove the lock offline with the Kubernetes validator and return the images to mirror."""
    lock = json.loads(LOCK_FILE.read_text(encoding="utf-8")) if lock is None else lock
    read = read or (lambda path: (preflight.REPOSITORY / path).read_bytes())
    try:
        digests = verify_image_lock(lock, read)
    except (ValueError, KeyError, TypeError, AttributeError, UnicodeDecodeError) as error:
        raise MirrorError("image_lock_invalid:" + str(error)[:120]) from None
    items = {item["purpose"]: item for item in lock["images"]}
    for purpose in purposes or ():
        if purpose not in items:
            raise MirrorError("unapproved_purpose:" + str(purpose)[:40])
    images = []
    for purpose in sorted(set(purposes or items)):
        item = items[purpose]
        raw = read(item["manifest_file"])
        if "sha256:" + hashlib.sha256(raw).hexdigest() != digests[purpose]:
            raise MirrorError("image_lock_invalid:manifest_changed:" + purpose)
        images.append(Image(purpose, item["source"], item["tag"], item["digest"], item["media_type"],
                            json.loads(json.dumps(item["platforms"])), raw))
    return Plan(tuple(images), lock["registry"]["host"], lock["registry"]["repository"], tuple(sorted(items)))


def destination(plan, image, project, account_id):
    return "docker://" + plan.host(account_id) + "/" + plan.repository(project, image) + ":" + image.tag


def copy_arguments(skopeo, policy, authfile, image, target):
    return [skopeo, "--policy", str(policy), "copy", *COPY_OPTIONS, "--dest-authfile", str(authfile),
            "docker://" + image.source + "@" + image.digest, target]


def show_plan(plan, project=None, account_id=None, out_fn=print):
    project, account_id = project or "<project>", account_id or "<account_id>"
    out_fn(f"Image lock verified: {len(plan.images)} image(s), each an index pinned by the SHA-256 of its raw manifest "
           "with every platform (offline: no network, registry or AWS access).")
    for image in plan.images:
        platforms = ", ".join(f"{key} {value['digest']}" for key, value in sorted(image.platforms.items()))
        out_fn(f"- {image.purpose}: docker://{image.source}@{image.digest} "
               f"(the tag {image.tag} must still resolve to it) -> {destination(plan, image, project, account_id)}")
        out_fn(f"  {image.media_type}; platforms: {platforms}")
        out_fn("  " + " ".join(copy_arguments("skopeo", "<temporary policy>", "<temporary authfile>", image,
                                                 destination(plan, image, project, account_id))))
    out_fn("mirror copies these from the operator's workstation only; it was not run.")


def redact(text):
    """At most 20 short lines, none that could carry a token."""
    lines = []
    for line in str(text).splitlines()[:20]:
        lines.append("[redacted]" if LONG_TOKEN.search(line) or SECRET_WORD.search(line) else line[:200])
    return lines


def check_arguments(arguments):
    for argument in arguments:
        if FORBIDDEN_ARGUMENT.search(str(argument)):
            raise MirrorError("unsafe_argument")


def execute(arguments, env, stdin=None, binary=False):
    check_arguments(arguments)
    try:
        return subprocess.run(arguments, input=stdin, capture_output=True, text=not binary, check=False, env=env,
                              stdin=None if stdin is not None else subprocess.DEVNULL)
    except OSError:
        raise MirrorError("tool_unavailable:" + Path(arguments[0]).name) from None


def run_aws(aws, arguments, env):
    if tuple(arguments[:2]) not in READ_ONLY_AWS:
        raise MirrorError("aws_command_not_allowed:" + " ".join(arguments[:2]))
    process = execute([aws] + arguments + ["--region", REGION, "--output", "json"], env)
    if process.returncode != 0:
        if "RepositoryNotFoundException" in process.stderr:
            raise MirrorError("repository_missing (apply the registry root first; this script never creates "
                              "repositories)")
        raise MirrorError("aws_failed:" + " ".join(arguments[:2]))
    try:
        return json.loads(process.stdout)
    except ValueError:
        raise MirrorError("aws_output:" + " ".join(arguments[:2])) from None


def live_refusal(project, account_id, env):
    """The refusal code when this process must not copy images, else None."""
    refusal = preflight.automation_refusal(env)
    if refusal:
        return refusal
    for key in ("AWS_REGION", "AWS_DEFAULT_REGION"):
        if env.get(key) and env[key] != REGION:
            return "live_refused_region:" + key
    if not isinstance(project, str) or not PROJECT.fullmatch(project) or re.search("aws|amazon|cognito", project):
        return "invalid_project"
    if project in preflight.PLACEHOLDER_PROJECTS:
        return "placeholder_project"
    if not isinstance(account_id, str) or not ACCOUNT.fullmatch(account_id):
        return "invalid_account_id"
    if account_id in preflight.PLACEHOLDER_ACCOUNTS:
        return "placeholder_account_id"
    return None


def check_registry_root(plan, project, account_id, terraform, services, env):
    """The registry root's local values and applied output must name this project, account and lock."""
    root = Path(services) / "registry"
    if preflight.local_value(root, "project") != project or preflight.local_value(root, "aws_account_id") != account_id:
        raise MirrorError("registry_root_values_mismatch (registry/local.auto.tfvars must name the same project and "
                          "account)")
    output = handoff.terraform_output(terraform, root, "registry", env)
    host = plan.host(account_id)
    expected_repositories = {}
    # Every locked purpose, also when --purpose selects fewer: the registry root holds all of them.
    for purpose in plan.all_purposes:
        name = plan.repository_template.replace("${project}", project).replace("${purpose}", purpose)
        expected_repositories[purpose] = {"name": name, "arn": f"arn:aws:ecr:{REGION}:{account_id}:repository/{name}",
                                          "repository_url": host + "/" + name}
    if sorted(output) != ["host", "repositories"] or output.get("host") != host:
        raise MirrorError("registry_output_mismatch:host")
    if output.get("repositories") != expected_repositories:
        raise MirrorError("registry_output_mismatch:repositories")


def check_repositories(plan, project, account_id, aws, env):
    names = [plan.repository(project, image) for image in plan.images]
    data = run_aws(aws, ["ecr", "describe-repositories", "--registry-id", account_id, "--repository-names", *names], env)
    repositories = {item.get("repositoryName"): item for item in data.get("repositories") or []}
    if sorted(repositories) != sorted(names):
        raise MirrorError("repository_set_mismatch")
    host = plan.host(account_id)
    for name in names:
        repository = repositories[name]
        if repository.get("registryId") != account_id \
                or repository.get("repositoryArn") != f"arn:aws:ecr:{REGION}:{account_id}:repository/{name}" \
                or repository.get("repositoryUri") != host + "/" + name:
            raise MirrorError("repository_identity_mismatch:" + name)
        if repository.get("imageTagMutability") != "IMMUTABLE" or repository.get("imageTagMutabilityExclusionFilters"):
            raise MirrorError("repository_not_immutable:" + name)
        if (repository.get("encryptionConfiguration") or {}).get("encryptionType") != "AES256":
            raise MirrorError("repository_encryption_mismatch:" + name)


def inspect_raw(skopeo, reference, env, authfile=None):
    credentials = ["--no-creds"] if authfile is None else ["--authfile", str(authfile)]
    process = execute([skopeo, "inspect", "--raw", "--tls-verify=true", *credentials, reference], env, binary=True)
    return process.stdout if process.returncode == 0 else None


def check_upstream(skopeo, image, env):
    """The upstream tag must still resolve to the locked index, byte for byte."""
    observed = inspect_raw(skopeo, "docker://" + image.source + ":" + image.tag, env)
    if observed is None:
        raise MirrorError("upstream_unavailable:" + image.purpose)
    if observed != image.raw:
        raise MirrorError("upstream_tag_moved:" + image.purpose + " now sha256:" + hashlib.sha256(observed).hexdigest())


def destination_state(aws, account_id, repository, image, env, strict=False):
    """("present" | "absent", digests held). Stops on a conflicting tag or any unexpected image."""
    data = run_aws(aws, ["ecr", "describe-images", "--registry-id", account_id, "--repository-name", repository], env)
    allowed, held, tagged = image.expected(), set(), False
    for detail in data.get("imageDetails") or []:
        digest, tags = detail.get("imageDigest"), detail.get("imageTags") or []
        if detail.get("registryId") != account_id or detail.get("repositoryName") != repository:
            raise MirrorError("destination_identity_mismatch:" + image.purpose)
        if image.tag in tags and digest != image.digest:
            raise MirrorError("destination_tag_conflict:" + image.purpose + " (the immutable tag holds another digest)")
        if digest not in allowed:
            raise MirrorError("destination_unexpected_image:" + image.purpose)
        if any(tag != image.tag for tag in tags):
            raise MirrorError("destination_unexpected_tag:" + image.purpose)
        media_type = detail.get("imageManifestMediaType")
        if (strict or media_type is not None) and media_type != allowed.get(digest):
            raise MirrorError("destination_media_type_mismatch:" + image.purpose)
        tagged = tagged or image.tag in tags
        held.add(digest)
    return ("present" if tagged else "absent"), held


def verify_destination(plan, image, project, account_id, aws, skopeo, authfile, env):
    """Read the copy back two independent ways: raw bytes from the registry, and the ECR image list."""
    repository = plan.repository(project, image)
    stored = inspect_raw(skopeo, destination(plan, image, project, account_id), env, authfile)
    if stored is None:
        raise MirrorError("destination_manifest_unavailable:" + image.purpose)
    if stored != image.raw:
        raise MirrorError("destination_digest_mismatch:" + image.purpose + " holds sha256:"
                          + hashlib.sha256(stored).hexdigest())
    index = json.loads(stored)
    children = {"/".join([c["platform"]["os"], c["platform"]["architecture"]] + ([c["platform"]["variant"]]
                         if c["platform"].get("variant") else [])): {"digest": c["digest"], "media_type": c["mediaType"]}
                for c in index["manifests"]}
    if index.get("mediaType") != image.media_type or children != image.platforms:
        raise MirrorError("destination_index_mismatch:" + image.purpose)
    state, present = destination_state(aws, account_id, repository, image, env, strict=True)
    expected = image.expected()
    if state != "present":
        raise MirrorError("destination_tag_missing:" + image.purpose)
    if present != set(expected):
        raise MirrorError("destination_children_missing:" + image.purpose)


def login(aws, skopeo, host, workdir, env):
    """ECR token: aws stdout -> skopeo stdin -> a 0600 authfile in the private work directory."""
    process = execute([aws, "ecr", "get-login-password", "--region", REGION], env)
    token = process.stdout.strip() if process.returncode == 0 else ""
    if not token:
        raise MirrorError("ecr_login_failed")
    authfile = Path(workdir) / "auth.json"
    process = execute([skopeo, "login", "--authfile", str(authfile), "--username", "AWS", "--password-stdin",
                       "--tls-verify=true", host], env, stdin=token)
    token = None
    if process.returncode != 0 or not authfile.is_file():
        raise MirrorError("registry_login_failed")
    authfile.chmod(0o600)
    return authfile


def write_policy(plan, workdir):
    """Reject every image except the locked upstream repositories (integrity comes from the pinned digests)."""
    policy = {"default": [{"type": "reject"}],
              "transports": {"docker": {image.source: [{"type": "insecureAcceptAnything"}] for image in plan.images}}}
    path = Path(workdir) / "policy.json"
    path.write_text(json.dumps(policy, indent=2) + "\n", encoding="utf-8")
    path.chmod(0o600)
    return path


def new_workdir(env):
    """A new private directory outside the repository; checked before anything is created."""
    base = Path(env.get("TMPDIR") or tempfile.gettempdir()).resolve()
    if base == preflight.REPOSITORY or preflight.REPOSITORY in base.parents:
        raise MirrorError("workdir_inside_repository (set TMPDIR outside the repository)")
    workdir = Path(tempfile.mkdtemp(prefix="mirror-images-", dir=str(base))).resolve()
    workdir.chmod(0o700)
    return workdir


def remove_workdir(workdir, out_fn):
    shutil.rmtree(workdir, ignore_errors=True)
    if Path(workdir).exists():
        out_fn("Could not delete " + str(workdir) + "; delete it now: it holds an ECR login.")


def raise_on_signal(signum, _frame):
    raise MirrorError("interrupted:signal " + str(signum))


def mirror(project, account_id, purposes=None, aws="aws", skopeo="skopeo", terraform="terraform",
           services=preflight.SERVICES, env=None, confirm=input, out_fn=print, lock=None, read=None):
    environment = dict(os.environ if env is None else env)
    refusal = live_refusal(project, account_id, environment)
    if refusal:
        out_fn("Refused (" + refusal + "): images are mirrored only from the operator's workstation.")
        return 1
    environment["AWS_PAGER"] = ""
    plan = lock_plan(purposes, lock, read)
    for tool, name in ((aws, "aws"), (skopeo, "skopeo")):
        if execute([tool, "--version"], environment).returncode != 0:
            raise MirrorError("tool_unavailable:" + name)
    check_registry_root(plan, project, account_id, terraform, services, environment)
    identity = run_aws(aws, ["sts", "get-caller-identity"], environment)
    if identity.get("Account") != account_id:
        raise MirrorError("caller_account_mismatch")
    check_repositories(plan, project, account_id, aws, environment)
    host = plan.host(account_id)
    previous = {sig: signal.signal(sig, raise_on_signal) for sig in (signal.SIGTERM, signal.SIGHUP)}
    old_umask = os.umask(0o077)
    workdir = new_workdir(environment)
    try:
        authfile = login(aws, skopeo, host, workdir, environment)
        policy = write_policy(plan, workdir)
        for image in plan.images:
            check_upstream(skopeo, image, environment)
        states = {}
        for image in plan.images:
            states[image.purpose], _held = destination_state(aws, account_id, plan.repository(project, image), image,
                                                             environment)
        to_copy = [image for image in plan.images if states[image.purpose] != "present"]
        if to_copy:
            answer = confirm(f"Type the project name ({project}) to copy {len(to_copy)} image(s) into {host}: ")
            if answer.strip() != project:
                out_fn("Not confirmed; nothing was copied.")
                return 1
        verified = []
        for image in plan.images:
            try:
                if states[image.purpose] == "present":
                    verify_destination(plan, image, project, account_id, aws, skopeo, authfile, environment)
                    out_fn(f"{image.purpose}: already present, verified ({image.digest}).")
                else:
                    target = destination(plan, image, project, account_id)
                    process = execute(copy_arguments(skopeo, policy, authfile, image, target), environment)
                    if process.returncode != 0:
                        for line in redact(process.stderr):
                            out_fn("  " + line)
                        raise MirrorError("copy_failed:" + image.purpose)
                    verify_destination(plan, image, project, account_id, aws, skopeo, authfile, environment)
                    out_fn(f"{image.purpose}: copied and verified ({image.digest}, "
                           f"{len(image.platforms)} platforms).")
                verified.append(image.purpose)
            except MirrorError:
                remaining = [i.purpose for i in plan.images if i.purpose not in verified and i is not image]
                out_fn(f"Not mirrored: {image.purpose} failed; verified: {', '.join(verified) or 'none'}; "
                       f"not attempted: {', '.join(remaining) or 'none'}. Nothing was deleted. "
                       "Fix the cause and run mirror again; verified images are skipped.")
                raise
        out_fn(f"Mirrored {len(verified)} image(s) into {host}: every index digest, platform and child manifest "
               "matches kubernetes/images.lock.json.")
        return 0
    finally:
        remove_workdir(workdir, out_fn)
        os.umask(old_umask)
        for sig, handler in previous.items():
            signal.signal(sig, handler)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] not in ("plan", "mirror", "-h", "--help"):
        argv = ["plan"] + argv
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    show = sub.add_parser("plan", help="verify the lock and print the copy plan (default; offline)")
    copy = sub.add_parser("mirror", help="copy and verify the images (operator's workstation only)")
    for command, required in ((show, False), (copy, True)):
        command.add_argument("--project", required=required)
        command.add_argument("--account-id", required=required)
        command.add_argument("--purpose", action="append", help="limit to a locked purpose (repeatable)")
    copy.add_argument("--aws", default="aws")
    copy.add_argument("--skopeo", default="skopeo")
    copy.add_argument("--terraform", default="terraform", help="reads the applied registry root's output")
    args = parser.parse_args(argv)
    try:
        if args.command == "plan":
            show_plan(lock_plan(args.purpose), args.project, args.account_id)
            return 0
        return mirror(args.project, args.account_id, args.purpose, args.aws, args.skopeo, args.terraform)
    except (MirrorError, preflight.PreflightError, OSError, ValueError) as error:
        # MirrorError and PreflightError messages are fixed codes; other errors show only their type.
        message = str(error) if isinstance(error, (MirrorError, preflight.PreflightError)) else type(error).__name__
        print("Stopped: " + message, file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        # The work directory, with the ECR login, is already deleted by mirror's finally block.
        print("Stopped: interrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
