"""Only the isolated, owner-dispatched container executes this entry point.
All command output and private material stay inside disposable tmpfs. The stdout
protocol is deliberately restricted to nonsecret gate/status pairs.
"""
import configparser,errno,hashlib,ipaddress,json,os,re,shutil,socket,ssl,subprocess,time,urllib.request,urllib.error
from pathlib import Path
from gates import require,network_gate,unreachable_gate,identity_gate,tls_gate,plan_gate,state_id,api_owner,evidence_gate,CONTROLS,OPERATIONS,freshness_gate,refresh_gate
HERE=Path(__file__).resolve().parent
PRIVATE=Path('/work/private')
from runtime_contracts import ENDPOINT,DIAGNOSTICS,RuntimeFailure,strict_json,startup_record,generated_file,cli_error_code,unsigned_sts_rejected
API_NAMES={'CreateVpc','DescribeVpcs','DescribeVpcAttribute','ModifyVpcAttribute','CreateTags','DeleteTags','DeleteVpc','GetCallerIdentity','GetUser','ListRoles'}

def emit(gate,status,exit_code=None,api=None,resource_id=None,diagnostic=None,sha=None,run_id=None):
  require(re.fullmatch(r"[A-Za-z0-9_-]{1,100}",gate) and status in ["PASS","FAIL","BLOCKED","NOT_TESTED","PARTIAL-SKIP"],"safe-report")
  require(api is None or api in API_NAMES,"safe-api-name")
  require(diagnostic is None or diagnostic in DIAGNOSTICS,"safe-diagnostic")
  row={'gate':gate,'status':status}
  if sha is not None:
    require(re.fullmatch('[0-9a-f]{40}',sha) and re.fullmatch('[0-9]+-[0-9]+',run_id),'safe-execution-identity');row.update(sha=sha,run_id=run_id)
  if diagnostic is not None:row['diagnostic']=diagnostic
  if exit_code is not None:
    require(type(exit_code) is int,'safe-exit-code');row['exit_code']=exit_code
  if api is not None:row['api']=api
  if resource_id is not None:
    require(re.fullmatch('vpc-[0-9a-f]+',resource_id),'safe-resource-id');row['resource_id']=resource_id
  print(json.dumps(row),flush=True)

class Run:
  def __init__(self):
    self.manifest=strict_json((HERE/'run.json').read_text())
    require(re.fullmatch('[0-9a-f]{40}',self.manifest['sha']) and re.fullmatch('[0-9]+-[0-9]+',self.manifest['run_id']),'run-manifest')
    self.run_id=self.manifest['run_id'];self.root=PRIVATE/'root';self.home=PRIVATE/'home'
    emit('execution-identity','PASS',sha=self.manifest['sha'],run_id=self.run_id)
    self.report={'sha':self.manifest['sha'],'controls':dict.fromkeys(CONTROLS,'NOT_TESTED'),'operations':dict.fromkeys(OPERATIONS,'NOT_TESTED'),'cleanup_complete':False,'lifecycle_ok':False,'resource_cleanup':'NOT_TESTED','material_cleanup':'NOT_TESTED','process_cleanup':'NOT_TESTED'}
    self.env={'PATH':'/usr/local/bin:/usr/bin:/bin','HOME':str(self.home),'CHECKPOINT_DISABLE':'1','TF_IN_AUTOMATION':'true','TF_INPUT':'false','AWS_CONFIG_FILE':'/dev/null','AWS_EC2_METADATA_DISABLED':'true','AWS_DEFAULT_REGION':'ca-central-1','AWS_REGION':'ca-central-1','AWS_PAGER':'','EMULATOR_TELEMETRY':'off','NO_PROXY':'127.0.0.1,localhost','AWS_MAX_ATTEMPTS':'2','AWS_RETRY_MODE':'standard'}
    self.emulator=None;self.baseline=None;self.owned_id=None;self.creation_attempted=False
    self.phase='create';self.lifecycle_ok=False;self.current_operation='preflight';self.private_owned=False;self.plans={};self.failed=False;self.recovering=False;self.credentials=None
  def mark(self,key,name):
    if self.recovering:
      emit('recovery-'+name,'PASS');return
    self.report[key][name]='PASS';emit(('control-' if key=='controls' else '')+name,'PASS',resource_id=self.owned_id if name in ['api_create','api_update','destroy','api_absence'] else None)
  def cmd(self,args,ok=(0,),env=None):
    if getattr(self,'emulator',None) is not None and self.emulator.poll() is not None:raise RuntimeFailure('EMULATOR_PROCESS_EXIT')
    try:p=subprocess.run(args,cwd=self.root,env=env or self.env,capture_output=True,text=True,timeout=120)
    except subprocess.TimeoutExpired:raise RuntimeFailure('COMMAND_TIMEOUT') from None
    except RuntimeFailure:raise
    except Exception:raise RuntimeFailure('COMMAND_FAILED') from None
    if p.returncode not in ok:
      api=re.search(r'operation error [A-Za-z0-9]+: ([A-Za-z0-9]+)',p.stdout+p.stderr)
      api=api.group(1) if api and api.group(1) in API_NAMES else None
      unsupported=bool(api and re.search(r'(?:StatusCode: ?501|HTTP ?501)',p.stdout+p.stderr))
      status='PARTIAL-SKIP' if unsupported else 'FAIL'
      if self.current_operation in self.report['operations']:self.report['operations'][self.current_operation]=status
      emit(self.current_operation+'-'+Path(args[0]).name,status,p.returncode,api)
      raise RuntimeFailure('COMMAND_FAILED')
    if p.returncode==0:emit(self.current_operation+'-'+Path(args[0]).name,'PASS',p.returncode)
    return p
  def tf(self,*args,ok=(0,)):
    return self.cmd(['terraform',*args],ok)
  def aws(self,service,operation,*args):
    p=self.cmd(['aws','--no-cli-pager','--endpoint-url',ENDPOINT,'--ca-bundle',self.env['AWS_CA_BUNDLE'],'--region','ca-central-1','--cli-connect-timeout','3','--cli-read-timeout','10',service,operation,*args,'--output','json'])
    return strict_json(p.stdout) if p.stdout.strip() else {}
  def vpcs(self):
    rows=self.aws('ec2','describe-vpcs')['Vpcs'];d={v['VpcId']:v for v in rows};require(len(d)==len(rows),'duplicate-api-id')
    for value in rows:
      tags=value.get('Tags',[])
      require(len({tag['Key'] for tag in tags})==len(tags),'duplicate-api-tag')
      value['Tags']=sorted(tags,key=lambda tag:tag['Key'])
    return d
  def state(self):
    if not (self.root/'terraform.tfstate').exists():return {'resources':[]}
    value=strict_json(self.tf('state','pull').stdout)
    require(isinstance(value,dict) and value.get('version')==4 and value.get('terraform_version')=='1.17.0','state-file-header')
    return value
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
    p=self.cmd(['aws','--no-cli-pager','--endpoint-url',ENDPOINT,'--ca-bundle',self.env['AWS_CA_BUNDLE'],'--region','ca-central-1','ec2','describe-vpcs','--vpc-ids',self.owned_id,'--output','json'],ok=(254,))
    require(cli_error_code(p,'DescribeVpcs')=='InvalidVpcID.NotFound','independent-delete-absence')
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
    self.startup()
    self.authenticate()
    self.current_operation='provider-init'
    require({f.name for f in (HERE/'adapter').iterdir()}=={'main.tf','.terraform.lock.hcl'},'adapter-source-inventory')
    for f in (HERE/'adapter').iterdir():shutil.copyfile(f,self.root/f.name)
    baseline=(self.root/'.terraform.lock.hcl').read_bytes()
    cli=PRIVATE/'terraform.rc';cli.write_text('provider_installation { filesystem_mirror { path = "/opt/verification/mirror" include = ["registry.terraform.io/hashicorp/aws"] } }\n')
    self.env['TF_CLI_CONFIG_FILE']=str(cli)
    self.variables('create');self.tf('init','-input=false','-lockfile=readonly','-no-color');self.tf('validate','-no-color')
    require((self.root/'.terraform.lock.hcl').read_bytes()==baseline,'offline-provider-lock');self.mark('controls','9')
    self.current_operation='initial_state_empty'
    require(state_id(self.state(),self.run_id) is None,'initial-state-not-empty');self.mark('operations','initial_state_empty');self.mark('controls','10')
    self.current_operation='baseline'
    self.baseline=self.vpcs()
    require(all(v['CidrBlock']!='10.238.0.0/16' for v in self.baseline.values()),'test-cidr-preexisting')
  def http(self,request,context,timeout=5):
    class NoRedirect(urllib.request.HTTPRedirectHandler):
      def redirect_request(self,*args,**kwargs):raise RuntimeFailure('HEALTH_NOT_READY')
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),urllib.request.HTTPSHandler(context=context),NoRedirect())
    return opener.open(request,timeout=timeout)
  def startup(self):
    self.current_operation='startup'
    log=PRIVATE/'emulator.log';err=PRIVATE/'emulator.err'
    with log.open('w') as out,err.open('w') as stderr:
      self.emulator=subprocess.Popen(['aws-emulator','--bind','127.0.0.1','--port','9297','--auth','on','--telemetry','off','--idle-timeout','600'],env=self.env,stdout=out,stderr=stderr)
    deadline=time.monotonic()+60;record=None
    while time.monotonic()<deadline:
      if self.emulator.poll() is not None:raise RuntimeFailure('STARTUP_PROCESS_EXIT')
      raw=log.read_bytes()
      if len(raw)>2*1024**2:raise RuntimeFailure('STARTUP_LOG_INVALID')
      try:
        candidates=[startup_record(strict_json(line),self.home) for line in raw.split(b'\n')[:-1] if line.strip()]
        candidates=[r for r in candidates if r is not None]
      except RuntimeFailure:raise
      except Exception:raise RuntimeFailure('STARTUP_LOG_INVALID') from None
      if len(candidates)>1:raise RuntimeFailure('STARTUP_LOG_INVALID')
      if candidates:record=candidates[0];break
      time.sleep(0.5)
    if record is None:raise RuntimeFailure('STARTUP_TIMEOUT')
    self.current_operation='generated-material'
    try:
      expected=self.home/'.aws/emulator/9297'
      ca=generated_file(Path(record['ca_file']),expected/'ca.pem',os.getuid())
      for key,filename in [('config_file','config'),('java_truststore_file','truststore.p12')]:generated_file(Path(record[key]),expected/filename,os.getuid())
      credentials=generated_file(expected/'emulator_credentials',expected/'emulator_credentials',os.getuid())
      parser=configparser.ConfigParser(interpolation=None);parser.read(credentials)
      require(not parser.defaults() and parser.sections()==['default'] and all(parser['default'].get(k) for k in ['aws_access_key_id','aws_secret_access_key']),'generated-credentials')
      self.credentials=dict(parser['default'])
      self.env.update(AWS_SHARED_CREDENTIALS_FILE=str(credentials),AWS_CA_BUNDLE=str(ca),AWS_PROFILE='default')
    except RuntimeFailure:raise
    except Exception:raise RuntimeFailure('GENERATED_MATERIAL_INVALID') from None
    self.current_operation='health'
    try:
      context=ssl.create_default_context(cafile=str(ca));tls_gate(context.verify_mode,context.check_hostname)
    except RuntimeFailure:raise
    except Exception:raise RuntimeFailure('TLS_VALIDATION_FAILED') from None
    healthy=False
    while time.monotonic()<deadline:
      if self.emulator.poll() is not None:raise RuntimeFailure('STARTUP_PROCESS_EXIT')
      try:
        with self.http(ENDPOINT+'/__admin/health',context) as response:
          healthy=response.status==200 and response.read(64)==b'ok'
      except urllib.error.URLError as error:
        if isinstance(error.reason,ssl.SSLCertVerificationError):raise RuntimeFailure('TLS_VALIDATION_FAILED') from None
      if healthy:break
      time.sleep(0.5)
    if not healthy:raise RuntimeFailure('HEALTH_NOT_READY')
    try:
      with self.http(ENDPOINT+'/__admin/health',ssl.create_default_context()):pass
    except urllib.error.URLError as error:
      if not isinstance(error.reason,ssl.SSLCertVerificationError):raise RuntimeFailure('TLS_VALIDATION_FAILED') from None
    else:raise RuntimeFailure('TLS_VALIDATION_FAILED')
    if self.emulator.poll() is not None:raise RuntimeFailure('STARTUP_PROCESS_EXIT')
    self.mark('controls','2');self.mark('controls','4');self.mark('controls','5');emit('startup-ready','PASS')
  def authenticate(self):
    self.current_operation='auth-signed-sts'
    try:identity_gate(self.aws('sts','get-caller-identity'))
    except RuntimeFailure:raise
    except Exception:raise RuntimeFailure('SYNTHETIC_IDENTITY_MISMATCH') from None
    self.mark('controls','8')
    args=['aws','--no-cli-pager','--endpoint-url',ENDPOINT,'--ca-bundle',self.env['AWS_CA_BUNDLE'],'--region','ca-central-1','--cli-connect-timeout','3','--cli-read-timeout','10','sts','get-caller-identity','--output','json']
    # STS translates the framework's Unauthenticated refusal according to whether
    # the presented key resolves. Its external code is not generic AccessDenied.
    for field,label,code in [('aws_secret_access_key','signature','SignatureDoesNotMatch'),('aws_access_key_id','credential','InvalidClientTokenId')]:
      self.current_operation='auth-invalid-'+label
      changed=dict(self.credentials);value=changed[field];changed[field]=('X' if value[0]!='X' else 'Y')+value[1:]
      env=dict(self.env,AWS_ACCESS_KEY_ID=changed['aws_access_key_id'],AWS_SECRET_ACCESS_KEY=changed['aws_secret_access_key'])
      result=self.cmd(args,ok=(0,254,255),env=env)
      observed=cli_error_code(result,'GetCallerIdentity')
      if result.returncode!=254 or observed!=code:
        diagnostic='AUTH_REQUEST_ACCEPTED' if result.returncode==0 else {'AccessDenied':'AUTH_UNEXPECTED_ACCESS_DENIED','SignatureDoesNotMatch':'AUTH_UNEXPECTED_SIGNATURE_MISMATCH','InvalidClientTokenId':'AUTH_UNEXPECTED_INVALID_TOKEN'}.get(observed,'AUTH_UNCLASSIFIED_REJECTION')
        emit(self.current_operation,'BLOCKED',exit_code=result.returncode,diagnostic=diagnostic)
        raise RuntimeFailure('AUTH_REJECTION_UNPROVEN')
      emit(self.current_operation,'PASS')
    # Route unsigned STS explicitly; a 404 UnknownService never proves authentication.
    self.current_operation='auth-unsigned-sts'
    request=urllib.request.Request(ENDPOINT,data=b'Action=GetCallerIdentity&Version=2011-06-15',headers={'Host':'sts.ca-central-1.amazonaws.com','Content-Type':'application/x-www-form-urlencoded'})
    context=ssl.create_default_context(cafile=self.env['AWS_CA_BUNDLE']);tls_gate(context.verify_mode,context.check_hostname)
    try:
      with self.http(request,context):pass
    except urllib.error.HTTPError as error:
      body=error.read(8193)
      if not unsigned_sts_rejected(error.code,body):
        emit('auth-unsigned-sts','BLOCKED',diagnostic='AUTH_UNSIGNED_UNRESOLVED' if error.code==404 else 'AUTH_UNCLASSIFIED_REJECTION')
        raise RuntimeFailure('AUTH_REJECTION_UNPROVEN') from None
    else:raise RuntimeFailure('AUTH_REJECTION_UNPROVEN')
    self.mark('controls','3');emit('authentication-enforced','PASS')
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
    read_plan=self.root/'refresh.plan'
    self.tf('plan','-refresh-only','-detailed-exitcode','-input=false','-no-color','-out='+str(read_plan))
    refresh_gate(strict_json(self.tf('show','-json',str(read_plan)).stdout),self.owned_id,self.run_id,self.phase);self.mark('operations','read')
    self.current_operation='update'
    self.variables('updated');plan=self.inventory('updated','update',self.owned_id)
    self.apply_plan(plan);self.phase='updated';self.mark('operations','update')
    self.current_operation='api_update'
    rows=self.vpcs();api_owner(rows[self.owned_id],self.owned_id,self.run_id,'updated');self.baseline_preserved(rows,True);self.mark('operations','api_update')
    self.current_operation='no_op'
    self.inventory('updated','no-op',self.owned_id);self.mark('operations','no_op')
    self.destroy();self.lifecycle_ok=True;self.report['lifecycle_ok']=True
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
    require(self.owned_id is None or self.owned_id==candidate,'known-owned-id-mismatch')
    self.owned_id=candidate;self.phase=phase;self.baseline_preserved(rows,True);self.variables(phase)
    if found:
      require(found==candidate,'residual-id-mismatch');self.destroy()
    else:
      # Partial create with no State: API cleanup is NOT Terraform Destroy success.
      self.aws('ec2','delete-vpc','--vpc-id',candidate);self.absence();emit('partial-create-api-cleanup','PASS')
  def finish(self):
    require(self.private_owned or not PRIVATE.exists(),'private-material-remains')
    resource_status='NOT_TESTED'
    if self.creation_attempted:
      try:
        if not self.lifecycle_ok:
          self.recovering=True
          try:self.recover()
          finally:self.recovering=False
        # Even a completed lifecycle must retain independent absence/empty State proof.
        require(state_id(self.state(),self.run_id) is None,'residual-state')
        self.baseline_preserved(self.vpcs(),False)
        if self.owned_id:self.absence()
        resource_status='PASS'
      except Exception as error:resource_status='FAIL';emit('resource-cleanup','FAIL',diagnostic=error.code if isinstance(error,RuntimeFailure) else 'RESOURCE_CLEANUP_FAILED')
    self.report['resource_cleanup']=resource_status
    if resource_status!='FAIL':emit('resource-cleanup',resource_status)
    process_ok=True
    if self.emulator:
      try:
        if self.emulator.poll() is None:self.emulator.terminate()
        self.emulator.wait(timeout=15)
      except subprocess.TimeoutExpired:
        process_ok=False
        try:
          self.emulator.kill();self.emulator.wait(timeout=5)
        except Exception:pass
      except Exception:process_ok=False
    self.report['process_cleanup']='PASS' if process_ok else 'FAIL'
    emit('process-cleanup',self.report['process_cleanup'],diagnostic=None if process_ok else 'PROCESS_CLEANUP_FAILED')
    material_ok=False
    try:
      if self.private_owned and PRIVATE.exists():shutil.rmtree(PRIVATE)
      require(not PRIVATE.exists(),'private-material-remains');material_ok=True
    except Exception:emit('material-cleanup','FAIL',diagnostic='MATERIAL_CLEANUP_FAILED')
    finally:self.credentials=None
    self.report['material_cleanup']='PASS' if material_ok else 'FAIL'
    if material_ok:self.mark('operations','material_cleanup')
    self.report['cleanup_complete']=resource_status=='PASS' and material_ok and process_ok
    if self.report['cleanup_complete']:self.mark('controls','14')
    for key in ['controls','operations']:
      for name,status in self.report[key].items():
        if status!='PASS':emit(('control-' if key=='controls' else '')+name,status)
    if self.failed or not self.lifecycle_ok:raise RuntimeFailure('EVIDENCE_INCOMPLETE')
    try:evidence_gate(self.report)
    except Exception:raise RuntimeFailure('EVIDENCE_INCOMPLETE') from None
    emit('lifecycle-evidence-complete','PASS')

def main():
  import signal
  def interrupted(signum,frame):raise RuntimeFailure('INTERRUPTED')
  previous=signal.signal(signal.SIGTERM,interrupted)
  os.umask(0o077);run=None;failed=False
  try:
    run=Run();run.setup();run.execute()
  except (Exception,KeyboardInterrupt,SystemExit) as error:
    failed=True
    if run:run.failed=True
    operation=run.current_operation if run else 'preflight'
    fallback='PLAN_REJECTED' if operation in ['plan','update','no_op','destroy_plan','read'] else 'PROVIDER_INIT_FAILED' if operation=='provider-init' else 'STATE_REJECTED' if operation in ['initial_state_empty','baseline'] or (run and run.creation_attempted) else 'UNCLASSIFIED_FAILURE'
    emit('execution','FAIL' if run and run.creation_attempted else 'BLOCKED',diagnostic=error.code if isinstance(error,RuntimeFailure) else 'INTERRUPTED' if isinstance(error,(KeyboardInterrupt,SystemExit)) else fallback)
  finally:
    try:
      if run:
        try:run.finish()
        except (Exception,KeyboardInterrupt,SystemExit) as error:
          failed=True;emit('complete-evidence-and-cleanup','FAIL',diagnostic=error.code if isinstance(error,RuntimeFailure) else 'EVIDENCE_INCOMPLETE')
      else:failed=True
    finally:signal.signal(signal.SIGTERM,previous)
  return 1 if failed else 0
if __name__=='__main__':raise SystemExit(main())
