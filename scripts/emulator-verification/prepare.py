"""Host-side verified downloads and offline image context. Never starts Emulator."""
import hashlib,json,os,re,shutil,socket,subprocess,tempfile
from pathlib import Path
from gates import require,signature_gate,owner_gate
HERE=Path(__file__).resolve().parent
LOCK=json.loads((HERE/'versions.json').read_text())

def command(args, **kwargs):
  p=subprocess.run(args,capture_output=True,text=True,**kwargs)
  require(p.returncode==0,'prepare-command-'+Path(args[0]).name)
  return p.stdout

def download(url, path):
  command(['curl','--disable','--fail','--silent','--show-error','--location','--proto','=https','--proto-redir','=https','--tlsv1.2','--max-time','180',url,'--output',str(path)])

def verify_signature(package, signature, key, fingerprint):
  with tempfile.TemporaryDirectory(prefix='publisher-') as d:
    command(['gpg','--homedir',d,'--batch','--import',str(key)])
    rows=command(['gpg','--homedir',d,'--batch','--with-colons','--fingerprint'])
    require(fingerprint in [l.split(':')[9] for l in rows.splitlines() if l.startswith('fpr:')],'publisher-fingerprint')
    p=subprocess.run(['gpg','--homedir',d,'--batch','--status-fd','1','--verify',str(signature),str(package)],capture_output=True,text=True)
    require(p.returncode==0,'package-signature-exit')
    signature_gate(p.stdout,fingerprint)

def preflight():
  owner_gate(os.environ['ACTOR'],os.environ['OWNER'],os.environ['VISIBILITY'],os.environ['GITHUB_REF'],command(['git','rev-parse','HEAD']).strip(),os.environ['TARGET_SHA'],os.environ['OWNER_BILLING_CONFIRMED']=='true',os.environ['OWNER_CHECKED_AT'],os.environ['GITHUB_RUN_ATTEMPT'],os.environ['TRIGGERING_ACTOR'])
  require(os.environ.get('RUNNER_KIND')=='github-hosted' and os.environ.get('RUNNER_OS')=='Linux' and os.environ.get('RUNNER_ARCH')=='X64','standard-runner')
  require(os.cpu_count()>=2 and shutil.disk_usage(os.environ['RUNNER_TEMP']).free>=10*1024**3,'free-capacity')
  memory=int(next(l.split()[1] for l in Path('/proc/meminfo').read_text().splitlines() if l.startswith('MemAvailable:')))*1024
  require(memory>=6*1024**3,'free-memory')
  require(os.environ.get('DOCKER_HOST') in [None,'unix:///var/run/docker.sock'] and os.environ.get('DOCKER_CONTEXT') in [None,'default'],'no-remote-docker')
  endpoint=json.loads(command(['docker','context','inspect','--format','{{json .Endpoints.docker.Host}}']))
  require(endpoint=='unix:///var/run/docker.sock','local-standard-docker')
  command(['docker','info'])

def main():
  preflight()
  require({f.name for f in (HERE/'adapter').iterdir()}=={'main.tf'},'source-adapter-inventory')
  root=Path(os.environ['RUNNER_TEMP'])/'emulator-verification'
  require(not root.exists(),'fresh-workspace');root.mkdir(mode=0o700)
  artifacts=root/'artifacts';artifacts.mkdir();shutil.copytree(HERE,root/'verification',ignore=shutil.ignore_patterns('__pycache__','tests'))
  files={}
  for name,filename in [('emulator','emulator.deb'),('awscli','awscli.zip'),('terraform','terraform.zip')]:
    row=LOCK[name];p=artifacts/filename;download(row['url'],p)
    require(hashlib.sha256(p.read_bytes()).hexdigest()==row['sha256'],'artifact-sha-'+name);files[filename]=row['sha256']
    if name!='terraform':
      sig=root/(name+'.sig');download(row['url']+'.sig',sig)
      key=root/(name+'.asc')
      if name=='emulator':download(row['key_url'],key)
      else:shutil.copyfile(HERE/'awscli-publisher.asc',key)
      verify_signature(p,sig,key,row['fingerprint'])
  require(command(['dpkg-deb','--field',str(artifacts/'emulator.deb'),'Version']).strip()==LOCK['emulator']['package_version'],'package-version')
  (artifacts/'artifacts.sha256').write_text(''.join(v+'  '+k+'\n' for k,v in files.items()))
  # Hash-verified Terraform prepares the signature/lock-verified provider mirror.
  command(['unzip','-q',str(artifacts/'terraform.zip'),'terraform','-d',str(root/'tools')])
  tf=root/'tools/terraform';require(json.loads(command([str(tf),'version','-json']))['terraform_version']==LOCK['terraform']['version'],'terraform-version')
  adapter=root/'verification/adapter'
  shutil.copyfile(HERE.parents[1]/'infra/services/dev/ca-central-1/network/.terraform.lock.hcl',adapter/'.terraform.lock.hcl')
  baseline=(adapter/'.terraform.lock.hcl').read_bytes()
  home=root/'host-home';home.mkdir();tmp=root/'host-tmp';tmp.mkdir()
  clean={'PATH':os.environ['PATH'],'HOME':str(home),'TMPDIR':str(tmp),'TF_INPUT':'false','TF_IN_AUTOMATION':'true','CHECKPOINT_DISABLE':'1','AWS_CONFIG_FILE':'/dev/null','AWS_SHARED_CREDENTIALS_FILE':'/dev/null','AWS_EC2_METADATA_DISABLED':'true'}
  command([str(tf),'init','-backend=false','-input=false','-lockfile=readonly','-no-color'],cwd=adapter,env=clean)
  command([str(tf),'providers','mirror','-platform=linux_amd64',str(root/'verification/mirror')],cwd=adapter,env=clean)
  require((adapter/'.terraform.lock.hcl').read_bytes()==baseline,'provider-lock-unchanged')
  shutil.rmtree(adapter/'.terraform')
  probes={}
  for service in ['sts','ec2']:
    probes[service]=sorted({a[4][0] for a in socket.getaddrinfo(service+'.ca-central-1.amazonaws.com',443,socket.AF_INET,socket.SOCK_STREAM)})
  manifest={'sha':os.environ['TARGET_SHA'],'owner_checked_at':os.environ['OWNER_CHECKED_AT'],'run_id':os.environ['GITHUB_RUN_ID']+'-'+os.environ['GITHUB_RUN_ATTEMPT'],'host_netns':os.readlink('/proc/self/ns/net'),'probes':probes,'artifacts_verified':True,'versions':LOCK}
  (root/'verification/run.json').write_text(json.dumps(manifest))
  shutil.copyfile(HERE/'Dockerfile',root/'Dockerfile')
  print(json.dumps({'gate':'verified-preparation','status':'PASS','sha':manifest['sha'],'emulator':LOCK['emulator']['version'],'terraform':LOCK['terraform']['version'],'awscli':LOCK['awscli']['version'],'provider':LOCK['provider'],'package_sha256':LOCK['emulator']['sha256'],'publisher':LOCK['emulator']['fingerprint'],'awscli_sha256':LOCK['awscli']['sha256'],'awscli_publisher':LOCK['awscli']['fingerprint'],'terraform_sha256':LOCK['terraform']['sha256'],'provider_lock_sha256':hashlib.sha256(baseline).hexdigest(),'billing':'owner-attested-not-api-audited'}))
if __name__=='__main__':
  try:main()
  except Exception:
    print('{"gate":"preparation","status":"BLOCKED"}')
    raise SystemExit(1)
