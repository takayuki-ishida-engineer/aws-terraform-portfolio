"""Step 2 host preparation (network on, never starts the emulator).

Allowed in two contexts only: an operator's local run, or the
``aws-emulator-rehearsal.yml`` workflow on main (a push to main or the Owner's
manual dispatch). Any other CI is refused. In Actions it first checks the run
(main, the Owner, a public repository, the checked-out SHA), a standard
GitHub-hosted runner with enough CPU, memory and disk, and a local Docker daemon.
Per the Owner decision of 2026-11-20 there is no per-run billing attestation; the
Owner's standing configuration is a public repository on GitHub Free with $0
Budgets and usage blocking.

Downloads the artifacts pinned in scripts/emulator-verification/versions.json,
verifies SHA-256 and publisher signatures with the repository's own verifier,
extracts them into STEP2_BASE (no system-wide install), builds the locked AWS
provider mirror unless STEP2_PROVIDER_MIRROR is given, and records the public
STS/EC2 probe addresses for the isolation proof. With --docker-context it also
assembles the image context (tools, mirror, the tested network root and vpc
module, the harness and run.json). Prints only non-secret gate rows.
"""
import argparse, hashlib, json, os, shutil, socket, subprocess, sys, tempfile
from datetime import datetime, timezone
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
VERIFY = REPO / 'scripts/emulator-verification'
sys.path.insert(0, str(VERIFY))
import prepare as repo_prepare  # noqa: E402  (download, verify_signature)

WORKFLOW = '.github/workflows/aws-emulator-rehearsal.yml'
SCENARIOS = ('all', 'network', 'network-full', 'tfstate', 'api')
SOURCE_PATHS = ('infra/services/dev/ca-central-1', 'infra/modules')
HARNESS = ('rehearse.py',)
SHARED = ('gates.py', 'runtime_contracts.py')


def gate(name, status='PASS', **extra):
    print(json.dumps({'gate': name, 'status': status, **extra}), flush=True)


def execution_context(env):
    """'github-actions' only for the rehearsal workflow on main (push or dispatch), else 'local' or None."""
    if env.get('GITHUB_ACTIONS') == 'true':
        expected = env.get('GITHUB_REPOSITORY', '') + '/' + WORKFLOW + '@refs/heads/main'
        if (env.get('GITHUB_EVENT_NAME') in ('push', 'workflow_dispatch') and env.get('GITHUB_REF') == 'refs/heads/main'
                and env.get('GITHUB_REPOSITORY') and env.get('GITHUB_WORKFLOW_REF') == expected):
            return 'github-actions'
        return None
    if env.get('CI'):
        return None
    return 'local'


def actions_preflight(env, head):
    """Run, runner and Docker checks for Actions; returns the first failing gate name or None."""
    checks = [
        ('run-identity', env.get('ACTOR') == env.get('OWNER') and env.get('TRIGGERING_ACTOR') == env.get('OWNER')
         and env.get('VISIBILITY') == 'public' and env.get('GITHUB_REF') == 'refs/heads/main'
         and env.get('GITHUB_RUN_ATTEMPT') == '1' and env.get('TARGET_SHA') == env.get('GITHUB_SHA') == head),
        ('runner-eligibility', env.get('RUNNER_KIND') == 'github-hosted' and env.get('RUNNER_OS') == 'Linux'
         and env.get('RUNNER_ARCH') == 'X64'),
        ('runner-cpu', (os.cpu_count() or 0) >= 2),
        ('runner-disk', shutil.disk_usage(env.get('RUNNER_TEMP', '/')).free >= 10 * 1024 ** 3),
        ('runner-memory', memory_available() >= 8 * 1024 ** 3),
        ('docker-local-endpoint', env.get('DOCKER_HOST') in (None, 'unix:///var/run/docker.sock')
         and env.get('DOCKER_CONTEXT') in (None, 'default') and docker_is_local()),
    ]
    for name, ok in checks:
        if not ok:
            return name
        gate(name)
    return None


def memory_available():
    rows = Path('/proc/meminfo').read_text().splitlines()
    return int(next(r.split()[1] for r in rows if r.startswith('MemAvailable:'))) * 1024


def docker_is_local():
    try:
        endpoint = json.loads(command(['docker', 'context', 'inspect', '--format', '{{json .Endpoints.docker.Host}}']))
        command(['docker', 'info'])
    except (subprocess.CalledProcessError, ValueError, OSError):
        return False
    return endpoint == 'unix:///var/run/docker.sock'


def run_identity(env, context):
    if context == 'github-actions':
        run_id = env['GITHUB_RUN_ID'] + '-' + env['GITHUB_RUN_ATTEMPT']
        execution = {'kind': 'github-actions', 'repository': env['GITHUB_REPOSITORY'], 'workflow_ref': env['GITHUB_WORKFLOW_REF'],
                     'event': env['GITHUB_EVENT_NAME'],
                     'run_id': env['GITHUB_RUN_ID'], 'run_attempt': env['GITHUB_RUN_ATTEMPT'],
                     'run_url': env.get('GITHUB_SERVER_URL', 'https://github.com') + '/' + env['GITHUB_REPOSITORY'] + '/actions/runs/' + env['GITHUB_RUN_ID'],
                     'runner': 'ubuntu-24.04 (GitHub-hosted)'}
        return run_id, env['TARGET_SHA'], execution
    return datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S') + '-1', env.get('TESTED_SHA', ''), {'kind': 'local'}


def command(args, **kwargs):
    return subprocess.run(args, check=True, capture_output=True, text=True, **kwargs).stdout


def build_mirror(base, terraform):
    """Locked AWS provider mirror from the committed network lock, without changing the lock."""
    config = base / 'mirror-config'
    config.mkdir()
    (config / 'main.tf').write_text('terraform {\n  required_providers {\n    aws = { source = "hashicorp/aws", version = "= 6.72.0" }\n  }\n}\n')
    shutil.copyfile(REPO / 'infra/services/dev/ca-central-1/network/.terraform.lock.hcl', config / '.terraform.lock.hcl')
    lock = (config / '.terraform.lock.hcl').read_bytes()
    home, tmp = base / 'mirror-home', base / 'mirror-tmp'
    home.mkdir(); tmp.mkdir()
    env = {'PATH': os.environ['PATH'], 'HOME': str(home), 'TMPDIR': str(tmp), 'TF_INPUT': 'false', 'TF_IN_AUTOMATION': 'true',
           'CHECKPOINT_DISABLE': '1', 'AWS_CONFIG_FILE': '/dev/null', 'AWS_SHARED_CREDENTIALS_FILE': '/dev/null'}
    for name in ('HTTPS_PROXY', 'https_proxy', 'SSL_CERT_FILE', 'NO_PROXY', 'no_proxy'):
        if name in os.environ:
            env[name] = os.environ[name]
    command([str(terraform), 'init', '-backend=false', '-input=false', '-lockfile=readonly', '-no-color'], cwd=config, env=env)
    command([str(terraform), 'providers', 'mirror', '-platform=linux_amd64', str(base / 'mirror')], cwd=config, env=env)
    if (config / '.terraform.lock.hcl').read_bytes() != lock:
        raise RuntimeError('provider-lock-changed')
    for path in (config, home, tmp):
        shutil.rmtree(path)
    return base / 'mirror', hashlib.sha256(lock).hexdigest()


def docker_context(base, mirror, sha, run_id, scenario, execution):
    context = base / 'context'
    context.mkdir()
    shutil.copytree(base / 'tools/emulator', context / 'emulator', symlinks=True)
    shutil.copyfile(base / 'artifacts/awscli.zip', context / 'awscli.zip')
    shutil.copyfile(base / 'tools/bin/terraform', context / 'terraform')
    shutil.copytree(mirror, context / 'mirror')
    (context / 'source').mkdir()
    archive = subprocess.run(['git', '-C', str(REPO), 'archive', sha, *SOURCE_PATHS], check=True, capture_output=True).stdout
    subprocess.run(['tar', '-x', '-C', str(context / 'source')], input=archive, check=True)
    (context / 'harness').mkdir()
    for name in HARNESS:
        shutil.copyfile(HERE / name, context / 'harness' / name)
    for name in SHARED:
        shutil.copyfile(VERIFY / name, context / 'harness' / name)
    shutil.copyfile(base / 'prepared.json', context / 'prepared.json')
    harness_sha = hashlib.sha256((HERE / 'rehearse.py').read_bytes()).hexdigest()
    (context / 'run.json').write_text(json.dumps({'sha': sha, 'run_id': run_id, 'scenario': scenario,
                                                  'harness_sha256': harness_sha, 'execution': execution}))
    shutil.copyfile(HERE / 'Dockerfile', context / 'Dockerfile')
    rows = []
    for path in sorted(p for p in context.rglob('*') if p.is_file() and not p.is_symlink() and p.name != 'Dockerfile'):
        rows.append(hashlib.sha256(path.read_bytes()).hexdigest() + '  ' + str(path.relative_to(context)) + '\n')
    (context / 'context.sha256').write_text(''.join(rows))
    return harness_sha


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--docker-context', action='store_true')
    args = parser.parse_args(argv)
    env = dict(os.environ)
    context = execution_context(env)
    if context is None:
        gate('allowed-context', 'BLOCKED')
        return 1
    if context == 'github-actions':
        head = command(['git', '-C', str(REPO), 'rev-parse', 'HEAD']).strip()
        failed = actions_preflight(env, head)
        if failed:
            gate(failed, 'BLOCKED')
            return 1
    scenario = env.get('SCENARIO', 'all')
    base = Path(env['STEP2_BASE']).resolve() if env.get('STEP2_BASE') else None
    if scenario not in SCENARIOS:
        gate('scenario', 'BLOCKED')
        return 1
    if base is None or base == REPO or REPO in base.parents:
        gate('step2-base-outside-repository', 'BLOCKED')
        return 1
    run_id, sha, execution = run_identity(env, context)
    if args.docker_context:
        try:
            if len(sha) != 40 or command(['git', '-C', str(REPO), 'rev-parse', sha + '^{commit}']).strip() != sha:
                raise ValueError
            command(['git', '-C', str(REPO), 'merge-base', '--is-ancestor', sha, 'HEAD'])
        except (ValueError, subprocess.CalledProcessError):
            gate('tested-sha', 'BLOCKED')
            return 1
    lock = json.loads((VERIFY / 'versions.json').read_text())
    base.mkdir(mode=0o700, parents=True, exist_ok=True)
    art, tools = base / 'artifacts', base / 'tools'
    for d in (art, tools, base / 'context', base / 'mirror'):
        if d.exists():
            shutil.rmtree(d)
    art.mkdir(mode=0o700); tools.mkdir(mode=0o700)
    hashes = {}
    try:
        for name, filename in [('emulator', 'emulator.deb'), ('awscli', 'awscli.zip'), ('terraform', 'terraform.zip')]:
            row = lock[name]
            path = art / filename
            repo_prepare.download(row['url'], path)
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            if digest != row['sha256']:
                gate(name + '-sha256', 'BLOCKED')
                return 1
            hashes[name] = digest
            gate(name + '-sha256', sha256=digest)
            if name != 'terraform':
                sig = art / (name + '.sig')
                repo_prepare.download(row['url'] + '.sig', sig)
                key = art / (name + '.asc')
                if name == 'emulator':
                    repo_prepare.download(row['key_url'], key)
                else:
                    shutil.copyfile(VERIFY / 'awscli-publisher.asc', key)
                repo_prepare.verify_signature(path, sig, key, row['fingerprint'])
                gate(name + '-gpg', fingerprint=row['fingerprint'])
        version = command(['dpkg-deb', '--field', str(art / 'emulator.deb'), 'Version']).strip()
        if version != lock['emulator']['package_version']:
            gate('emulator-package-version', 'BLOCKED')
            return 1
        gate('emulator-package-version', version=version)
        # Private extraction instead of apt install; the reviewed postinst only adds a symlink.
        subprocess.run(['dpkg-deb', '-x', str(art / 'emulator.deb'), str(tools / 'emulator')], check=True)
        subprocess.run(['unzip', '-q', str(art / 'terraform.zip'), 'terraform', '-d', str(tools / 'bin')], check=True)
        terraform = tools / 'bin/terraform'
        if json.loads(command([str(terraform), 'version', '-json'], env=dict(os.environ, CHECKPOINT_DISABLE='1')))['terraform_version'] != lock['terraform']['version']:
            gate('terraform-version', 'BLOCKED')
            return 1
        if env.get('STEP2_PROVIDER_MIRROR'):
            mirror, lock_sha = Path(env['STEP2_PROVIDER_MIRROR']).resolve(), None
        else:
            mirror, lock_sha = build_mirror(base, terraform)
        gate('provider-offline-mirror', provider=lock['provider'], **({'lock_sha256': lock_sha} if lock_sha else {}))
        probes = {}
        for service in ('sts', 'ec2'):
            probes[service] = sorted({a[4][0] for a in socket.getaddrinfo(service + '.ca-central-1.amazonaws.com', 443,
                                                                            socket.AF_INET, socket.SOCK_STREAM)})
        manifest = {'versions': lock, 'artifact_sha256': hashes, 'probes': probes, 'host_netns': os.readlink('/proc/self/ns/net')}
        (base / 'prepared.json').write_text(json.dumps(manifest, indent=2))
        extra = {}
        if args.docker_context:
            extra['harness_sha256'] = docker_context(base, mirror, sha, run_id, scenario, execution)
            extra.update(run_id=run_id, sha=sha, scenario=scenario)
    except (repo_prepare.SignatureBlocked, repo_prepare.Blocked, subprocess.CalledProcessError, OSError, RuntimeError, KeyError) as error:
        gate('preparation', 'BLOCKED', stage=type(error).__name__)
        return 1
    gate('verified-preparation', probes=probes, **extra)
    return 0


if __name__ == '__main__':
    sys.exit(main())
