"""Independent upstream STS oracle; real Run, parsers and a local fake CLI process.

No AWS CLI, Emulator, Docker or resource operation is executed by these tests.
"""
import copy,datetime,inspect,io,json,ssl,subprocess,sys,tempfile,unittest,urllib.error
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch
import lifecycle,host_evidence
from gates import Blocked,CONTROLS
from runtime_contracts import cli_error_code,unsigned_sts_rejected,signed_sts_request,signed_sts_identity,sts_rejection
from test_lifecycle_audit import Model,STS,LEAK,SHA,RUN

WIRE_SIGNED_XML=(b'<?xml version="1.0"?><GetCallerIdentityResponse xmlns="https://sts.amazonaws.com/doc/2011-06-15/">'
  b'<GetCallerIdentityResult><UserId>synthetic</UserId><Account>000000000000</Account>'
  b'<Arn>arn:aws:iam::000000000000:user/emulator</Arn></GetCallerIdentityResult>'
  b'<ResponseMetadata><RequestId>synthetic</RequestId></ResponseMetadata>'
  b'</GetCallerIdentityResponse>')


class AuthModel(Model):
  """Inject only transport replies, using independent literal fixture outcomes."""
  def __init__(self,directory,probe=None,reply=None,unsigned=None,wire=None):
    super().__init__(directory);self.probe=probe;self.reply=reply;self.unsigned=unsigned;self.wire=wire;self.wire_requests=[]
  def command(self,args,**kw):
    result=super().command(args,**kw)
    if 'get-caller-identity' in args:
      env=kw['env']
      probe='unknown_key' if env.get('AWS_ACCESS_KEY_ID') and env['AWS_ACCESS_KEY_ID']!='DUMMY_ACCESS' else 'wrong_secret' if env.get('AWS_SECRET_ACCESS_KEY') and env['AWS_SECRET_ACCESS_KEY']!='DUMMY_SECRET' else 'signed'
      if probe==self.probe:return subprocess.CompletedProcess(args,self.reply['exit'],self.reply['stdout'],self.reply['stderr'])
    return result
  def http(self,request,context,timeout=5):
    if self.wire is not None and not isinstance(request,str) and request.has_header('Authorization'):
      from test_lifecycle_audit import Response
      self.wire_requests.append(request)
      if len(self.wire_requests)%2==1:
        if self.wire=='bad-baseline':
          raise urllib.error.HTTPError(request.full_url,403,'private',{},io.BytesIO(STS['unsigned']['body'].encode()))
        return Response(WIRE_SIGNED_XML,200)
      if self.wire=='accepted-invalid':return Response(WIRE_SIGNED_XML,200)
      expected='SignatureDoesNotMatch' if self.probe=='wrong_secret' else 'InvalidClientTokenId'
      if self.wire=='wrong-code':expected='AccessDenied'
      status=404 if self.wire=='not-routed' else 403
      body=STS['unsigned']['body'].replace('InvalidClientTokenId',expected).encode()
      if self.wire=='malformed-xml':body=b'<Code>'+expected.encode()+b'</Code>'
      raise urllib.error.HTTPError(request.full_url,status,'private',{},io.BytesIO(body))
    if not isinstance(request,str) and self.unsigned:
      status,body=self.unsigned
      if status==200:
        from test_lifecycle_audit import Response
        return Response(body,status)
      raise urllib.error.HTTPError(request.full_url,status,'private',{},io.BytesIO(body))
    return super().http(request,context,timeout)


class STSContracts(unittest.TestCase):
  def invoke(self,**kw):
    with tempfile.TemporaryDirectory() as directory:
      model=AuthModel(directory,**kw);code,rows=model.invoke()
      self.assertFalse(model.private.exists());return code,rows,model
  def assert_auth_blocked(self,code,rows,model):
    self.assertEqual(code,1);self.assertFalse(model.run.creation_attempted)
    self.assertNotIn({'gate':'control-3','status':'PASS'},rows)
    self.assertIn({'gate':'resource-cleanup','status':'NOT_TESTED'},rows)
    self.assertIn({'gate':'process-cleanup','status':'PASS'},rows)
    self.assertIn({'gate':'material_cleanup','status':'PASS'},rows)
    self.assertEqual(model.delete_ids,[])
    self.assertFalse(any(args[0]=='terraform' and args[1] in ['init','apply'] for args,_ in model.calls))
    self.assertFalse(any(row['gate']=='lifecycle-evidence-complete' for row in rows))
    with self.assertRaises(Blocked):host_evidence.complete(rows,SHA,RUN,'success')
  def test_upstream_oracle_and_sanitized_real_run_provenance(self):
    self.assertEqual(STS['provenance']['sts_blob'],'360b86ea65f621e19067df7b979dc28e9330f3a4')
    self.assertEqual(STS['observed_run']['run_id'],'43715108794')
    self.assertEqual(STS['observed_run']['sha'],'406b468c820ed7ed7db86c9d38b578184811453d')
    self.assertEqual(STS['observed_run']['rows'][-1],{'gate':'auth-invalid-credential','status':'BLOCKED','diagnostic':'AUTH_UNEXPECTED_INVALID_TOKEN','exit_code':254})
    # Literal service expectations, independent of production constants/predicates.
    self.assertIn('(InvalidClientTokenId)',STS['unknown_key']['stderr'])
    self.assertIn('(SignatureDoesNotMatch)',STS['wrong_secret']['stderr'])
    self.assertNotIn('AccessDenied',STS['unknown_key']['stderr'])
  def test_real_run_orchestration_independently_checks_both_key_halves(self):
    code,rows,model=self.invoke();self.assertEqual(code,0)
    probes=[env for args,env in model.calls if 'get-caller-identity' in args]
    self.assertEqual(len(probes),3)
    self.assertNotIn('AWS_ACCESS_KEY_ID',probes[0])
    self.assertTrue(probes[0]['AWS_SHARED_CREDENTIALS_FILE'].endswith('emulator_credentials'))
    self.assertEqual(probes[1]['AWS_ACCESS_KEY_ID'],'DUMMY_ACCESS')
    self.assertNotEqual(probes[1]['AWS_SECRET_ACCESS_KEY'],'DUMMY_SECRET')
    self.assertNotEqual(probes[2]['AWS_ACCESS_KEY_ID'],'DUMMY_ACCESS')
    self.assertEqual(probes[2]['AWS_SECRET_ACCESS_KEY'],'DUMMY_SECRET')
    for gate in ['auth-invalid-signature','auth-invalid-credential','authentication-enforced']:
      self.assertIn({'gate':gate,'status':'PASS'},rows)
  def test_generic_access_denied_is_not_an_sts_unknown_key_oracle(self):
    reply=dict(STS['unknown_key'],stderr=STS['unknown_key']['stderr'].replace('InvalidClientTokenId','AccessDenied'))
    result=self.invoke(probe='unknown_key',reply=reply);self.assert_auth_blocked(*result)
    self.assertIn('AUTH_UNEXPECTED_ACCESS_DENIED',[row.get('diagnostic') for row in result[1]])
  def test_wrong_secret_rejects_unknown_key_code_and_other_service_codes(self):
    for name in ['unknown_key','AccessDenied','ExpiredToken']:
      reply=copy.deepcopy(STS['unknown_key'])
      if name!='unknown_key':reply['stderr']=reply['stderr'].replace('InvalidClientTokenId',name)
      with self.subTest(case=name):self.assert_auth_blocked(*self.invoke(probe='wrong_secret',reply=reply))
    self.assert_auth_blocked(*self.invoke(probe='unknown_key',reply=STS['wrong_secret']))
  def test_exit_code_and_unexpected_success_never_prove_rejection(self):
    for probe in ['wrong_secret','unknown_key']:
      for code in [0,1,253,255]:
        with self.subTest(probe=probe,exit=code):
          result=self.invoke(probe=probe,reply=dict(STS[probe],exit=code));self.assert_auth_blocked(*result)
          self.assertNotIn({'gate':'auth-invalid-'+('signature' if probe=='wrong_secret' else 'credential'),'status':'PASS'},result[1])
  def test_cli_envelope_rejects_embedded_duplicate_malformed_and_stdout(self):
    good=STS['unknown_key']['stderr']
    for text,out in [('prefix '+good,''),(good+good,''),(good.replace('operation:','operation'),''),(good.replace('GetCallerIdentity','DescribeVpcs'),''),(good,json.dumps(STS['signed'])),(good+'\n'+LEAK,''),('<Error>'+good+'</Error>','')]:
      with self.subTest(case=text[:20]):
        reply=dict(STS['unknown_key'],stderr=text,stdout=out)
        self.assertIsNone(cli_error_code(subprocess.CompletedProcess([],254,out,text),'GetCallerIdentity'))
        self.assert_auth_blocked(*self.invoke(probe='unknown_key',reply=reply))
    retry=good.replace('operation:','operation (reached max retries: 1):')
    self.assertEqual(cli_error_code(subprocess.CompletedProcess([],254,'',retry),'GetCallerIdentity'),'InvalidClientTokenId')
  def test_unsigned_envelope_is_source_derived_and_namespace_aware(self):
    body=STS['unsigned']['body'].encode();self.assertTrue(unsigned_sts_rejected(403,body))
    with_id=body.replace(b'</ErrorResponse>',b'<RequestId>synthetic</RequestId></ErrorResponse>')
    self.assertTrue(unsigned_sts_rejected(403,with_id))
    cases=[body.replace(b'InvalidClientTokenId',b'AccessDenied'),body.replace(b'https://sts.amazonaws.com/doc/2011-06-15/',b'https://other.invalid/'),b'<Error><Code>InvalidClientTokenId</Code></Error>',body+b'broken',b'garbage<Code>InvalidClientTokenId</Code>',body.replace(b'<Code>',b'<Code>other</Code><Code>'),body.replace(b'<Message>',b'<Message><Code>InvalidClientTokenId</Code>'),body.replace(b'<Type>Sender</Type>',b''),body+b' '*8193,b'<!DOCTYPE fake>'+body]
    for i,bad in enumerate(cases):
      with self.subTest(case=i):self.assertFalse(unsigned_sts_rejected(403,bad))
    for status in [200,400,401,404,500]:self.assertFalse(unsigned_sts_rejected(status,body))
  def test_unsigned_runtime_2xx_404_and_malformed_403_block_before_provider(self):
    for status,body in [(200,b'ok'),(404,b'UnknownService'),(500,STS['unsigned']['body'].encode()),(403,b'broken<Code>InvalidClientTokenId</Code>')]:
      with self.subTest(status=status):self.assert_auth_blocked(*self.invoke(unsigned=(status,body)))
  def test_auth_disabled_and_accepted_unknown_credentials_remain_effective_negatives(self):
    for probe in ['wrong_secret','unknown_key']:
      reply={'exit':0,'stdout':json.dumps(STS['signed']),'stderr':''}
      with self.subTest(probe=probe):
        result=self.invoke(probe=probe,reply=reply);self.assert_auth_blocked(*result)
        self.assertIn('AUTH_REQUEST_ACCEPTED',[row.get('diagnostic') for row in result[1]])
        gate='auth-invalid-'+('signature' if probe=='wrong_secret' else 'credential')
        self.assertFalse(any(row['gate'].startswith(gate) and row['status']=='PASS' for row in result[1]))
  def test_negative_control_old_production_expectation_fails_independent_oracle(self):
    # Deliberately restore the exact former bug in a transient function, not files.
    source=inspect.getsource(lifecycle.Run.authenticate)
    original="('aws_access_key_id','credential','InvalidClientTokenId')"
    self.assertEqual(source.count(original),1)
    import textwrap
    space=dict(vars(lifecycle));exec(textwrap.dedent(source.replace(original,"('aws_access_key_id','credential','AccessDenied')")),space)
    with patch.object(lifecycle.Run,'authenticate',space['authenticate']):
      result=self.invoke();self.assert_auth_blocked(*result)
      self.assertIn('AUTH_UNEXPECTED_INVALID_TOKEN',[row.get('diagnostic') for row in result[1]])
  def test_real_local_fake_cli_subprocess_and_private_diagnostics(self):
    with tempfile.TemporaryDirectory() as directory:
      root=Path(directory);script=root/'fake_cli.py'
      script.write_text('import json,os,sys\nr='+repr(STS)+'\ne=os.environ\ncase="unknown_key" if e["AWS_ACCESS_KEY_ID"]!="DUMMY_ACCESS" else "wrong_secret" if e["AWS_SECRET_ACCESS_KEY"]!="DUMMY_SECRET" else "signed"\nif case=="signed":print(json.dumps(r[case]));sys.exit(0)\nsys.stderr.write(r[case]["stderr"]);sys.exit(r[case]["exit"])\n')
      run=object.__new__(lifecycle.Run);run.root=root;run.emulator=None;run.recovering=False
      run.credentials={'aws_access_key_id':'DUMMY_ACCESS','aws_secret_access_key':'DUMMY_SECRET'}
      run.env={'AWS_ACCESS_KEY_ID':'DUMMY_ACCESS','AWS_SECRET_ACCESS_KEY':'DUMMY_SECRET','AWS_CA_BUNDLE':'private-ca-path'}
      run.report={'controls':dict.fromkeys(CONTROLS,'NOT_TESTED')}
      actual=run.cmd;run.cmd=lambda args,**kw:actual([sys.executable,str(script),*args[1:]],**kw)
      def refusal(*args,**kw):raise urllib.error.HTTPError('https://127.0.0.1:9297',403,'private',{},io.BytesIO(STS['unsigned']['body'].encode()))
      run.http=refusal;out=io.StringIO()
      with patch.object(lifecycle.ssl,'create_default_context',return_value=ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)),redirect_stdout(out):run.authenticate()
      self.assertEqual(run.report['controls']['3'],'PASS')
      for secret in ['DUMMY_ACCESS','DUMMY_SECRET','private-ca-path','private message']:self.assertNotIn(secret,out.getvalue())
      self.assertTrue(all(row['status']=='PASS' for row in map(json.loads,out.getvalue().splitlines())))
  def test_signed_wire_matches_independent_botocore_sigv4_vector(self):
    # Fixed independent Botocore 1.43.18 SigV4Auth reference, not a production-derived oracle.
    at=datetime.datetime(2026,11,15,tzinfo=datetime.timezone.utc)
    request=signed_sts_request('EMULATOR123456789ABC','0123456789abcdef0123456789abcdef01234567',at)
    self.assertEqual(request.full_url,'https://127.0.0.1:9297/')
    self.assertEqual(request.get_method(),'POST')
    self.assertEqual(request.data,b'Action=GetCallerIdentity&Version=2011-06-15')
    self.assertEqual(request.get_header('Host'),'sts.ca-central-1.amazonaws.com')
    self.assertEqual(request.get_header('Authorization'),
      'AWS4-HMAC-SHA256 Credential=EMULATOR123456789ABC/20261115/ca-central-1/sts/aws4_request, '
      'SignedHeaders=content-type;host;x-amz-date, Signature=f4a844865d9f014468e65f88f22e65c534ba6c22db82268f5f19a538a8a9ee33')
  def test_structured_wire_parsers_reject_malformed_and_wrong_identity(self):
    self.assertEqual(signed_sts_identity(200,WIRE_SIGNED_XML),STS['signed'])
    for body in [WIRE_SIGNED_XML.replace(b'000000000000',b'111111111111'),
                 WIRE_SIGNED_XML.replace(b'GetCallerIdentityResponse',b'ErrorResponse'),
                 WIRE_SIGNED_XML.replace(b'<Account>',b'<Account>bad</Account><Account>'),
                 b'<!DOCTYPE evil>'+WIRE_SIGNED_XML]:
      with self.subTest(body=body[:25]):
        value=signed_sts_identity(200,body)
        self.assertTrue(value is None or value!=STS['signed'])
    self.assertIsNone(signed_sts_identity(403,WIRE_SIGNED_XML))
    unsigned=STS['unsigned']['body'].encode()
    self.assertTrue(sts_rejection(403,unsigned,'InvalidClientTokenId'))
    self.assertTrue(sts_rejection(403,unsigned.replace(b'InvalidClientTokenId',b'SignatureDoesNotMatch'),'SignatureDoesNotMatch'))
    for code,status,body in [('AccessDenied',403,unsigned),( 'SignatureDoesNotMatch',200,unsigned),
                             ('SignatureDoesNotMatch',403,unsigned),('InvalidClientTokenId',404,unsigned),
                             ('InvalidClientTokenId',403,b'<Code>InvalidClientTokenId</Code>')]:
      with self.subTest(code=code,status=status):self.assertFalse(sts_rejection(status,body,code))
  def test_unclassified_cli_requires_exact_signed_wire_positive_and_negative(self):
    for probe in ['wrong_secret','unknown_key']:
      reply=dict(STS[probe],stderr='unclassifiable synthetic CLI diagnostic')
      with self.subTest(probe=probe):
        code,rows,model=self.invoke(probe=probe,reply=reply,wire='valid')
        self.assertEqual(code,0)
        self.assertEqual(len(model.wire_requests),2)
        self.assertIn({'gate':'auth-invalid-'+('signature' if probe=='wrong_secret' else 'credential'),
                       'status':'PASS','diagnostic':'AUTH_WIRE_FALLBACK_VERIFIED'},rows)
        self.assertIn({'gate':'authentication-enforced','status':'PASS'},rows)
        self.assertEqual(model.inventory,model.original)
  def test_unclassified_cli_never_passes_on_false_wire_proof(self):
    for probe in ['wrong_secret','unknown_key']:
      reply=dict(STS[probe],stderr='unclassifiable synthetic CLI diagnostic')
      for wire in ['bad-baseline','accepted-invalid','wrong-code','not-routed','malformed-xml']:
        with self.subTest(probe=probe,wire=wire):
          result=self.invoke(probe=probe,reply=reply,wire=wire)
          self.assert_auth_blocked(*result)
          gate='auth-invalid-'+('signature' if probe=='wrong_secret' else 'credential')
          self.assertFalse(any(row['gate']==gate and row['status']=='PASS' for row in result[1]))
  def test_independent_absence_rejects_error_text_inside_unrelated_output(self):
    run=object.__new__(lifecycle.Run);run.owned_id='vpc-owned';run.env={'AWS_CA_BUNDLE':'private'}
    reply=subprocess.CompletedProcess([],254,'','prefix An error occurred (InvalidVpcID.NotFound) when calling the DescribeVpcs operation: private')
    run.cmd=lambda *args,**kw:reply
    with self.assertRaises(Blocked):run.absence()
