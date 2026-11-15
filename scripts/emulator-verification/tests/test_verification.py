"""Offline only: no Docker, Emulator, Terraform apply/destroy, AWS or network."""
import copy,errno,io,json,os,sys,tempfile,unittest
from contextlib import redirect_stdout
from datetime import datetime,timezone,timedelta
from pathlib import Path
from unittest.mock import patch,Mock
HERE=Path(__file__).resolve().parents[1];REPO=HERE.parents[1]
sys.dont_write_bytecode=True;sys.path.insert(0,str(HERE));sys.path.insert(0,str(REPO/'kubernetes/vendor/pyyaml'))
import yaml
from gates import *
from contracts import workflow_gate
import lifecycle
from prepare import verify_signature

SHA='a'*40;RUN='123-1';ID='vpc-0123456789abcdef0';NOW=datetime(2026,11,15,tzinfo=timezone.utc)
def vpc(phase='create'):
  return {'VpcId':ID,'CidrBlock':'10.238.0.0/16','Tags':[{'Key':k,'Value':v} for k,v in {'Name':'emulator-proof-'+RUN,'VerificationRun':RUN,'Phase':phase}.items()]}
def plan(action='create',phase='create'):
  row={'id':ID,'cidr_block':'10.238.0.0/16','tags':{'Name':'emulator-proof-'+RUN,'VerificationRun':RUN,'Phase':phase}}
  before=None if action=='create' else copy.deepcopy(row)
  if action=='update':before['tags']['Phase']='create'
  return {'terraform_version':'1.17.0','configuration':{'root_module':{'resources':[{'address':'aws_vpc.proof','mode':'managed'}]}},'resource_changes':[{'address':'aws_vpc.proof','type':'aws_vpc','name':'proof','mode':'managed','provider_name':'registry.terraform.io/hashicorp/aws','change':{'actions':[action],'before':before,'after':None if action=='delete' else row,'after_unknown':{}}}]}
class Gates(unittest.TestCase):
  def test_owner_positive_and_negative(self):
    args=['owner','owner','public','refs/heads/main',SHA,SHA,True,NOW.isoformat(),'1','owner',NOW]
    owner_gate(*args)
    for i,v in [(0,'outsider'),(2,'private'),(3,'refs/pull/1/merge'),(4,'b'*40),(5,'main'),(6,False),(7,'bad'),(7,(NOW-timedelta(hours=1)).isoformat()),(7,(NOW+timedelta(minutes=1)).isoformat()),(7,'2026-11-15T00:00:00'),(8,'2'),(9,'outsider')]:
      with self.subTest(i=i,v=v):
        a=args.copy();a[i]=v
        with self.assertRaises((Blocked,ValueError)):owner_gate(*a)
  def test_signature_status(self):
    fingerprint='A'*40
    signature_gate('[GNUPG:] VALIDSIG '+fingerprint+' 0 0',fingerprint)
    for s in ['', '[GNUPG:] BADSIG test', '[GNUPG:] VALIDSIG '+'B'*40+' 0 0','[GNUPG:] VALIDSIG '+fingerprint+' 0 0\n[GNUPG:] EXPKEYSIG x']:
      with self.subTest(s=s),self.assertRaises(Blocked):signature_gate(s,fingerprint)
  def test_actual_gpg_rejects_invalid_signature(self):
    with tempfile.TemporaryDirectory() as d:
      p=Path(d);(p/'data').write_text('not an AWS package');(p/'sig').write_text('invalid signature')
      with self.assertRaises(Blocked):verify_signature(p/'data',p/'sig',HERE/'awscli-publisher.asc','FB5DB77FD5C118B80511ADA8A6310ACC4672475C')
  def test_network_routes(self):
    links=[{'ifname':'lo'}];routes=[{'dst':'127.0.0.0/8','dev':'lo'},{'dst':'::1','dev':'lo'}]
    network_gate('net:[1]','net:[2]',links,routes)
    for host,current,l,r in [('same','same',links,routes),('', 'other',links,routes),('a','b',links+[{'ifname':'eth0'}],routes),('a','b',links,[{'dst':'default','dev':'lo'}]),('a','b',links,[{'dst':'10.0.0.0/8','dev':'lo'}]),('a','b',links,[{'dst':'127.0.0.0/8','dev':'lo','gateway':'1.1.1.1'}])]:
      with self.subTest(r=r),self.assertRaises(Blocked):network_gate(host,current,l,r)
  def test_external_unreachability(self):
    unreachable_gate({'sts':[errno.ENETUNREACH],'ec2':[errno.EHOSTUNREACH]})
    for d in [{},{'sts':[errno.ENETUNREACH]}, {'sts':[],'ec2':[]},*({'sts':[c],'ec2':[errno.ENETUNREACH]} for c in [0,errno.ETIMEDOUT,errno.ECONNREFUSED,errno.EACCES])]:
      with self.subTest(d=d),self.assertRaises(Blocked):unreachable_gate(d)
  def test_identity(self):
    good={'Account':'000000000000','Arn':'arn:aws:iam::000000000000:user/emulator'};identity_gate(good)
    for key,value in [('Account','111111111111'),('Arn','arn:aws:iam::000000000000:root')]:
      d=dict(good);d[key]=value
      with self.assertRaises(Blocked):identity_gate(d)
  def test_plans_positive(self):
    for action,phase in [('create','create'),('update','updated'),('no-op','updated'),('delete','updated')]:
      plan_gate(plan(action,phase),action,RUN,phase,None if action=='create' else ID)
  def test_plan_mutations(self):
    for name in ['missing','extra','address','type','actions','cidr','owner','tags','provider','index','module','configuration','version']:
      p=plan();r=p['resource_changes'][0];c=r['change']
      if name=='missing':p['resource_changes']=[]
      if name=='extra':p['resource_changes'].append(copy.deepcopy(r))
      if name=='address':r['address']='aws_vpc.preexisting'
      if name=='type':r['type']='aws_subnet'
      if name=='actions':c['actions']=['delete','create']
      if name=='cidr':c['after']['cidr_block']='10.0.0.0/8'
      if name=='owner':c['after']['tags']['VerificationRun']='other'
      if name=='tags':c['after']['tags']['extra']='unapproved'
      if name=='provider':r['provider_name']='untrusted/aws'
      if name=='index':r['index']=0
      if name=='module':r['module_address']='module.other'
      if name=='configuration':p['configuration']['root_module']['resources'].append({'address':'data.secret.unsafe','mode':'data'})
      if name=='version':p['terraform_version']='unknown'
      with self.subTest(name=name),self.assertRaises(Blocked):plan_gate(p,'create',RUN,'create')
    with self.assertRaises(Blocked):plan_gate(plan('delete','updated'),'delete',RUN,'updated','vpc-foreign')
    p=plan('update','updated');p['resource_changes'][0]['change']['after']['enable_dns_support']=False
    with self.assertRaises(Blocked):plan_gate(p,'update',RUN,'updated',ID)
  def test_reviewed_plan_hash_rejects_change(self):
    import hashlib
    with tempfile.TemporaryDirectory() as d:
      p=Path(d)/'saved.plan';p.write_bytes(b'reviewed')
      run=object.__new__(lifecycle.Run);run.plans={str(p):hashlib.sha256(p.read_bytes()).hexdigest()};run.tf=Mock()
      run.apply_plan(p);run.tf.assert_called_once()
      p.write_bytes(b'tampered');run.tf.reset_mock()
      with self.assertRaises(Blocked):run.apply_plan(p)
      run.tf.assert_not_called()
  def test_state_and_api_identity(self):
    attrs=plan()['resource_changes'][0]['change']['after']
    s={'resources':[{'type':'aws_vpc','name':'proof','mode':'managed','instances':[{'attributes':attrs}]}]}
    self.assertEqual(state_id(s,RUN),ID);self.assertIsNone(state_id({'resources':[]},RUN))
    for name in ['wrong-id','wrong-tag','extra-resource']:
      q=copy.deepcopy(s)
      if name=='wrong-id':q['resources'][0]['instances'][0]['attributes']['id']='wrong'
      if name=='wrong-tag':q['resources'][0]['instances'][0]['attributes']['tags']['VerificationRun']='other'
      if name=='extra-resource':q['resources'].append(copy.deepcopy(q['resources'][0]))
      with self.subTest(name=name),self.assertRaises(Blocked):state_id(q,RUN)
    api_owner(vpc(),ID,RUN,'create')
    with self.assertRaises(Blocked):api_owner(vpc(),'vpc-other',RUN,'create')
  def test_missing_and_forged_evidence(self):
    r={'sha':SHA,'controls':dict.fromkeys(CONTROLS,'PASS'),'operations':dict.fromkeys(OPERATIONS,'PASS'),'cleanup_complete':True};evidence_gate(r)
    for group in ['controls','operations']:
      for name in list(r[group]):
        q=copy.deepcopy(r);q[group].pop(name)
        with self.subTest(group=group,name=name),self.assertRaises(Blocked):evidence_gate(q)
      for status in ['NOT_TESTED','BLOCKED','FAIL','PARTIAL-SKIP']:
        q=copy.deepcopy(r);q[group][next(iter(q[group]))]=status
        with self.subTest(status=status),self.assertRaises(Blocked):evidence_gate(q)
    q=copy.deepcopy(r);q['cleanup_complete']=False
    with self.assertRaises(Blocked):evidence_gate(q)
    for s in ['{"x":1,"x":2}','{"x":NaN}','{broken']:
      with self.assertRaises((ValueError,Blocked)):lifecycle.strict_json(s)
  def test_failed_destroy_and_cleanup_cannot_pass(self):
    # Exercise the actual exception/finish coordinator with all resource calls mocked.
    fake=Mock();fake.creation_attempted=True;fake.setup.return_value=None;fake.execute.side_effect=Blocked('destroy-failed');fake.finish.side_effect=Blocked('cleanup-incomplete')
    output=io.StringIO()
    with patch.object(lifecycle,'Run',return_value=fake),redirect_stdout(output):self.assertEqual(lifecycle.main(),1)
    self.assertNotIn('lifecycle-evidence-complete',output.getvalue());self.assertIn('FAIL',output.getvalue())
  def test_command_error_output_never_logged(self):
    run=object.__new__(lifecycle.Run);run.root=Path('/tmp');run.env={};run.current_operation='create';run.report={'operations':dict.fromkeys(OPERATIONS,'NOT_TESTED')}
    p=Mock(returncode=1,stdout='private-key-value',stderr='secret-credential-value');output=io.StringIO()
    with patch.object(lifecycle.subprocess,'run',return_value=p),redirect_stdout(output),self.assertRaises(Blocked):run.cmd(['terraform','apply'])
    self.assertNotIn('private-key-value',output.getvalue());self.assertNotIn('secret-credential-value',output.getvalue())
  def test_workflow_and_mutations(self):
    w=yaml.load((REPO/'.github/workflows/aws-emulator-verification.yml').read_text(),Loader=yaml.BaseLoader);workflow_gate(w)
    for name in ['push','write','runner','artifact','cache','sha','owner','network','caps','ports','mount','privileged','credentials','lfs']:
      q=copy.deepcopy(w);j=q['jobs']['representative'];steps=j['steps']
      if name=='push':q['on']['push']={}
      if name=='write':q['permissions']['contents']='write'
      if name=='runner':j['runs-on']='ubuntu-latest'
      if name in ['artifact','cache']:steps.append({'uses':'actions/'+('upload-artifact' if name=='artifact' else 'cache')+'@'+'a'*40})
      if name=='sha':steps[0]['run']=steps[0]['run'].replace("assert e['TARGET_SHA']==e['GITHUB_SHA']",'pass')
      if name=='owner':steps[0]['run']=steps[0]['run'].replace("e['OWNER_BILLING_CONFIRMED']=='true'",'True')
      if name=='network':steps[3]['run']=steps[3]['run'].replace('--network none','--network host')
      if name=='caps':steps[3]['run']=steps[3]['run'].replace('--cap-drop ALL','')
      if name in ['ports','mount','privileged']:steps[3]['run']=steps[3]['run'].replace('docker run ','docker run '+{'ports':'-p 9297:9297 ','mount':'-v /:/host ','privileged':'--privileged '}[name])
      if name=='credentials':steps[1]['with']['persist-credentials']='true'
      if name=='lfs':steps[1]['with']['lfs']='true'
      with self.subTest(name=name),self.assertRaises(Blocked):workflow_gate(q)
  def test_recovery_never_deletes_foreign_or_mismatched_resource(self):
    run=object.__new__(lifecycle.Run);run.creation_attempted=True;run.baseline={};run.owned_id=None;run.run_id=RUN
    foreign=vpc();foreign['Tags']=[{'Key':'VerificationRun','Value':'other'}]
    run.vpcs=Mock(return_value={ID:foreign});run.aws=Mock();run.destroy=Mock()
    with self.assertRaises(Blocked):run.recover()
    run.aws.assert_not_called();run.destroy.assert_not_called()
    run.vpcs=Mock(return_value={ID:vpc()});run.state=Mock(return_value={'resources':[]})
    # A State ID with a different API ID must not reach destroy.
    run.state=Mock(return_value={'resources':[{'type':'aws_vpc','name':'proof','mode':'managed','instances':[{'attributes':dict(plan()['resource_changes'][0]['change']['after'],id='vpc-ffffffff')}]}]})
    run.variables=Mock()
    with self.assertRaises(Blocked):run.recover()
    run.aws.assert_not_called();run.destroy.assert_not_called()
  def test_cleanup_does_not_remove_unowned_material(self):
    run=object.__new__(lifecycle.Run);run.lifecycle_ok=False;run.recover=Mock();run.emulator=None;run.private_owned=False
    with tempfile.TemporaryDirectory() as d:
      private=Path(d)/'preexisting';private.mkdir();marker=private/'keep';marker.write_text('keep')
      with patch.object(lifecycle,'PRIVATE',private),self.assertRaises(Blocked):run.finish()
      self.assertEqual(marker.read_text(),'keep')
  def test_initial_dispatch_script_execution(self):
    import subprocess
    w=yaml.load((REPO/'.github/workflows/aws-emulator-verification.yml').read_text(),Loader=yaml.BaseLoader)
    script=w['jobs']['representative']['steps'][0]['run']
    with tempfile.TemporaryDirectory() as d:
      env=dict(os.environ,ACTOR='owner',OWNER='owner',VISIBILITY='public',OWNER_BILLING_CONFIRMED='true',TRIGGERING_ACTOR='owner',GITHUB_RUN_ATTEMPT='1',GITHUB_REF='refs/heads/main',TARGET_SHA=SHA,GITHUB_SHA=SHA,OWNER_CHECKED_AT=datetime.now(timezone.utc).isoformat(),GITHUB_OUTPUT=str(Path(d)/'output'))
      self.assertEqual(subprocess.run(['bash','-c',script],env=env,capture_output=True).returncode,0)
      for k,v in [('TARGET_SHA','b'*40),('OWNER_BILLING_CONFIRMED','false'),('ACTOR','outsider'),('GITHUB_RUN_ATTEMPT','2')]:
        with self.subTest(k=k):self.assertNotEqual(subprocess.run(['bash','-c',script],env=dict(env,**{k:v}),capture_output=True).returncode,0)
  def test_tls_disabled_rejected(self):
    import ssl
    c=ssl.create_default_context();tls_gate(c.verify_mode,c.check_hostname)
    for mode,hostname in [(ssl.CERT_NONE,False),(ssl.CERT_OPTIONAL,True),(ssl.CERT_REQUIRED,False)]:
      with self.subTest(mode=mode,hostname=hostname),self.assertRaises(Blocked):tls_gate(mode,hostname)
  def test_tls_and_provider_source_contract(self):
    tf=(HERE/'adapter/main.tf').read_text();src=(HERE/'lifecycle.py').read_text();docker=(HERE/'Dockerfile').read_text()
    for forbidden in ['skip_credentials_validation','insecure','skip_requesting_account_id']:
      self.assertNotIn(forbidden,tf)
    self.assertIn('custom_ca_bundle',tf);self.assertIn('allowed_account_ids = ["000000000000"]',tf)
    self.assertIn('ssl.SSLCertVerificationError',src);self.assertNotIn('CERT_NONE',src)
    self.assertIn('ssl.create_default_context(cafile=str(ca))',src)
    self.assertIn('ubuntu:24.04@sha256:',docker);self.assertIn('sha256sum --check',docker)

if __name__=='__main__':
  suite=unittest.defaultTestLoader.loadTestsFromTestCase(Gates)
  result=unittest.TextTestRunner(verbosity=2).run(suite)
  raise SystemExit(0 if result.wasSuccessful() and not result.skipped and result.testsRun==19 else 1)
