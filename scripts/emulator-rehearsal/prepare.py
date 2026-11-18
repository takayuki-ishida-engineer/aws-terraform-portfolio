"""Step 2 host preparation (network on, never starts the emulator).

Owner-authorized local runs only, refused in CI. Downloads the pinned official
artifacts from scripts/emulator-verification/versions.json, verifies SHA-256 and
publisher signatures with the repository's own verifier, extracts them into
STEP2_BASE (no system-wide install) and records the public STS/EC2 probe
addresses for the isolation proof. Prints only non-secret gate rows.
"""
import hashlib, json, os, shutil, socket, subprocess, sys
from pathlib import Path

sys.dont_write_bytecode = True
REPO = Path(__file__).resolve().parents[2]
VERIFY = REPO / 'scripts/emulator-verification'
sys.path.insert(0, str(VERIFY))
import prepare as repo_prepare  # noqa: E402  (download + verify_signature)

BASE = Path(os.environ.get('STEP2_BASE', '')).resolve() if os.environ.get('STEP2_BASE') else None
ART = BASE / 'artifacts' if BASE else None
TOOLS = BASE / 'tools' if BASE else None


def gate(name, status='PASS', **extra):
    print(json.dumps({'gate': name, 'status': status, **extra}), flush=True)


def main():
    if os.environ.get('CI') or os.environ.get('GITHUB_ACTIONS'):
        gate('local-only', 'BLOCKED')
        return 1
    if BASE is None or REPO in BASE.parents or BASE == REPO:
        gate('step2-base-outside-repository', 'BLOCKED')
        return 1
    lock = json.loads((VERIFY / 'versions.json').read_text())
    for d in (ART, TOOLS):
        if d.exists():
            shutil.rmtree(d)
        d.mkdir(mode=0o700, parents=True)
    hashes = {}
    for name, filename in [('emulator', 'emulator.deb'), ('awscli', 'awscli.zip'), ('terraform', 'terraform.zip')]:
        row = lock[name]
        path = ART / filename
        repo_prepare.download(row['url'], path)
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != row['sha256']:
            gate(name + '-sha256', 'BLOCKED')
            return 1
        hashes[name] = digest
        gate(name + '-sha256', sha256=digest)
        if name != 'terraform':
            sig = ART / (name + '.sig')
            repo_prepare.download(row['url'] + '.sig', sig)
            key = ART / (name + '.asc')
            if name == 'emulator':
                repo_prepare.download(row['key_url'], key)
            else:
                shutil.copyfile(VERIFY / 'awscli-publisher.asc', key)
            repo_prepare.verify_signature(path, sig, key, row['fingerprint'])
            gate(name + '-gpg', fingerprint=row['fingerprint'])
    version = subprocess.run(['dpkg-deb', '--field', str(ART / 'emulator.deb'), 'Version'],
                             capture_output=True, text=True, check=True).stdout.strip()
    if version != lock['emulator']['package_version']:
        gate('emulator-package-version', 'BLOCKED')
        return 1
    gate('emulator-package-version', version=version)
    # Private extraction instead of apt install; the reviewed postinst only adds a symlink.
    subprocess.run(['dpkg-deb', '-x', str(ART / 'emulator.deb'), str(TOOLS / 'emulator')], check=True)
    subprocess.run(['unzip', '-q', str(ART / 'awscli.zip'), '-d', str(ART / 'awscli-src')], check=True)
    subprocess.run([str(ART / 'awscli-src/aws/install'), '--install-dir', str(TOOLS / 'aws-cli'),
                    '--bin-dir', str(TOOLS / 'bin')], check=True, capture_output=True)
    subprocess.run(['unzip', '-q', str(ART / 'terraform.zip'), 'terraform', '-d', str(TOOLS / 'bin')], check=True)
    shutil.rmtree(ART / 'awscli-src')
    probes = {}
    for service in ('sts', 'ec2'):
        probes[service] = sorted({a[4][0] for a in socket.getaddrinfo(service + '.ca-central-1.amazonaws.com', 443,
                                                                        socket.AF_INET, socket.SOCK_STREAM)})
    manifest = {'versions': lock, 'artifact_sha256': hashes, 'probes': probes,
                'host_netns': os.readlink('/proc/self/ns/net')}
    (BASE / 'prepared.json').write_text(json.dumps(manifest, indent=2))
    gate('verified-preparation', probes=probes)
    return 0


if __name__ == '__main__':
    sys.exit(main())
