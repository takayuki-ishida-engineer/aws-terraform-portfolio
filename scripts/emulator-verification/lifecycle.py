"""Only the isolated, owner-dispatched container executes this entry point.
All command output and private material stay inside disposable tmpfs. The stdout
protocol is deliberately restricted to nonsecret gate/status pairs.
"""
import configparser,errno,hashlib,ipaddress,json,os,re,shutil,socket,ssl,subprocess,time,urllib.request,urllib.error
from pathlib import Path
from gates import Blocked,require,network_gate,unreachable_gate,identity_gate,tls_gate,plan_gate,state_id,api_owner,evidence_gate,CONTROLS,OPERATIONS,freshness_gate
HERE=Path(__file__).resolve().parent
PRIVATE=Path('/work/private')
ENDPOINT='https://127.0.0.1:9297'

def emit(gate,status,exit_code=None,api=None,resource_id=None):
  row={'gate':gate,'status':status}
  if exit_code is not None:row['exit_code']=exit_code
  if api is not None:row['api']=api
  if resource_id is not None:
    require(re.fullmatch('vpc-[0-9a-f]+',resource_id),'safe-resource-id');row['resource_id']=resource_id
  print(json.dumps(row),flush=True)

def strict_json(s):
  def pairs(rows):
    d={}
    for k,v in rows:
      require(k not in d,'duplicate-json');d[k]=v
    return d
  return json.loads(s,object_pairs_hook=pairs,parse_constant=lambda x:(_ for _ in ()).throw(Blocked('nonfinite-json')))

class Run:
  def __init__(self):
    self.manifest=strict_json((HERE/'run.json').read_text())
    require(re.fullmatch('[0-9a-f]{40}',self.manifest['sha']) and re.fullmatch('[0-9]+-[0-9]+',self.manifest['run_id']),'run-manifest')
    self.run_id=self.manifest['run_id'];self.root=PRIVATE/'root';self.home=PRIVATE/'home'
    self.report={'sha':self.manifest['sha'],'controls':dict.fromkeys(CONTROLS,'NOT_TESTED'),'operations':dict.fromkeys(OPERATIONS,'NOT_TESTED'),'cleanup_complete':False}
    self.env={'PATH':'/usr/local/bin:/usr/bin:/bin','HOME':str(self.home),'CHECKPOINT_DISABLE':'1','TF_IN_AUTOMATION':'true','TF_INPUT':'false','AWS_CONFIG_FILE':'/dev/null','AWS_EC2_METADATA_DISABLED':'true','AWS_DEFAULT_REGION':'ca-central-1','AWS_REGION':'ca-central-1','AWS_PAGER':'','EMULATOR_TELEMETRY':'off','NO_PROXY':'127.0.0.1,localhost'}
    self.emulator=None;self.baseline=None;self.owned_id=None;self.creation_attempted=False
    self.phase='create';self.lifecycle_ok=False;self.current_operation='preflight';self.private_owned=False;self.plans={}
  def mark(self,key,name):
    self.report[key][name]='PASS';emit(('control-' if key=='controls' else '')+name,'PASS',resource_id=self.owned_id if name in ['api_create','api_update','destroy','api_absence'] else None)
  def cmd(self,args,ok=(0,)):
    try:p=subprocess.run(args,cwd=self.root,env=self.env,capture_output=True,text=True,timeout=120)
    except subprocess.TimeoutExpired:raise Blocked('command-timeout')
    if p.returncode not in ok:
      api=re.search(r'operation error [A-Za-z0-9]+: ([A-Za-z0-9]+)',p.stdout+p.stderr)
      unsupported=bool(api and re.search(r'(?:StatusCode: ?501|HTTP ?501)',p.stdout+p.stderr))
      status='PARTIAL-SKIP' if unsupported else 'FAIL'
      if self.current_operation in self.report['operations']:self.report['operations'][self.current_operation]=status
      emit(self.current_operation+'-'+Path(args[0]).name,status,p.returncode,api.group(1) if api else None)
      raise Blocked('command-exit')
    emit(self.current_operation+'-'+Path(args[0]).name,'PASS',p.returncode)
    return p
  def tf(self,*args,ok=(0,)):
    return self.cmd(['terraform',*args],ok)
  def aws(self,service,operation,*args):
    p=self.cmd(['aws','--no-cli-pager','--endpoint-url',ENDPOINT,'--ca-bundle',self.env['AWS_CA_BUNDLE'],'--region','ca-central-1',service,operation,*args,'--output','json'])
    return strict_json(p.stdout) if p.stdout.strip() else {}
  def vpcs(self):
    rows=self.aws('ec2','describe-vpcs')['Vpcs'];d={v['VpcId']:v for v in rows};require(len(d)==len(rows),'duplicate-api-id');return d
  def state(self):
    if not (self.root/'terraform.tfstate').exists():return {'resources':[]}
    return strict_json(self.tf('state','pull').stdout)
  def inventory(self,phase,action,owned=None):
    path=self.root/(action+'.plan')
    args=['plan','-input=false','-no-color','-out='+str(path)]
    if action=='delete':args.append('-destroy')
    self.tf(*args)
    digest=hashlib.sha256(path.read_bytes()).hexdigest()
    plan=strict_json(self.tf('show','-json',str(path)).stdout)
    require(hashlib.sha256(path.read_bytes()).hexdigest()==digest,'plan-changed-during-review')
    plan_gate(plan,action,self.run_id,phase,owned)
    self.plans[str(path)]=digest
    return path
  def apply_plan(self,path):
    require(hashlib.sha256(path.read_bytes()).hexdigest()==self.plans.get(str(path)),'reviewed-plan-hash')
    return self.tf('apply','-input=false','-no-color',str(path))
  def baseline_preserved(self,rows,include_owned):
    expected=set(self.baseline)|({self.owned_id} if include_owned else set())
    require(set(rows)==expected and all(rows[k]==v for k,v in self.baseline.items()),'preexisting-vpcs-changed')
  def absence(self):
    p=self.cmd(['aws','--no-cli-pager','--endpoint-url',ENDPOINT,'--ca-bundle',self.env['AWS_CA_BUNDLE'],'--region','ca-central-1','ec2','describe-vpcs','--vpc-ids',self.owned_id,'--output','json'],ok=(254,255))
    require('InvalidVpcID.NotFound' in p.stderr,'independent-delete-absence')
    self.baseline_preserved(self.vpcs(),False)
  def setup(self):
    freshness_gate(self.manifest['owner_checked_at'])
    require(not PRIVATE.exists() and not any(k.startswith(('AWS_','TF_')) or k in ['GITHUB_TOKEN','GH_TOKEN'] for k in os.environ),'no-host-auth-or-tf-config')
    require(not Path('/var/run/docker.sock').exists() and os.statvfs('/').f_flag & os.ST_RDONLY,'readonly-no-docker-socket')
    status=Path('/proc/self/status').read_text()
    for k,v in [('CapEff','0000000000000000'),('CapBnd','0000000000000000'),('NoNewPrivs','1')]:require(re.search(r'^'+k+r':\s*'+v+r'$',status,re.M),'container-privileges')
    PRIVATE.mkdir(mode=0o700);self.private_owned=True;self.home.mkdir(mode=0o700);self.root.mkdir(mode=0o700)
    links=strict_json(self.cmd(['ip','-j','link']).stdout)
    routes=strict_json(self.cmd(['ip','-j','-4','route','show','table','all']).stdout)+strict_json(self.cmd(['ip','-j','-6','route','show','table','all']).stdout)
    network_gate(self.manifest['host_netns'],os.readlink('/proc/self/ns/net'),links,routes);self.mark('controls','6')
    results={}
    for service,ips in self.manifest['probes'].items():
      results[service]=[]
      require(ips and all(ipaddress.ip_address(x).is_global for x in ips),'public-aws-probe-ips')
      for address in ips:
        with socket.socket(socket.AF_INET,socket.SOCK_STREAM) as sock:
          sock.settimeout(2)
          try:result=sock.connect_ex((address,443))
          except (TimeoutError,socket.timeout):result=errno.ETIMEDOUT
          results[service].append(result)
    unreachable_gate(results);self.mark('controls','7')
    lock=self.manifest['versions'];require(self.manifest['artifacts_verified'] is True,'verified-artifacts')
    version=self.cmd(['aws-emulator','-v']).stdout
    require(re.search(r'\b'+re.escape(lock['emulator']['version'])+r'\b',version),'emulator-version')
    require(lock['awscli']['version'] in self.cmd(['aws','--version']).stdout,'awscli-version')
    require(strict_json(self.tf('version','-json').stdout)['terraform_version']==lock['terraform']['version'],'terraform-version');self.mark('controls','1')
    log=PRIVATE/'emulator.log';err=PRIVATE/'emulator.err'
    with log.open('w') as out,err.open('w') as stderr:
      self.emulator=subprocess.Popen(['aws-emulator','--bind','127.0.0.1','--port','9297','--auth','on','--telemetry','off','--idle-timeout','600'],env=self.env,stdout=out,stderr=stderr)
    startup=None
    for _ in range(120):
      require(self.emulator.poll() is None,'emulator-startup-exit')
      for line in log.read_text().splitlines():
        try:row=strict_json(line)
        except (ValueError,Blocked):continue
        if row.get('message')=='emulator server information':startup=row
      if startup:break
      time.sleep(0.5)
    require(startup is not None and startup['endpoint_url']==ENDPOINT,'loopback-https')
    ca=Path(startup['ca_file']).resolve();expected=self.home/'.aws/emulator/9297'
    require(ca==expected/'ca.pem','generated-ca-location')
    credentials=expected/'emulator_credentials'
    require(credentials.is_file() and credentials.resolve()==credentials and credentials.stat().st_uid==os.getuid(),'generated-private-credentials')
    credentials.chmod(0o600)
    parser=configparser.ConfigParser();parser.read(credentials)
    require(parser.sections()==['default'] and all(parser['default'].get(k) for k in ['aws_access_key_id','aws_secret_access_key']),'generated-credentials')
    self.env.update(AWS_SHARED_CREDENTIALS_FILE=str(credentials),AWS_CA_BUNDLE=str(ca),AWS_PROFILE='default')
    context=ssl.create_default_context(cafile=str(ca))
    tls_gate(context.verify_mode,context.check_hostname)
    with urllib.request.urlopen(ENDPOINT+'/__admin/health',context=context,timeout=5) as response:require(response.status==200 and response.read()==b'ok','verified-health')
    # A default trust store must NOT trust this run's generated private CA.
    try:urllib.request.urlopen(ENDPOINT+'/__admin/health',context=ssl.create_default_context(),timeout=5)
    except urllib.error.URLError as e:require(isinstance(e.reason,ssl.SSLCertVerificationError),'tls-negative-verification')
    else:raise Blocked('system-trust-unexpectedly-accepts-ca')
    # Query routing identifies EC2 even without SigV4. Never accept mere 404 routing failure as proof of auth.
    request=urllib.request.Request(ENDPOINT,data=b'Action=DescribeVpcs&Version=2016-11-15',headers={'Host':'ec2.ca-central-1.amazonaws.com','Content-Type':'application/x-www-form-urlencoded'})
    try:urllib.request.urlopen(request,context=context,timeout=5)
    except urllib.error.HTTPError as e:
      require(e.code==403,'unsigned-request-not-auth-rejected')
    else:raise Blocked('unsigned-api-request-accepted')
    self.mark('controls','2');self.mark('controls','3');self.mark('controls','4');self.mark('controls','5')
    identity_gate(self.aws('sts','get-caller-identity'));self.mark('controls','8')
    require({f.name for f in (HERE/'adapter').iterdir()}=={'main.tf','.terraform.lock.hcl'},'adapter-source-inventory')
    for f in (HERE/'adapter').iterdir():shutil.copyfile(f,self.root/f.name)
    baseline=(self.root/'.terraform.lock.hcl').read_bytes()
    cli=PRIVATE/'terraform.rc';cli.write_text('provider_installation { filesystem_mirror { path = "/opt/verification/mirror" include = ["registry.terraform.io/hashicorp/aws"] } }\n')
    self.env['TF_CLI_CONFIG_FILE']=str(cli)
    self.variables('create');self.tf('init','-input=false','-lockfile=readonly','-no-color');self.tf('validate','-no-color')
    require((self.root/'.terraform.lock.hcl').read_bytes()==baseline,'offline-provider-lock');self.mark('controls','9');self.mark('controls','10')
    self.baseline=self.vpcs()
    require(all(v['CidrBlock']!='10.238.0.0/16' for v in self.baseline.values()),'test-cidr-preexisting')
  def variables(self,phase):
    (self.root/'inputs.auto.tfvars.json').write_text(json.dumps({'ca_file':self.env['AWS_CA_BUNDLE'],'run_id':self.run_id,'phase':phase}))
  def execute(self):
    self.current_operation='plan'
    plan=self.inventory('create','create');self.mark('operations','plan');self.mark('controls','11')
    self.current_operation='create'
    freshness_gate(self.manifest['owner_checked_at'])
    self.creation_attempted=True;self.apply_plan(plan);self.mark('operations','create')
    self.owned_id=state_id(self.state(),self.run_id);require(bool(self.owned_id),'created-id')
    self.current_operation='api_create'
    rows=self.vpcs();self.baseline_preserved(rows,True);api_owner(rows[self.owned_id],self.owned_id,self.run_id,'create');self.mark('operations','api_create');self.mark('controls','12')
    self.current_operation='read'
    self.tf('plan','-refresh-only','-detailed-exitcode','-input=false','-no-color');self.mark('operations','read')
    self.current_operation='update'
    self.variables('updated');plan=self.inventory('updated','update',self.owned_id)
    self.apply_plan(plan);self.phase='updated';self.mark('operations','update')
    self.current_operation='api_update'
    rows=self.vpcs();api_owner(rows[self.owned_id],self.owned_id,self.run_id,'updated');self.baseline_preserved(rows,True);self.mark('operations','api_update')
    self.current_operation='no_op'
    self.tf('plan','-detailed-exitcode','-input=false','-no-color');self.mark('operations','no_op')
    self.destroy();self.lifecycle_ok=True
  def destroy(self):
    rows=self.vpcs();self.baseline_preserved(rows,True)
    api_owner(rows[self.owned_id],self.owned_id,self.run_id,self.phase)
    require(state_id(self.state(),self.run_id)==self.owned_id,'destroy-state-id')
    self.current_operation='destroy_plan'
    plan=self.inventory(self.phase,'delete',self.owned_id);self.mark('operations','destroy_plan')
    self.current_operation='destroy'
    self.apply_plan(plan);self.mark('operations','destroy')
    require(state_id(self.state(),self.run_id) is None,'destroy-state-not-empty');self.mark('operations','state_empty')
    self.current_operation='api_absence'
    self.absence();self.mark('operations','api_absence');self.mark('operations','baseline_preserved');self.mark('controls','13')
  def recover(self):
    if not self.creation_attempted or self.baseline is None:return
    rows=self.vpcs();new=set(rows)-set(self.baseline)
    if not new:
      self.baseline_preserved(rows,False)
      require(state_id(self.state(),self.run_id) is None,'residual-state')
      return
    require(len(new)==1,'ambiguous-residual-resources')
    candidate=next(iter(new));require(candidate not in self.baseline,'never-delete-preexisting')
    tags={t['Key']:t['Value'] for t in rows[candidate].get('Tags',[])}
    phase=tags.get('Phase');require(phase in ['create','updated'],'cleanup-phase')
    api_owner(rows[candidate],candidate,self.run_id,phase)
    found=state_id(self.state(),self.run_id)
    self.owned_id=candidate;self.phase=phase;self.variables(phase)
    if found:
      require(found==candidate,'residual-id-mismatch');self.destroy()
    else:
      # Partial create with no State: API cleanup is NOT Terraform Destroy success.
      self.aws('ec2','delete-vpc','--vpc-id',candidate);self.absence();emit('partial-create-api-cleanup','PASS')
  def finish(self):
    resource_cleanup=True
    if not self.lifecycle_ok:
      try:self.recover()
      except Exception:resource_cleanup=False;emit('resource-cleanup','FAIL')
    if self.emulator:
      try:
        if self.emulator.poll() is None:self.emulator.terminate()
        self.emulator.wait(timeout=15)
      except subprocess.TimeoutExpired:
        resource_cleanup=False
        self.emulator.kill()
        try:self.emulator.wait(timeout=5)
        except Exception:resource_cleanup=False
      except Exception:resource_cleanup=False
    if self.private_owned and PRIVATE.exists():shutil.rmtree(PRIVATE)
    require(not PRIVATE.exists(),'private-material-remains')
    self.mark('operations','material_cleanup')
    self.report['cleanup_complete']=resource_cleanup
    emit('resource-cleanup','PASS' if resource_cleanup else 'FAIL')
    if self.report['cleanup_complete']:self.mark('controls','14')
    for key in ['controls','operations']:
      for name,status in self.report[key].items():
        if status!='PASS':emit(('control-' if key=='controls' else '')+name,status)
    evidence_gate(self.report)
    emit('lifecycle-evidence-complete','PASS')

def main():
  import signal
  def interrupted(signum,frame):raise Blocked('interrupted-run')
  signal.signal(signal.SIGTERM,interrupted)
  os.umask(0o077);run=None;failed=False
  try:
    run=Run();run.setup();run.execute()
  except Exception:
    failed=True;emit('execution','FAIL' if run and run.creation_attempted else 'BLOCKED')
  finally:
    if run:
      try:run.finish()
      except Exception:failed=True;emit('complete-evidence-and-cleanup','FAIL')
    else:failed=True
  return 1 if failed else 0
if __name__=='__main__':raise SystemExit(main())
