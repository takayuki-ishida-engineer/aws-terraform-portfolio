"""Pure startup/material and safe diagnostic contracts; no resource operations."""
import datetime,hashlib,hmac,json,re,stat,urllib.request,xml.etree.ElementTree as ET
from pathlib import Path
from gates import Blocked,require
ENDPOINT='https://127.0.0.1:9297'
DIAGNOSTICS=frozenset([
  'STARTUP_PROCESS_EXIT','STARTUP_TIMEOUT','STARTUP_LOG_INVALID',
  'STARTUP_ENDPOINT_MISMATCH','GENERATED_MATERIAL_INVALID','TLS_VALIDATION_FAILED',
  'HEALTH_NOT_READY','AUTH_WIRE_FALLBACK_VERIFIED','AUTH_STRUCTURED_REJECTION_UNPROVEN','AUTH_REQUEST_ACCEPTED','AUTH_UNEXPECTED_ACCESS_DENIED','AUTH_UNEXPECTED_SIGNATURE_MISMATCH','AUTH_UNEXPECTED_INVALID_TOKEN','AUTH_UNCLASSIFIED_REJECTION','AUTH_UNSIGNED_UNRESOLVED','AUTH_REJECTION_UNPROVEN','SYNTHETIC_IDENTITY_MISMATCH',
  'PROVIDER_INIT_FAILED','STATE_REJECTED','PLAN_REJECTED','COMMAND_TIMEOUT',
  'COMMAND_FAILED','EMULATOR_PROCESS_EXIT','INTERRUPTED','RESOURCE_CLEANUP_FAILED',
  'MATERIAL_CLEANUP_FAILED','PROCESS_CLEANUP_FAILED','EVIDENCE_INCOMPLETE',
  'UNCLASSIFIED_FAILURE','HOST_CLEANUP_FAILED','SUMMARY_EVIDENCE_INVALID',
])
class RuntimeFailure(Blocked):
  def __init__(self,code):
    self.code=code if code in DIAGNOSTICS else 'UNCLASSIFIED_FAILURE'
    super().__init__()

def strict_json(s):
  def pairs(rows):
    d={}
    for key,value in rows:
      require(key not in d,'duplicate-json');d[key]=value
    return d
  return json.loads(s,object_pairs_hook=pairs,parse_constant=lambda value:(_ for _ in ()).throw(Blocked('nonfinite-json')))

def cli_error_code(result, operation):
  """Read one CLI ClientError envelope, never an embedded error-looking string.

  Caller must separately require exit 254 and the service-specific expected code.
  The message is private and is neither returned nor logged. Retry wording follows
  botocore ClientError; arbitrary/multiple records or successful JSON are refused.
  """
  if result.stdout.strip():return None
  match=re.fullmatch(r'An error occurred \(([A-Za-z0-9.]+)\) when calling the '+re.escape(operation)+r' operation(?: \(reached max retries: [0-9]+\))?: [^\r\n]+',result.stderr.strip())
  return match[1] if match else None

def signed_sts_request(access_key, secret_key, now=None):
  """Sign only the fixed loopback STS request using SigV4; never accept a target URL.

  The signing algorithm is checked against an independent Botocore test vector.
  No key, authorization header, request or response body is ever printed.
  """
  if not isinstance(access_key,str) or not re.fullmatch('[A-Za-z0-9_]+',access_key):raise ValueError('invalid-emulator-key')
  if not isinstance(secret_key,str) or not re.fullmatch('[A-Za-z0-9_]+',secret_key):raise ValueError('invalid-emulator-secret')
  at=now or datetime.datetime.now(datetime.timezone.utc)
  if at.tzinfo is None:raise ValueError('signed-sts-timezone')
  date=at.astimezone(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
  scope=date[:8]+'/ca-central-1/sts/aws4_request'
  host='127.0.0.1:9297'
  signed_headers='content-type;host;x-amz-date'
  canonical_headers='content-type:application/x-www-form-urlencoded\n'+'host:'+host+'\n'+'x-amz-date:'+date+'\n'
  body=b'Action=GetCallerIdentity&Version=2011-06-15'
  canonical='POST\n/\n\n'+canonical_headers+'\n'+signed_headers+'\n'+hashlib.sha256(body).hexdigest()
  to_sign='AWS4-HMAC-SHA256\n'+date+'\n'+scope+'\n'+hashlib.sha256(canonical.encode()).hexdigest()
  def digest(key,value):return hmac.new(key,value.encode(),hashlib.sha256).digest()
  key=digest(('AWS4'+secret_key).encode(),date[:8])
  for part in ['ca-central-1','sts','aws4_request']:key=digest(key,part)
  signature=hmac.new(key,to_sign.encode(),hashlib.sha256).hexdigest()
  authorization='AWS4-HMAC-SHA256 Credential='+access_key+'/'+scope+', SignedHeaders='+signed_headers+', Signature='+signature
  return urllib.request.Request(ENDPOINT+'/',data=body,method='POST',headers={
    'Host':host,'Content-Type':'application/x-www-form-urlencoded',
    'X-Amz-Date':date,'Authorization':authorization,
  })

def signed_sts_identity(status, body):
  """Read the exact identity fields from bounded STS success XML, not text matches."""
  if status!=200 or not isinstance(body,bytes) or len(body)>8192 or b'<!' in body:return None
  ns='{https://sts.amazonaws.com/doc/2011-06-15/}'
  try:root=ET.fromstring(body)
  except (ET.ParseError,ValueError):return None
  if root.tag!=ns+'GetCallerIdentityResponse' or root.attrib:return None
  matches=[child for child in root if child.tag==ns+'GetCallerIdentityResult']
  if len(matches)!=1:return None
  result=matches[0]
  if result.attrib or any(child.attrib or len(child) for child in result):return None
  account=[child.text for child in result if child.tag==ns+'Account']
  arn=[child.text for child in result if child.tag==ns+'Arn']
  if len(account)!=1 or len(arn)!=1:return None
  return {'Account':account[0],'Arn':arn[0]}

def sts_rejection(status, body, expected_code):
  """Validate a single structured awsQuery rejection with an exact error code."""
  if expected_code not in ('SignatureDoesNotMatch','InvalidClientTokenId'):return False
  if status!=403 or not isinstance(body,bytes) or len(body)>8192:return False
  # No declarations/entities: authentication evidence never needs a DTD.
  if b'<!' in body:return False
  ns='{https://sts.amazonaws.com/doc/2011-06-15/}'
  try:root=ET.fromstring(body)
  except (ET.ParseError,ValueError):return False
  if root.tag!=ns+'ErrorResponse' or root.attrib:return False
  if [child.tag for child in root] not in [[ns+'Error'],[ns+'Error',ns+'RequestId']]:return False
  error=root[0]
  if error.attrib or [child.tag for child in error]!=[ns+'Type',ns+'Code',ns+'Message']:return False
  if any(child.attrib or len(child) for child in error):return False
  if len(root)==2 and (root[1].attrib or len(root[1]) or not root[1].text):return False
  if any(text and text.strip() for text in [root.text,error.text,*[child.tail for child in root],*[child.tail for child in error]]):return False
  return error[0].text=='Sender' and error[1].text==expected_code and bool(error[2].text)

def unsigned_sts_rejected(status,body):
  return sts_rejection(status,body,'InvalidClientTokenId')

def startup_record(row, home):
  """v1.0.385 uses tracing-subscriber JSON with non-flattened fields."""
  if not isinstance(row,dict):raise RuntimeFailure('STARTUP_LOG_INVALID')
  fields=row.get('fields')
  if row.get('message')=='emulator server information':raise RuntimeFailure('STARTUP_LOG_INVALID')
  if not isinstance(fields,dict):raise RuntimeFailure('STARTUP_LOG_INVALID')
  if fields.get('message')!='emulator server information':return None
  if row.get('level')!='INFO':raise RuntimeFailure('STARTUP_LOG_INVALID')
  if fields.get('endpoint_url')!=ENDPOINT or fields.get('health_check_url')!=ENDPOINT+'/__admin/health':
    raise RuntimeFailure('STARTUP_ENDPOINT_MISMATCH')
  expected=Path(home)/'.aws/emulator/9297'
  for key,filename in [('ca_file','ca.pem'),('config_file','config'),('java_truststore_file','truststore.p12')]:
    if fields.get(key)!=str(expected/filename):raise RuntimeFailure('GENERATED_MATERIAL_INVALID')
  return fields

def generated_file(path, expected, uid):
  path=Path(path);expected=Path(expected)
  require(path==expected and path.resolve()==expected and not path.is_symlink(),'generated-material-path')
  info=path.stat()
  require(stat.S_ISREG(info.st_mode) and info.st_uid==uid and stat.S_IMODE(info.st_mode)==0o600,'generated-material-permissions')
  return path
