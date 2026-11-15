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

def signature_gate(status, fingerprint):
  # GnuPG status-fd is parsed, not the human-readable Good signature message.
  rows = [l.split() for l in status.splitlines() if l.startswith('[GNUPG:] VALIDSIG ')]
  require(len(rows) == 1 and rows[0][2] == fingerprint and not any(x in status for x in ['BADSIG', 'ERRSIG', 'REVKEYSIG', 'EXPKEYSIG']), 'package-signature')

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
  if action == 'update':
    require(c['before']['tags'].get('Phase') == 'create' and phase == 'updated', 'tag-update-transition')
    require({k:v for k,v in c['before'].items() if k not in ['tags','tags_all']} == {k:v for k,v in c['after'].items() if k not in ['tags','tags_all']}, 'tag-only-update')
  if action in ['update', 'no-op']:
    require(c['before'].get('cidr_block') == row['cidr_block'] and c['before']['tags'].get('VerificationRun') == run_id, 'update-owner')
    require(c.get('after_unknown', {}).get('id', False) is False, 'unknown-update-id')
    require(c['after'].get('id') == owned_id, 'update-id')

def state_id(state, run_id):
  rows = state.get('resources', [])
  if not rows:
    return None
  require(len(rows) == 1 and rows[0].get('type') == 'aws_vpc' and rows[0].get('name') == 'proof' and rows[0].get('mode') == 'managed' and 'module' not in rows[0], 'state-inventory')
  require(len(rows[0]['instances']) == 1, 'state-instances')
  a = rows[0]['instances'][0]['attributes']
  require(re.fullmatch('vpc-[0-9a-f]+', a.get('id', '')) and a.get('cidr_block') == '10.238.0.0/16' and a.get('tags', {}).get('VerificationRun') == run_id, 'state-owner')
  return a['id']

def api_owner(vpc, owned_id, run_id, phase):
  tags = {x['Key']: x['Value'] for x in vpc.get('Tags', [])}
  require(vpc.get('VpcId') == owned_id and vpc.get('CidrBlock') == '10.238.0.0/16' and tags == {'Name': 'emulator-proof-'+run_id, 'VerificationRun': run_id, 'Phase': phase}, 'api-resource-identity')

CONTROLS = [str(i) for i in range(1, 15)]
OPERATIONS = ['plan', 'create', 'read', 'api_create', 'update', 'api_update', 'no_op', 'destroy_plan', 'destroy', 'api_absence', 'state_empty', 'baseline_preserved', 'material_cleanup']

def evidence_gate(report):
  require(re.fullmatch('[0-9a-f]{40}', report.get('sha', '')), 'evidence-sha')
  for key, expected in [('controls', CONTROLS), ('operations', OPERATIONS)]:
    require(set(report.get(key, {})) == set(expected), 'evidence-inventory')
    require(all(v == 'PASS' for v in report[key].values()), 'incomplete-evidence')
  require(report.get('cleanup_complete') is True, 'cleanup-incomplete')
