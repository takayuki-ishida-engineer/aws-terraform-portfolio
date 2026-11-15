"""Pure startup/material and safe diagnostic contracts; no resource operations."""
import json,stat
from pathlib import Path
from gates import Blocked,require
ENDPOINT='https://127.0.0.1:9297'
DIAGNOSTICS=frozenset([
  'STARTUP_PROCESS_EXIT','STARTUP_TIMEOUT','STARTUP_LOG_INVALID',
  'STARTUP_ENDPOINT_MISMATCH','GENERATED_MATERIAL_INVALID','TLS_VALIDATION_FAILED',
  'HEALTH_NOT_READY','AUTH_REQUEST_ACCEPTED','AUTH_UNEXPECTED_ACCESS_DENIED','AUTH_UNEXPECTED_SIGNATURE_MISMATCH','AUTH_UNEXPECTED_INVALID_TOKEN','AUTH_UNCLASSIFIED_REJECTION','AUTH_UNSIGNED_UNRESOLVED','AUTH_REJECTION_UNPROVEN','SYNTHETIC_IDENTITY_MISMATCH',
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
