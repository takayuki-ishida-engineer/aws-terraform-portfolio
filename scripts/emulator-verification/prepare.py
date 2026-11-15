"""Host-side verified downloads and offline image context. Never starts Emulator."""
import hashlib,json,os,re,shutil,socket,subprocess,tempfile
from contextlib import contextmanager,nullcontext
from pathlib import Path
from gates import Blocked,require,signature_gate,owner_gate
HERE=Path(__file__).resolve().parent
PREPARATION_GATES=frozenset([
  'preparation','owner-confirmation','runner-eligibility','runner-cpu',
  'runner-memory','runner-disk','docker-local-endpoint','workspace-configuration',
  'workspace-preparation','emulator-package-version','terraform-installation',
  'provider-offline-mirror','workspace-finalization','verified-preparation',
  *(name+'-'+step for name in ['emulator','awscli','terraform'] for step in ['download','sha256']),
  *(name+'-'+step for name in ['emulator','awscli'] for step in ['signature-material','gpg-verification','gpg-publisher','gpg-signature']),
])

class PreparationBlocked(Blocked):
  def __init__(self, gate):
    # Expose only an allowlisted name; never format exception or command details.
    self.gate=gate if gate in PREPARATION_GATES else 'preparation'
    super().__init__()

def report(gate, status):
  require(gate in PREPARATION_GATES and status in ['PASS','BLOCKED'],'diagnostic-schema')
  print(json.dumps({'gate':gate,'status':status}),flush=True)

@contextmanager
def stage(gate):
  require(gate in PREPARATION_GATES,'diagnostic-gate')
  try:
    yield
  except PreparationBlocked:
    raise
  except (Exception,KeyboardInterrupt,SystemExit):
    raise PreparationBlocked(gate) from None
  else:
    report(gate,'PASS')

def command(args, **kwargs):
  p=subprocess.run(args,capture_output=True,text=True,**kwargs)
  require(p.returncode==0,'prepare-command-'+Path(args[0]).name)
  return p.stdout

def download(url, path):
  command(['curl','--disable','--fail','--silent','--show-error','--location','--proto','=https','--proto-redir','=https','--tlsv1.2','--max-time','180',url,'--output',str(path)])

def verify_signature(package, signature, key, fingerprint, artifact=None):
  with tempfile.TemporaryDirectory(prefix='publisher-') as d:
    with stage(artifact+'-gpg-publisher') if artifact else nullcontext():
      command(['gpg','--homedir',d,'--batch','--import',str(key)])
      rows=command(['gpg','--homedir',d,'--batch','--with-colons','--fingerprint'])
      require(fingerprint in [l.split(':')[9] for l in rows.splitlines() if l.startswith('fpr:')],'publisher-fingerprint')
    with stage(artifact+'-gpg-signature') if artifact else nullcontext():
      p=subprocess.run(['gpg','--homedir',d,'--batch','--status-fd','1','--verify',str(signature),str(package)],capture_output=True,text=True)
      require(p.returncode==0,'package-signature-exit')
      signature_gate(p.stdout,fingerprint)

def preflight():
  with stage('owner-confirmation'):
    owner_gate(os.environ['ACTOR'],os.environ['OWNER'],os.environ['VISIBILITY'],os.environ['GITHUB_REF'],command(['git','rev-parse','HEAD']).strip(),os.environ['TARGET_SHA'],os.environ['OWNER_BILLING_CONFIRMED']=='true',os.environ['OWNER_CHECKED_AT'],os.environ['GITHUB_RUN_ATTEMPT'],os.environ['TRIGGERING_ACTOR'])
  with stage('runner-eligibility'):
    require(os.environ.get('RUNNER_KIND')=='github-hosted' and os.environ.get('RUNNER_OS')=='Linux' and os.environ.get('RUNNER_ARCH')=='X64','standard-runner')
  with stage('runner-cpu'):
    require(os.cpu_count()>=2,'free-cpu')
  with stage('runner-disk'):
    require(shutil.disk_usage(os.environ['RUNNER_TEMP']).free>=10*1024**3,'free-disk')
  with stage('runner-memory'):
    memory=int(next(l.split()[1] for l in Path('/proc/meminfo').read_text().splitlines() if l.startswith('MemAvailable:')))*1024
    require(memory>=6*1024**3,'free-memory')
  with stage('docker-local-endpoint'):
    require(os.environ.get('DOCKER_HOST') in [None,'unix:///var/run/docker.sock'] and os.environ.get('DOCKER_CONTEXT') in [None,'default'],'no-remote-docker')
    endpoint=json.loads(command(['docker','context','inspect','--format','{{json .Endpoints.docker.Host}}']))
    require(endpoint=='unix:///var/run/docker.sock','local-standard-docker')
    command(['docker','info'])

def main():
  preflight()
  # Parsing belongs inside the protected entry point, not at module import time.
  with stage('workspace-configuration'):
    lock=json.loads((HERE/'versions.json').read_text())
  with stage('workspace-preparation'):
    require({f.name for f in (HERE/'adapter').iterdir()}=={'main.tf'},'source-adapter-inventory')
    root=Path(os.environ['RUNNER_TEMP'])/'emulator-verification'
    require(not root.exists(),'fresh-workspace');root.mkdir(mode=0o700)
    artifacts=root/'artifacts';artifacts.mkdir();shutil.copytree(HERE,root/'verification',ignore=shutil.ignore_patterns('__pycache__','tests'))
  files={}
  for name,filename in [('emulator','emulator.deb'),('awscli','awscli.zip'),('terraform','terraform.zip')]:
    with stage(name+'-download'):
      row=lock[name];p=artifacts/filename;download(row['url'],p)
    with stage(name+'-sha256'):
      require(hashlib.sha256(p.read_bytes()).hexdigest()==row['sha256'],'artifact-sha-'+name);files[filename]=row['sha256']
    if name!='terraform':
      with stage(name+'-signature-material'):
        sig=root/(name+'.sig');download(row['url']+'.sig',sig)
        key=root/(name+'.asc')
        if name=='emulator':download(row['key_url'],key)
        else:shutil.copyfile(HERE/'awscli-publisher.asc',key)
      with stage(name+'-gpg-verification'):
        verify_signature(p,sig,key,row['fingerprint'],artifact=name)
  with stage('emulator-package-version'):
    require(command(['dpkg-deb','--field',str(artifacts/'emulator.deb'),'Version']).strip()==lock['emulator']['package_version'],'package-version')
  with stage('terraform-installation'):
    (artifacts/'artifacts.sha256').write_text(''.join(v+'  '+k+'\n' for k,v in files.items()))
    # Hash-verified Terraform prepares the signature/lock-verified provider mirror.
    command(['unzip','-q',str(artifacts/'terraform.zip'),'terraform','-d',str(root/'tools')])
    tf=root/'tools/terraform';require(json.loads(command([str(tf),'version','-json']))['terraform_version']==lock['terraform']['version'],'terraform-version')
  with stage('provider-offline-mirror'):
    adapter=root/'verification/adapter'
    shutil.copyfile(HERE.parents[1]/'infra/services/dev/ca-central-1/network/.terraform.lock.hcl',adapter/'.terraform.lock.hcl')
    baseline=(adapter/'.terraform.lock.hcl').read_bytes()
    home=root/'host-home';home.mkdir();tmp=root/'host-tmp';tmp.mkdir()
    clean={'PATH':os.environ['PATH'],'HOME':str(home),'TMPDIR':str(tmp),'TF_INPUT':'false','TF_IN_AUTOMATION':'true','CHECKPOINT_DISABLE':'1','AWS_CONFIG_FILE':'/dev/null','AWS_SHARED_CREDENTIALS_FILE':'/dev/null','AWS_EC2_METADATA_DISABLED':'true'}
    command([str(tf),'init','-backend=false','-input=false','-lockfile=readonly','-no-color'],cwd=adapter,env=clean)
    command([str(tf),'providers','mirror','-platform=linux_amd64',str(root/'verification/mirror')],cwd=adapter,env=clean)
    require((adapter/'.terraform.lock.hcl').read_bytes()==baseline,'provider-lock-unchanged')
    shutil.rmtree(adapter/'.terraform')
  with stage('workspace-finalization'):
    probes={}
    for service in ['sts','ec2']:
      probes[service]=sorted({a[4][0] for a in socket.getaddrinfo(service+'.ca-central-1.amazonaws.com',443,socket.AF_INET,socket.SOCK_STREAM)})
    manifest={'sha':os.environ['TARGET_SHA'],'owner_checked_at':os.environ['OWNER_CHECKED_AT'],'run_id':os.environ['GITHUB_RUN_ID']+'-'+os.environ['GITHUB_RUN_ATTEMPT'],'host_netns':os.readlink('/proc/self/ns/net'),'probes':probes,'artifacts_verified':True,'versions':lock}
    (root/'verification/run.json').write_text(json.dumps(manifest))
    shutil.copyfile(HERE/'Dockerfile',root/'Dockerfile')
  print(json.dumps({'gate':'verified-preparation','status':'PASS','sha':manifest['sha'],'emulator':lock['emulator']['version'],'terraform':lock['terraform']['version'],'awscli':lock['awscli']['version'],'provider':lock['provider'],'package_sha256':lock['emulator']['sha256'],'publisher':lock['emulator']['fingerprint'],'awscli_sha256':lock['awscli']['sha256'],'awscli_publisher':lock['awscli']['fingerprint'],'terraform_sha256':lock['terraform']['sha256'],'provider_lock_sha256':hashlib.sha256(baseline).hexdigest(),'billing':'owner-attested-not-api-audited'}),flush=True)

def entrypoint():
  try:
    main()
  except PreparationBlocked as error:
    report(error.gate,'BLOCKED')
    return 1
  except (Exception,KeyboardInterrupt,SystemExit):
    # Unexpected failures are still nonzero, with no traceback or exception text.
    report('preparation','BLOCKED')
    return 1
  return 0

if __name__=='__main__':raise SystemExit(entrypoint())
