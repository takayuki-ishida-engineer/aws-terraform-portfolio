"""Pure fail-closed gates shared by the actual runner and offline tests."""
import ipaddress
import re
from datetime import datetime, timezone

class Blocked(RuntimeError):
  pass

def require(ok, label):
  if not ok:
    raise Blocked(label)

def owner_gate(actor, owner, visibility, ref, actual_sha, target_sha, confirmed, checked_at, attempt, triggering_actor, now=None):
  require(actor == owner and visibility == 'public', 'owner-public')
  require(ref == 'refs/heads/main' and re.fullmatch('[0-9a-f]{40}', target_sha) and actual_sha == target_sha, 'reviewed-main-sha')
  require(confirmed is True and attempt == '1' and triggering_actor == owner, 'owner-billing-not-confirmed')
  freshness_gate(checked_at, now)

def freshness_gate(checked_at, now=None):
  try:
    stamp = datetime.fromisoformat(checked_at)
    require(stamp.tzinfo is not None, 'attestation-timezone')
    age = ((now or datetime.now(timezone.utc)) - stamp).total_seconds()
    require(0 <= age <= 1800, 'stale-owner-attestation')
  except (ValueError, TypeError):
    raise Blocked('owner-attestation-time')

GPG_DIAGNOSTIC_CODES=frozenset([
  'GPG_EXIT_NONZERO','VALIDSIG_MISSING','VALIDSIG_MULTIPLE','VALIDSIG_MALFORMED',
  'SIGNER_PRIMARY_MISMATCH','SIGNATURE_INVALID','SIGNATURE_EXPIRED_OR_REVOKED',
  'GPG_RESULT_UNAVAILABLE',
])

class SignatureBlocked(Blocked):
  def __init__(self, code):
    self.code=code if code in GPG_DIAGNOSTIC_CODES else 'GPG_RESULT_UNAVAILABLE'
    super().__init__()

def signature_gate(status, fingerprint, returncode):
  """Consume only status-fd bytes from the same successful gpg --verify process.

  VALIDSIG's first fingerprint identifies the signer; its optional final field
  identifies the cryptographically bound primary key. Never infer that binding
  from key-list membership or GOODSIG text. Notation/UID payloads need not be UTF-8.
  """
  def reject(code):raise SignatureBlocked(code)
  if type(returncode) is not int or returncode!=0:reject('GPG_EXIT_NONZERO')
  if isinstance(status,str):status=status.encode('utf8')
  if not isinstance(status,bytes):reject('GPG_RESULT_UNAVAILABLE')
  records=[]
  for line in status.split(b'\n'):
    match=re.match(rb'^\[GNUPG:\] ([A-Z_]+)(?: |$)',line)
    if match:records.append((match[1],line))
  codes={code for code,_ in records}
  if codes & {b'EXPSIG',b'EXPKEYSIG',b'REVKEYSIG',b'KEYEXPIRED',b'SIGEXPIRED',b'KEYREVOKED'}:
    reject('SIGNATURE_EXPIRED_OR_REVOKED')
  if codes & {b'BADSIG',b'ERRSIG',b'NO_PUBKEY',b'NODATA',b'BADARMOR',b'ERROR',b'FAILURE',b'UNEXPECTED',b'TRUNCATED'}:
    reject('SIGNATURE_INVALID')
  rows=[line for code,line in records if code==b'VALIDSIG']
  if not rows:reject('VALIDSIG_MISSING')
  if len(rows)!=1:reject('VALIDSIG_MULTIPLE')
  try:args=rows[0].decode('ascii').split()[2:]
  except UnicodeDecodeError:reject('VALIDSIG_MALFORMED')
  if len(args) not in [9,10]:reject('VALIDSIG_MALFORMED')
  signer=args[0];primary=args[9] if len(args)==10 else signer
  valid_fingerprint=lambda value:isinstance(value,str) and re.fullmatch(r'(?:[0-9A-F]{40}|[0-9A-F]{64})',value)
  if not all(valid_fingerprint(value) for value in [fingerprint,signer,primary]):reject('VALIDSIG_MALFORMED')
  if primary!=fingerprint:reject('SIGNER_PRIMARY_MISMATCH')
  return {'signer':signer,'primary':primary}

def network_gate(host_ns, current_ns, links, routes):
  require(bool(host_ns) and host_ns != current_ns, 'independent-netns')
  require({x['ifname'] for x in links} == {'lo'}, 'loopback-only-interface')
  for r in routes:
    require(r.get('dev') == 'lo' and 'gateway' not in r and r.get('dst') not in [None, 'default'], 'external-route')
    require(ipaddress.ip_network(r['dst'], strict=False).is_loopback, 'external-route-address')

def unreachable_gate(results):
  import errno
  require(set(results) == {'sts', 'ec2'}, 'external-probes-missing')
  require(all(v and all(code in [errno.ENETUNREACH, errno.EHOSTUNREACH] for code in v) for v in results.values()), 'external-unreachability-unproven')

def tls_gate(verify_mode, check_hostname):
  import ssl
  require(verify_mode == ssl.CERT_REQUIRED and check_hostname is True, 'strict-tls-verification')

def identity_gate(identity):
  require(identity.get('Account') == '000000000000' and identity.get('Arn') == 'arn:aws:iam::000000000000:user/emulator', 'synthetic-identity')

def plan_gate(plan, action, run_id, phase, owned_id=None):
  require(plan.get('terraform_version') == '1.17.0', 'plan-version')
  configuration=plan.get('configuration', {}).get('root_module', {})
  require(not configuration.get('module_calls') and [(r.get('address'),r.get('mode')) for r in configuration.get('resources', [])] == [('aws_vpc.proof','managed')], 'configuration-inventory')
  require(not plan.get('deferred_changes') and not plan.get('errored',False),'plan-drift-or-deferred')
  if plan.get('resource_drift'):
    require(action=='delete' and len(plan['resource_drift'])==1,'plan-drift')
    # Recovery may observe the already-applied, exact Phase tag transition.
    drift_plan=dict(plan,resource_drift=[],resource_changes=plan['resource_drift'])
    drift_plan.pop('planned_values',None) # Parent destroy values are checked separately below.
    plan_gate(drift_plan,'update',run_id,'updated',owned_id)
  if 'planned_values' in plan:
    root=plan['planned_values'].get('root_module',{})
    require(not root.get('child_modules'),'plan-value-modules')
    require([r.get('address') for r in root.get('resources',[])]==([] if action=='delete' else ['aws_vpc.proof']),'plan-value-inventory')
  changes = plan.get('resource_changes', [])
  require(len(changes) == 1, 'single-plan-resource')
  r = changes[0]
  require(r.get('address') == 'aws_vpc.proof' and r.get('type') == 'aws_vpc' and r.get('mode') == 'managed' and r.get('provider_name') == 'registry.terraform.io/hashicorp/aws' and r.get('name') == 'proof' and 'index' not in r and 'module_address' not in r, 'plan-identity')
  c = r['change']
  require(c['actions'] == [action], 'plan-actions')
  row = c['before'] if action == 'delete' else c['after']
  require(row.get('cidr_block') == '10.238.0.0/16' and row.get('tags') == {'Name': 'emulator-proof-'+run_id, 'VerificationRun': run_id, 'Phase': phase}, 'plan-owner-cidr-tags')
  if action == 'create':
    require(c['before'] is None and owned_id is None, 'create-without-old-state')
  else:
    require(bool(owned_id) and c['before'].get('id') == owned_id, 'plan-owned-id')
  if action == 'delete':require(c.get('after') is None,'delete-after-values')
  if action == 'update':
    require(c['before']['tags'] == {'Name':'emulator-proof-'+run_id,'VerificationRun':run_id,'Phase':'create'} and phase == 'updated', 'tag-update-transition')
    require({k:v for k,v in c['before'].items() if k not in ['tags','tags_all']} == {k:v for k,v in c['after'].items() if k not in ['tags','tags_all']}, 'tag-only-update')
  if action in ['update', 'no-op']:
    require(c['before'].get('cidr_block') == row['cidr_block'] and c['before']['tags'].get('VerificationRun') == run_id, 'update-owner')
    require(c.get('after_unknown', {}).get('id', False) is False, 'unknown-update-id')
    require(c['after'].get('id') == owned_id, 'update-id')

def state_id(state, run_id):
  require(isinstance(state,dict) and state.get('version',4)==4 and 'values' not in state and 'root_module' not in state,'state-raw-format')
  require('resources' in state and isinstance(state['resources'],list) and isinstance(state.get('outputs',{}),dict) and not state.get('outputs'),'state-resources-format')
  rows = state['resources']
  if not rows:
    return None
  require(len(rows) == 1 and rows[0].get('type') == 'aws_vpc' and rows[0].get('name') == 'proof' and rows[0].get('mode') == 'managed' and 'module' not in rows[0], 'state-inventory')
  require(rows[0].get('provider','provider[\"registry.terraform.io/hashicorp/aws\"]')=='provider[\"registry.terraform.io/hashicorp/aws\"]','state-provider')
  require(len(rows[0]['instances']) == 1, 'state-instances')
  instance=rows[0]['instances'][0]
  require('index_key' not in instance and 'deposed' not in instance,'state-instance-address')
  a = instance['attributes']
  require(re.fullmatch('vpc-[0-9a-f]+', a.get('id', '')) and a.get('cidr_block') == '10.238.0.0/16' and a.get('tags', {}).get('VerificationRun') == run_id, 'state-owner')
  return a['id']

def api_owner(vpc, owned_id, run_id, phase):
  raw=vpc.get('Tags',[])
  tags = {x['Key']: x['Value'] for x in raw}
  require(len(tags)==len(raw),'api-duplicate-tags')
  require(vpc.get('VpcId') == owned_id and vpc.get('CidrBlock') == '10.238.0.0/16' and tags == {'Name': 'emulator-proof-'+run_id, 'VerificationRun': run_id, 'Phase': phase}, 'api-resource-identity')

CONTROLS = [str(i) for i in range(1, 15)]
OPERATIONS = ['initial_state_empty', 'plan', 'create', 'read', 'api_create', 'update', 'api_update', 'no_op', 'destroy_plan', 'destroy', 'api_absence', 'state_empty', 'baseline_preserved', 'material_cleanup']

def evidence_gate(report):
  require(re.fullmatch('[0-9a-f]{40}', report.get('sha', '')), 'evidence-sha')
  for key, expected in [('controls', CONTROLS), ('operations', OPERATIONS)]:
    require(set(report.get(key, {})) == set(expected), 'evidence-inventory')
    require(all(v == 'PASS' for v in report[key].values()), 'incomplete-evidence')
  require(report.get('cleanup_complete') is True and report.get('lifecycle_ok') is True, 'cleanup-incomplete')
  require(all(report.get(name)=='PASS' for name in ['resource_cleanup','material_cleanup','process_cleanup']),'cleanup-evidence-missing')


def refresh_gate(plan, owned_id, run_id, phase):
  # Refresh-only JSON may omit no-op resource_changes; planned_values is still exact.
  configuration=plan.get('configuration',{}).get('root_module',{})
  require(plan.get('terraform_version')=='1.17.0' and not plan.get('resource_drift') and not plan.get('deferred_changes') and not plan.get('errored',False),'refresh-drift')
  require(not configuration.get('module_calls') and [(r.get('address'),r.get('mode')) for r in configuration.get('resources',[])]==[('aws_vpc.proof','managed')],'refresh-configuration')
  root=plan['planned_values']['root_module'];require(not root.get('child_modules'),'refresh-modules')
  resources=root.get('resources',[])
  require(len(resources)==1 and resources[0].get('address')=='aws_vpc.proof' and resources[0].get('mode')=='managed' and resources[0].get('type')=='aws_vpc' and resources[0].get('provider_name')=='registry.terraform.io/hashicorp/aws','refresh-inventory')
  values=resources[0]['values']
  require(values.get('id')==owned_id and values.get('cidr_block')=='10.238.0.0/16' and values.get('tags')=={'Name':'emulator-proof-'+run_id,'VerificationRun':run_id,'Phase':phase},'refresh-owner')
  if plan.get('resource_changes'):plan_gate(plan,'no-op',run_id,phase,owned_id)
