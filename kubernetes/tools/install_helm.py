#!/usr/bin/env python3
"""Download a pinned Helm archive, verify locked and published SHA256, extract one executable."""
import argparse,hashlib,json,subprocess,tarfile,tempfile,io
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--destination',type=Path,required=True);a=p.parse_args()
root=Path(__file__).resolve().parents[2];lock=json.loads((root/'kubernetes/dependencies.lock.json').read_text())['helm']
def get(url):return subprocess.check_output(['curl','--fail','--silent','--show-error','--location','--proto','=https','--tlsv1.2','--max-time','120',url])
archive=get(lock['url']);published=get(lock['checksum_url']).decode().split()[0]
if hashlib.sha256(archive).hexdigest()!=lock['sha256'] or published!=lock['sha256']:raise SystemExit('Helm archive published/locked checksum mismatch')
with tarfile.open(fileobj=io.BytesIO(archive)) as t:binary=t.extractfile('linux-amd64/helm').read()
if hashlib.sha256(binary).hexdigest()!=lock['binary_sha256']:raise SystemExit('Helm executable checksum mismatch')
a.destination.parent.mkdir(parents=True,exist_ok=True);a.destination.write_bytes(binary);a.destination.chmod(0o755)
print('Verified Helm',lock['version'],lock['sha256'])
