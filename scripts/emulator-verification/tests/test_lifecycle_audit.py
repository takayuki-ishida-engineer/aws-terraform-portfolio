"""Integrated real Run orchestration with simulated process/API transport only."""
import copy,errno,io,json,os,signal,ssl,subprocess,tempfile,unittest,urllib.error
from contextlib import ExitStack,redirect_stdout,redirect_stderr
from datetime import datetime,timezone
from pathlib import Path
from unittest.mock import Mock,patch
import lifecycle,host_evidence
from gates import Blocked,plan_gate,state_id,refresh_gate,OPERATIONS,evidence_gate
from runtime_contracts import RuntimeFailure,startup_record,generated_file
HERE=Path(__file__).resolve().parents[1]
FIXTURES=Path(__file__).parent/'fixtures'
SHA='a'*40;RUN='123-1';ID='vpc-0123456789abcdef0';BASE='vpc-eeeeeeee'
LEAK='DUMMY_SECRET_OR_RAW_LOG_MUST_NOT_ESCAPE'
# Independent source-derived service oracle; never import production error codes.
STS=json.loads((FIXTURES/'sts-1.0.385.json').read_text())

def attrs(phase='create'):
  a=copy.deepcopy(json.loads((FIXTURES/'native-vpc-create-change.json').read_text())['change']['after'])
  a.update(id=ID,arn='arn:aws:ec2:ca-central-1:000000000000:vpc/'+ID,owner_id='000000000000')
  a['tags']['Phase']=phase;a['tags_all']=dict(a['tags']);return a

def state(values):
  return {'version':4,'terraform_version':'1.17.0','serial':1,'lineage':'synthetic','outputs':{},'resources':[] if values is None else [{'mode':'managed','type':'aws_vpc','name':'proof','provider':'provider["registry.terraform.io/hashicorp/aws"]','instances':[{'schema_version':1,'attributes':copy.deepcopy(values)}]}]}

def vpc(values):
  return {'VpcId':values['id'],'CidrBlock':values['cidr_block'],'OwnerId':'000000000000','Tags':[{'Key':k,'Value':v} for k,v in values['tags'].items()]}

def plan(action='create',phase='create',before=None):
  row=copy.deepcopy(json.loads((FIXTURES/'native-vpc-create-change.json').read_text()))
  before=copy.deepcopy(before or attrs('create'))
  after=attrs(phase)
  if action!='create':row['change'].update(actions=[action],before=before,after=None if action=='delete' else after,after_unknown={})
  result={'format_version':'1.2','terraform_version':'1.17.0','configuration':{'root_module':{'resources':[{'address':'aws_vpc.proof','mode':'managed'}]}},'resource_changes':[row], 'planned_values':{'root_module':{'resources':[{'address':'aws_vpc.proof','mode':'managed','type':'aws_vpc','provider_name':'registry.terraform.io/hashicorp/aws','values':after}]}}}
  if action=='delete':result['planned_values']={'root_module':{}}
  return result


def refresh_plan(values):
  # Terraform 1.17.0 `show -json` of `plan -refresh-only` (observed offline with the real
  # binary): no resource_changes, empty planned_values, refreshed object in prior_state.
  resource={'address':'aws_vpc.proof','mode':'managed','type':'aws_vpc','name':'proof','provider_name':'registry.terraform.io/hashicorp/aws','schema_version':1,'sensitive_values':{},'values':copy.deepcopy(values)}
  return {'format_version':'1.2','terraform_version':'1.17.0','applyable':False,'complete':True,'errored':False,'configuration':{'root_module':{'resources':[{'address':'aws_vpc.proof','mode':'managed'}]}},'planned_values':{'root_module':{}},'prior_state':{'format_version':'1.0','terraform_version':'1.17.0','values':{'root_module':{'resources':[resource]}}}}


class Response:
  def __init__(self,body=b'ok',status=200):self.body=io.BytesIO(body);self.status=status
  def read(self,*args):return self.body.read(*args)
  def __enter__(self):return self
  def __exit__(self,*args):self.body.close()

class Process:
  def __init__(self,model):self.model=model;self.returncode=None
  def poll(self):return self.returncode
  def terminate(self):self.returncode=0
  def kill(self):
    if self.model.fault=='process-kill-failed':raise OSError(LEAK)
    self.returncode=-9
  def wait(self,timeout=None):
    if self.model.fault in ['process-cleanup','process-kill-failed'] and self.returncode!=-9:raise subprocess.TimeoutExpired('private',timeout)
    return self.returncode

class Model:
  def __init__(self,directory,fault=None):
    self.base=Path(directory);self.source=self.base/'source';self.source.mkdir();self.private=self.base/'work/private';self.private.parent.mkdir()
    (self.source/'adapter').mkdir();(self.source/'adapter/main.tf').write_text((HERE/'adapter/main.tf').read_text());(self.source/'adapter/.terraform.lock.hcl').write_text('public synthetic lock')
    manifest={'sha':SHA,'run_id':RUN,'host_netns':'net:[host]','owner_checked_at':datetime.now(timezone.utc).isoformat(),'probes':{'sts':['1.1.1.1'],'ec2':['1.1.1.2']},'artifacts_verified':True,'versions':json.loads((HERE/'versions.json').read_text())}
    (self.source/'run.json').write_text(json.dumps(manifest))
    self.fault=fault;self.run=None;self.time=0;self.saved={};self.values=None;self.calls=[];self.delete_ids=[];self.consumed=False
    self.original={BASE:{'VpcId':BASE,'CidrBlock':'10.99.0.0/16','Tags':[]}}
    self.inventory=copy.deepcopy(self.original);self.process=None
  def clock(self):return self.time
  def sleep(self,delay):self.time+=max(delay,1)
  def make_run(self):
    self.run=self.real_run();return self.run
  def popen(self,args,**kw):
    self.process=Process(self)
    home=self.private/'home';folder=home/'.aws/emulator/9297';folder.mkdir(parents=True)
    for name in ['ca.pem','config','truststore.p12']:
      p=folder/name;p.write_text('private fixture '+LEAK);p.chmod(0o600)
    credentials=folder/'emulator_credentials';credentials.write_text('[default]\naws_access_key_id = DUMMY_ACCESS\naws_secret_access_key = DUMMY_SECRET\n');credentials.chmod(0o600)
    row=json.loads((FIXTURES/'startup-1.0.385.json').read_text())
    for key in ['ca_file','config_file','java_truststore_file']:row['fields'][key]=row['fields'][key].replace('/work/private',str(self.private))
    if self.fault=='startup-timeout':row['fields']['message']='not ready'
    if self.fault=='startup-exit':self.process.returncode=7
    if self.fault=='startup-path':row['fields']['ca_file']='/foreign/ca.pem'
    if self.fault=='credential-mode':credentials.chmod(0o644)
    if self.fault=='credential-symlink':
      foreign=self.base/'foreign';foreign.write_text(LEAK);credentials.unlink();credentials.symlink_to(foreign)
    text='malformed '+LEAK if self.fault=='startup-json' else json.dumps(row)
    kw['stdout'].write(text+'\n');kw['stdout'].flush()
    return self.process
  def context(self,*args,**kw):
    if kw.get('cafile') and self.fault=='invalid-ca':raise ssl.SSLError(LEAK)
    context=ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT);context.fixture_trusted=bool(kw.get('cafile'));return context
  def http(self,request,context,timeout=5):
    if not context.fixture_trusted:
      if self.fault=='untrusted-ca-accepted':return Response()
      raise urllib.error.URLError(ssl.SSLCertVerificationError(LEAK))
    if isinstance(request,str):return Response(b'not-ready' if self.fault=='health-timeout' else b'ok')
    code=404 if self.fault=='unsigned-unknown-service' else STS['unsigned']['status']
    body='<Error><Code>UnknownService</Code></Error>' if code==404 else STS['unsigned']['body']
    raise urllib.error.HTTPError('https://127.0.0.1:9297',code,'private error',{},io.BytesIO(body.encode()))
  def write_state(self):
    (self.run.root/'terraform.tfstate').write_text(json.dumps(state(self.values)))
  def command(self,args,**kw):
    self.calls.append((list(args),dict(kw.get('env',{}))))
    tool=Path(args[0]).name;out='';err='';code=0
    if tool=='ip':out=json.dumps([{'ifname':'lo'}] if 'link' in args else [{'dst':'127.0.0.0/8' if '-4' in args else '::1','dev':'lo'}])
    elif tool=='aws-emulator':out='aws-emulator 1.0.385'
    elif tool=='aws':
      if '--version' in args:out='aws-cli/2.35.0'
      elif 'get-caller-identity' in args:
        env=kw['env'];error=None
        if env.get('AWS_ACCESS_KEY_ID') and env['AWS_ACCESS_KEY_ID']!='DUMMY_ACCESS':error='unknown_key'
        elif env.get('AWS_SECRET_ACCESS_KEY') and env['AWS_SECRET_ACCESS_KEY']!='DUMMY_SECRET':error='wrong_secret'
        if self.fault=='invalid-credential-accepted' and error=='unknown_key':error=None
        if error and self.fault!='auth-off':
          reply=STS[error];code=reply['exit'];out=reply['stdout'];err=reply['stderr'].replace('synthetic private message omitted',LEAK)
        else:out=json.dumps(dict(STS['signed'],Account='111111111111') if self.fault=='sts-mismatch' else STS['signed'])
      elif 'describe-vpcs' in args:
        if '--vpc-ids' in args and args[args.index('--vpc-ids')+1] not in self.inventory:
          code=254;err='\naws: [ERROR]: An error occurred (InvalidVpcID.NotFound) when calling the DescribeVpcs operation: '+LEAK+'\n'
        else:out=json.dumps({'Vpcs':list(self.inventory.values())})
      elif 'delete-vpc' in args:
        target=args[args.index('--vpc-id')+1];self.delete_ids.append(target);self.inventory.pop(target)
      else:raise AssertionError('Unexpected AWS test operation')
    elif tool=='terraform':
      operation=args[1]
      if operation=='version':out=json.dumps({'terraform_version':'1.17.0'})
      elif operation=='init':
        if self.fault=='provider-init':code=1;err=LEAK
        elif self.fault=='initial-state':self.values=attrs();self.write_state()
      elif operation=='validate':pass
      elif operation=='state':out=json.dumps(state(self.values))
      elif operation=='plan':
        phase=json.loads((self.run.root/'inputs.auto.tfvars.json').read_text())['phase']
        action='delete' if '-destroy' in args else 'no-op' if self.values is not None and self.values['tags']['Phase']==phase else 'update' if self.values else 'create'
        row=plan(action,phase,self.values)
        if '-refresh-only' in args:row=refresh_plan(self.values)
        if action=='delete' and self.values and self.values['tags']['Phase']!=phase:
          drift=plan('update','updated',self.values)['resource_changes'][0];row['resource_drift']=[drift];row['resource_changes'][0]['change']['before']=attrs(phase)
        if self.fault=='plan-inventory' and action=='create':row['resource_changes'].append(copy.deepcopy(row['resource_changes'][0]))
        if self.fault=='refresh-drift' and '-refresh-only' in args:row['resource_drift']=[{}]
        path=Path(next(arg[5:] for arg in args if arg.startswith('-out=')));path.write_bytes(b'private saved plan '+LEAK.encode());self.saved[str(path)]=row
      elif operation=='show':out=json.dumps(self.saved[args[-1]])
      elif operation=='apply':
        row=self.saved[args[-1]];action=row['resource_changes'][0]['change']['actions'][0]
        if action=='create':
          self.values=attrs();self.inventory[ID]=vpc(self.values)
          if self.fault!='partial-create-no-state':self.write_state()
          if self.fault=='api-id-mismatch':self.values['id']='vpc-ffffffff';self.write_state()
          if self.fault in ['partial-create','partial-create-no-state']:code=1;err=LEAK
          if self.fault=='command-timeout':raise subprocess.TimeoutExpired(args,120,output=LEAK)
          if self.fault=='sigterm':signal.getsignal(signal.SIGTERM)(signal.SIGTERM,None)
          if self.fault=='process-crash':self.process.returncode=9
        elif action=='update':
          self.inventory[ID]=vpc(attrs('updated'))
          if self.fault=='partial-update':code=1;err=LEAK
          else:self.values=attrs('updated');self.write_state()
        elif action=='delete':
          if self.fault=='destroy-once' and not self.consumed:self.consumed=True;code=1;err=LEAK
          else:self.delete_ids.append(ID);self.inventory.pop(ID,None);self.values=None;self.write_state()
        else:raise AssertionError('Unexpected apply action')
      else:raise AssertionError('Unexpected Terraform test operation')
    else:raise AssertionError('Unexpected test tool')
    return subprocess.CompletedProcess(args,code,out,err)
  def invoke(self):
    self.real_run=lifecycle.Run;out=io.StringIO();err=io.StringIO();read=Path.read_text;exists=Path.exists
    def file_read(path,*args,**kw):
      if str(path)=='/proc/self/status':return 'CapEff:\t0000000000000000\nCapBnd:\t0000000000000000\nNoNewPrivs:\t1\n'
      return read(path,*args,**kw)
    def file_exists(path):return False if str(path)=='/var/run/docker.sock' else exists(path)
    sock=Mock();sock.__enter__=Mock(return_value=sock);sock.__exit__=Mock();sock.connect_ex.return_value=errno.ENETUNREACH
    with ExitStack() as stack:
      contexts=[patch.object(lifecycle,'HERE',self.source),patch.object(lifecycle,'PRIVATE',self.private),patch.object(lifecycle,'Run',side_effect=self.make_run),patch.dict(os.environ,{'PATH':'/usr/bin:/bin'},clear=True),patch.object(Path,'read_text',file_read),patch.object(Path,'exists',file_exists),patch.object(lifecycle.os,'statvfs',return_value=Mock(f_flag=os.ST_RDONLY)),patch.object(lifecycle.os,'readlink',return_value='net:[isolated]'),patch.object(lifecycle.socket,'socket',return_value=sock),patch.object(lifecycle.subprocess,'run',side_effect=self.command),patch.object(lifecycle.subprocess,'Popen',side_effect=self.popen),patch.object(lifecycle.time,'monotonic',side_effect=self.clock),patch.object(lifecycle.time,'sleep',side_effect=self.sleep),patch.object(lifecycle.ssl,'create_default_context',side_effect=self.context),patch.object(self.real_run,'http',side_effect=self.http),redirect_stdout(out),redirect_stderr(err)]
      if self.fault=='material-cleanup':
        real_remove=lifecycle.shutil.rmtree
        def remove(path,*args,**kw):
          if Path(path)==self.private:raise OSError(LEAK)
          return real_remove(path,*args,**kw)
        contexts.append(patch.object(lifecycle.shutil,'rmtree',side_effect=remove))
      for context in contexts:stack.enter_context(context)
      code=lifecycle.main()
    assert LEAK not in out.getvalue()+err.getvalue(),'Private fixture leaked'
    assert err.getvalue()=='','Unexpected stderr'
    return code,[json.loads(line) for line in out.getvalue().splitlines()]

class IntegratedLifecycle(unittest.TestCase):
  def invoke(self,fault=None):
    with tempfile.TemporaryDirectory() as directory:
      model=Model(directory,fault);code,rows=model.invoke()
      self.assertTrue(all(target==ID for target in model.delete_ids));self.assertEqual(model.inventory.get(BASE),model.original[BASE])
      if fault!='material-cleanup':self.assertFalse(model.private.exists())
      return code,rows,model
  def test_complete_setup_execute_finish_with_real_gate_code(self):
    code,rows,model=self.invoke();self.assertEqual(code,0)
    self.assertTrue(model.run.lifecycle_ok);evidence_gate(model.run.report)
    host_rows=rows+[{'gate':'host-cleanup','status':'PASS'}]
    host_evidence.complete(host_evidence.rows_from_text('\n'.join(json.dumps(row) for row in host_rows)),SHA,RUN,'success')
    self.assertEqual([r['gate'] for r in rows if r['gate'] in OPERATIONS],['initial_state_empty','plan','create','api_create','read','update','api_update','no_op','destroy_plan','destroy','state_empty','api_absence','baseline_preserved','material_cleanup'])
    self.assertEqual(model.delete_ids,[ID]);self.assertEqual(model.inventory,model.original)
  def test_startup_failures_never_claim_ready_or_resource_cleanup(self):
    for fault,diagnostic in [('startup-timeout','STARTUP_TIMEOUT'),('startup-exit','STARTUP_PROCESS_EXIT'),('startup-json','STARTUP_LOG_INVALID'),('startup-path','GENERATED_MATERIAL_INVALID'),('credential-mode','GENERATED_MATERIAL_INVALID'),('credential-symlink','GENERATED_MATERIAL_INVALID'),('invalid-ca','TLS_VALIDATION_FAILED'),('health-timeout','HEALTH_NOT_READY'),('untrusted-ca-accepted','TLS_VALIDATION_FAILED')]:
      with self.subTest(fault=fault):
        code,rows,model=self.invoke(fault);self.assertEqual(code,1)
        self.assertIn(diagnostic,[r.get('diagnostic') for r in rows]);self.assertNotIn('startup-ready',[r['gate'] for r in rows])
        self.assertEqual(model.delete_ids,[]);self.assertIn({'gate':'resource-cleanup','status':'NOT_TESTED'},rows)
        self.assertNotIn({'gate':'control-14','status':'PASS'},rows)
  def test_auth_sts_provider_and_plan_failures(self):
    for fault in ['auth-off','invalid-credential-accepted','unsigned-unknown-service','sts-mismatch','provider-init','initial-state','plan-inventory']:
      with self.subTest(fault=fault):
        code,rows,model=self.invoke(fault);self.assertEqual(code,1);self.assertFalse(model.run.creation_attempted)
        self.assertFalse(any(r['gate']=='lifecycle-evidence-complete' for r in rows));self.assertIn({'gate':'resource-cleanup','status':'NOT_TESTED'},rows)
        self.assertFalse(any(args[0]=='terraform' and args[1]=='apply' for args,_ in model.calls))
        if fault=='invalid-credential-accepted':self.assertIn({'gate':'auth-invalid-credential','status':'BLOCKED','exit_code':0,'diagnostic':'AUTH_REQUEST_ACCEPTED'},rows)
        if fault=='unsigned-unknown-service':self.assertIn({'gate':'auth-unsigned-sts','status':'BLOCKED','diagnostic':'AUTH_UNSIGNED_UNRESOLVED'},rows)
  def test_partial_apply_update_destroy_and_interrupt_recovery(self):
    for fault in ['partial-create','partial-create-no-state','partial-update','destroy-once','refresh-drift','command-timeout','sigterm']:
      with self.subTest(fault=fault):
        code,rows,model=self.invoke(fault);self.assertEqual(code,1)
        self.assertFalse(any(r['gate']=='lifecycle-evidence-complete' for r in rows))
        self.assertIn({'gate':'resource-cleanup','status':'PASS'},rows);self.assertEqual(model.inventory,model.original)
        if fault=='partial-create-no-state':self.assertIn({'gate':'partial-create-api-cleanup','status':'PASS'},rows)
        if fault=='sigterm':self.assertIn('INTERRUPTED',[row.get('diagnostic') for row in rows])
        if fault=='destroy-once':self.assertFalse(any(r['gate']=='destroy' and r['status']=='PASS' for r in rows))
  def test_ambiguous_identity_and_process_crash_refuse_deletion(self):
    for fault in ['api-id-mismatch','process-crash']:
      with self.subTest(fault=fault):
        code,rows,model=self.invoke(fault);self.assertEqual(code,1);self.assertEqual(model.delete_ids,[])
        self.assertTrue(any(r['gate']=='resource-cleanup' and r['status']=='FAIL' for r in rows))
  def test_material_and_process_cleanup_failures_cannot_complete(self):
    for fault in ['material-cleanup','process-cleanup','process-kill-failed']:
      with self.subTest(fault=fault):
        code,rows,_=self.invoke(fault);self.assertEqual(code,1)
        self.assertFalse(any(r['gate']=='lifecycle-evidence-complete' for r in rows))
        self.assertTrue(any(r.get('diagnostic') in ['MATERIAL_CLEANUP_FAILED','PROCESS_CLEANUP_FAILED'] for r in rows))

class RuntimeContracts(unittest.TestCase):
  def test_startup_nested_fixture_and_mutations(self):
    good=json.loads((FIXTURES/'startup-1.0.385.json').read_text());home=Path('/work/private/home')
    self.assertIsNotNone(startup_record(good,home))
    other=copy.deepcopy(good);other['fields']['message']='ordinary event';self.assertIsNone(startup_record(other,home))
    for key,value in [('fields',None),('message','emulator server information'),('level','WARN')]:
      row=copy.deepcopy(good);row[key]=value
      with self.subTest(key=key),self.assertRaises(Blocked):startup_record(row,home)
    for key,value in [('endpoint_url','http://127.0.0.1:9297'),('endpoint_url','https://sts.amazonaws.com'),('health_check_url','https://127.0.0.1:9999/__admin/health'),('ca_file','/foreign/ca.pem')]:
      row=copy.deepcopy(good);row['fields'][key]=value
      with self.subTest(key=key),self.assertRaises(Blocked):startup_record(row,home)
  def test_real_native_plan_projection_and_state_address_mutations(self):
    plan_gate(plan(),'create',RUN,'create')
    for name in ['extra','deferred','drift','wrong-owner']:
      row=plan()
      if name=='extra':row['resource_changes'].append(copy.deepcopy(row['resource_changes'][0]))
      if name=='deferred':row['deferred_changes']=[{}]
      if name=='drift':row['resource_drift']=[{}]
      if name=='wrong-owner':row['resource_changes'][0]['change']['after']['tags']['VerificationRun']='foreign'
      with self.subTest(name=name),self.assertRaises(Blocked):plan_gate(row,'create',RUN,'create')
    for invalid in [{},{'values':{}},{'resources':{}},{'resources':None},{'resources':[],'outputs':{'unexpected':'private'}},{'resources':[],'version':5}]:
      with self.subTest(kind=tuple(invalid)),self.assertRaises(Blocked):state_id(invalid,RUN)
    for key in ['index_key','deposed']:
      value=state(attrs());value['resources'][0]['instances'][0][key]=0
      with self.assertRaises(Blocked):state_id(value,RUN)
  def test_refresh_json_and_owned_tag_drift_recovery(self):
    row=refresh_plan(attrs('create'));refresh_gate(row,ID,RUN,'create')
    row['resource_drift']=[{}]
    with self.assertRaises(Blocked):refresh_gate(row,ID,RUN,'create')
    # Regression for Run 43786507720: refresh-only planned_values is empty; the old
    # no-op-shaped expectation, changes or a foreign refreshed object stay refused.
    old=plan('no-op','create');old['resource_changes']=[]
    def prior(row):return row['prior_state']['values']['root_module']
    mutations={'old-no-op-shape':lambda r:r.clear() or r.update(old),'resource-changes':lambda r:r.update(resource_changes=plan('no-op','create')['resource_changes']),
      'planned-resource':lambda r:r.update(planned_values=old['planned_values']),'no-prior-state':lambda r:r.pop('prior_state'),
      'prior-version':lambda r:r['prior_state'].update(terraform_version='1.16.0'),'prior-child-module':lambda r:prior(r).update(child_modules=[{}]),
      'prior-foreign-id':lambda r:prior(r)['resources'][0]['values'].update(id='vpc-ffffffff'),'prior-phase':lambda r:prior(r)['resources'][0]['values']['tags'].update(Phase='updated'),
      'prior-duplicate':lambda r:prior(r)['resources'].append(copy.deepcopy(prior(r)['resources'][0]))}
    for name,mutate in mutations.items():
      row=refresh_plan(attrs('create'));mutate(row)
      with self.subTest(refresh=name),self.assertRaises(Blocked):refresh_gate(row,ID,RUN,'create')
    destroy=plan('delete','updated',attrs('updated'));destroy['resource_drift']=plan('update','updated')['resource_changes']
    plan_gate(destroy,'delete',RUN,'updated',ID)
    destroy['resource_drift'][0]['change']['after']['id']='vpc-ffffffff'
    with self.assertRaises(Blocked):plan_gate(destroy,'delete',RUN,'updated',ID)
  def test_baseline_tag_order_and_duplicate_tag_identity(self):
    run=object.__new__(lifecycle.Run)
    original=vpc(attrs());changed=copy.deepcopy(original);changed['Tags'].reverse()
    run.aws=Mock(side_effect=[{'Vpcs':[original]},{'Vpcs':[changed]}]);run.baseline=copy.deepcopy(run.vpcs());run.owned_id=None
    run.baseline_preserved(run.vpcs(),False)
    changed['Tags'].append(copy.deepcopy(changed['Tags'][0]));run.aws=Mock(return_value={'Vpcs':[changed]})
    with self.assertRaises(Blocked):run.vpcs()
    from gates import api_owner
    with self.assertRaises(Blocked):api_owner(changed,ID,RUN,'create')
  def test_generated_material_real_file_symlink_and_permission_checks(self):
    with tempfile.TemporaryDirectory() as directory:
      path=Path(directory)/'ca.pem';path.write_text('public fixture');path.chmod(0o600)
      self.assertEqual(generated_file(path,path,os.getuid()),path)
      path.chmod(0o644)
      with self.assertRaises(Blocked):generated_file(path,path,os.getuid())
      path.unlink();target=Path(directory)/'foreign';target.write_text(LEAK);path.symlink_to(target)
      with self.assertRaises(Blocked):generated_file(path,path,os.getuid())
  def test_summary_missing_corrupt_mismatched_and_failure_receipts(self):
    rows=[{'gate':'execution-identity','status':'PASS','sha':SHA,'run_id':RUN}]+[{'gate':g,'status':'PASS'} for g in sorted(host_evidence.REQUIRED-{'host-cleanup'})]+[{'gate':'host-cleanup','status':'PASS'}]
    host_evidence.complete(rows,SHA,RUN,'success')
    for change in ['missing','duplicate','failure','sha','run','oom','host-failure']:
      value=copy.deepcopy(rows);status='success'
      if change=='missing':value.pop(1)
      if change=='duplicate':value.append(copy.deepcopy(value[1]))
      if change=='failure':value.insert(1,{'gate':'execution','status':'FAIL'})
      if change=='sha':value[0]['sha']='b'*40
      if change=='run':value[0]['run_id']='other'
      if change=='oom':status='failure'
      if change=='host-failure':value[-1]['status']='FAIL'
      with self.subTest(change=change),self.assertRaises(Blocked):host_evidence.complete(value,SHA,RUN,status)
    for text in ['{"gate":"'+LEAK+'","status":"PASS"}', '{broken', '{"gate":"host-cleanup","status":"PASS","secret":"'+LEAK+'"}']:
      with self.assertRaises((Blocked,ValueError)):host_evidence.rows_from_text(text)

class LocalTLS(unittest.TestCase):
  def test_real_loopback_https_ca_hostname_and_redirect_rejection(self):
    import http.server,threading,socket
    with tempfile.TemporaryDirectory(prefix='local-tls-') as directory:
      root=Path(directory);key=root/'key.pem';cert=root/'cert.pem'
      command=['openssl','req','-x509','-newkey','rsa:2048','-nodes','-keyout',str(key),'-out',str(cert),'-days','1','-subj','/CN=127.0.0.1','-addext','subjectAltName=IP:127.0.0.1']
      result=subprocess.run(command,capture_output=True);self.assertEqual(result.returncode,0,'Temporary test certificate generation failed')
      class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
          self.send_response(302 if self.path=='/redirect' else 200)
          if self.path=='/redirect':self.send_header('Location','https://outside.example.invalid/')
          self.end_headers();self.wfile.write(b'ok')
        def log_message(self,*args):pass
      server=http.server.ThreadingHTTPServer(('127.0.0.1',0),Handler)
      context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);context.load_cert_chain(cert,key);server.socket=context.wrap_socket(server.socket,server_side=True)
      thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
      try:
        run=object.__new__(lifecycle.Run);port=server.server_port;url='https://127.0.0.1:'+str(port)
        trusted=ssl.create_default_context(cafile=str(cert))
        with run.http(url,trusted) as response:self.assertEqual((response.status,response.read()),(200,b'ok'))
        with self.assertRaises(urllib.error.URLError) as caught:run.http(url,ssl.create_default_context())
        self.assertIsInstance(caught.exception.reason,ssl.SSLCertVerificationError)
        with self.assertRaises(urllib.error.URLError) as caught:run.http('https://localhost:'+str(port),trusted)
        self.assertIsInstance(caught.exception.reason,ssl.SSLCertVerificationError)
        real_resolve=socket.getaddrinfo
        def loopback_only(host,*args,**kwargs):
          if host not in ['127.0.0.1','localhost']:raise AssertionError('External TLS test connection prohibited')
          return real_resolve(host,*args,**kwargs)
        with patch.object(socket,'getaddrinfo',side_effect=loopback_only),self.assertRaises(RuntimeFailure):run.http(url+'/redirect',trusted)
        with self.assertRaises(ssl.SSLError):ssl.create_default_context(cafile=str(key))
      finally:server.shutdown();server.server_close();thread.join(timeout=5)

class HostWorkflow(unittest.TestCase):
  def workflow(self):
    import yaml
    return yaml.load((HERE.parents[1]/'.github/workflows/aws-emulator-verification.yml').read_text(),Loader=yaml.BaseLoader)
  def test_actual_shell_cleanup_with_fake_docker_and_oom(self):
    import sys
    script=self.workflow()['jobs']['representative']['steps'][3]['run']
    subprocess.run(['bash','-n'],input=script,text=True,capture_output=True,check=True)
    for mode in ['success','oom','query-failed','remove-failed','image-failed']:
      with self.subTest(mode=mode),tempfile.TemporaryDirectory() as directory:
        root=Path(directory);binary=root/'bin';binary.mkdir();(root/'emulator-verification').mkdir()
        fake=binary/'docker'
        fake.write_text('#!'+sys.executable+'''\nimport os,sys,json
from pathlib import Path
a=sys.argv[1:];m=os.environ['FAKE_DOCKER_MODE']
if a[0]=='build':Path(a[a.index('--iidfile')+1]).write_text('sha256:'+'a'*64)
elif a[0]=='run':
 print(json.dumps({'gate':'execution-identity','status':'PASS','sha':'a'*40,'run_id':'123-1'}))
 if m=='oom':sys.exit(137)
elif a[:2]==['container','ls']:
 if m=='query-failed':sys.exit(1)
 if m=='remove-failed':print('emulator-proof-123-1')
elif a[0]=='rm':sys.exit(1 if m=='remove-failed' else 0)
elif a[:2]==['image','rm']:sys.exit(1 if m=='image-failed' else 0)
else:sys.exit(1)
''');fake.chmod(0o700)
        env=dict(os.environ,PATH=str(binary)+os.pathsep+'/usr/bin:/bin',RUNNER_TEMP=directory,GITHUB_RUN_ID='123',GITHUB_RUN_ATTEMPT='1',FAKE_DOCKER_MODE=mode)
        result=subprocess.run(['bash','-c',script],env=env,capture_output=True,text=True)
        self.assertEqual(result.returncode,0 if mode=='success' else 137 if mode=='oom' else 1)
        rows=host_evidence.rows_from_text((root/'emulator-safe-report.json').read_text())
        self.assertEqual(rows[-1]['gate'],'host-cleanup');self.assertEqual(rows[-1]['status'],'PASS' if mode in ['success','oom'] else 'FAIL')
        self.assertFalse((root/'emulator-verification').exists());self.assertNotIn(LEAK,result.stdout+result.stderr)
        with self.assertRaises(Blocked):host_evidence.complete(rows,SHA,RUN,'success' if result.returncode==0 else 'failure')
  def test_workflow_security_and_cleanup_mutations(self):
    from contracts import workflow_gate
    good=self.workflow();workflow_gate(good)
    for name in ['write','dispatch','privileged','host-network','mount','env-forward','env-short','cap-add','network-equal','swap','pids','work-noexec','tmp-exec','cleanup','summary','summary-outcome','summary-condition']:
      row=copy.deepcopy(good);run=row['jobs']['representative']['steps'][3]
      if name=='write':row['permissions']['contents']='write'
      if name=='dispatch':row['on']['push']={}
      if name=='privileged':run['run']=run['run'].replace('docker run ','docker run --privileged ')
      if name=='host-network':run['run']=run['run'].replace('--network none','--network host')
      if name=='mount':run['run']=run['run'].replace('docker run ','docker run --mount type=bind,source=/,target=/host ')
      if name=='env-forward':run['run']=run['run'].replace('docker run ','docker run -e AWS_ACCESS_KEY_ID ')
      if name=='env-short':run['run']=run['run'].replace('docker run ','docker run -eAWS_ACCESS_KEY_ID ' )
      if name=='cap-add':run['run']=run['run'].replace('docker run ','docker run --cap-add NET_ADMIN ' )
      if name=='network-equal':run['run']=run['run'].replace('docker run ','docker run --network=host ' )
      if name=='swap':run['run']=run['run'].replace('--memory-swap 3g','')
      if name=='pids':run['run']=run['run'].replace('--pids-limit 128','')
      # Docker tmpfs defaults to noexec: /work needs explicit exec for the provider plugin; /tmp stays noexec.
      if name=='work-noexec':run['run']=run['run'].replace('/work:rw,exec,','/work:rw,')
      if name=='tmp-exec':run['run']=run['run'].replace('/tmp:rw,noexec,','/tmp:rw,exec,')
      if name=='cleanup':run['run']=run['run'].replace('cleanup_failed=1','cleanup_failed=0')
      if name=='summary-outcome':row['jobs']['representative']['steps'][4]['env']['EXECUTION_STATUS']='success'
      if name=='summary-condition':row['jobs']['representative']['steps'][4]['if']='false'
      if name=='summary':row['jobs']['representative']['steps'][4]['run']='true'
      with self.subTest(name=name),self.assertRaises(Blocked):workflow_gate(row)
  def test_summary_never_echoes_malformed_secret_or_false_complete(self):
    with tempfile.TemporaryDirectory() as directory:
      root=Path(directory);report=root/'emulator-safe-report.json';summary=root/'summary'
      for text in ['{'+LEAK, json.dumps({'gate':LEAK,'status':'PASS'}),json.dumps({'gate':'lifecycle-evidence-complete','status':'PASS'})]:
        report.write_text(text);summary.write_text('')
        with patch.dict(os.environ,{'GITHUB_STEP_SUMMARY':str(summary),'RUNNER_TEMP':directory,'TARGET_SHA':SHA,'GITHUB_RUN_ID':'123','GITHUB_RUN_ATTEMPT':'1','OWNER_ATTESTATION_ACCEPTED':'true','EXECUTION_STATUS':'success'}):self.assertEqual(host_evidence.main(),1)
        self.assertNotIn(LEAK,summary.read_text());self.assertIn('SUMMARY_EVIDENCE_INVALID',summary.read_text())

  def test_summary_script_handles_missing_checkout(self):
    script=self.workflow()['jobs']['representative']['steps'][4]['run']
    with tempfile.TemporaryDirectory() as directory:
      path=Path(directory)/'summary'
      result=subprocess.run(['bash','-c',script],cwd=directory,env=dict(os.environ,GITHUB_STEP_SUMMARY=str(path)),capture_output=True,text=True)
      self.assertEqual(result.returncode,1);self.assertIn('CHECKOUT_UNAVAILABLE',path.read_text());self.assertEqual(result.stderr,'')
