#!/usr/bin/env python3
"""Evidence ledger for formal AWS Emulator workflow runs (Master Policy v14.4 §13.4).

Every run of the Step 2 rehearsal workflow and of the representative workflow is
recorded once per Run ID and Attempt as a sanitized JSON entry in
docs/evidence/emulator-runs/. This tool builds an entry from trusted GitHub run
metadata plus the allowlisted structured rows of the run's job log, validates
entries, regenerates index.md and compares the ledger with actions-runs.json, a
static snapshot of the GitHub Actions run list taken by the operator. The
comparison is only as current as that snapshot: it never queries the GitHub API
and does not show that the ledger matches the live run list at any later time.

The ledger is a third-party-traceable audit record, not a copy of the full log.
Nothing is inferred: a value that the run did not record is absent or marked
NOT_TESTED, and a run without a structured record never gets a 14-control PASS.
The tool reads files only; it makes no network call and starts no emulator.

  harvest.py build --meta META.json [--log JOB.log] --repo REPO --out DIR --harvested-at TS
                    [--registration regular|initial-backfill]   (default regular)
  harvest.py check DIR      validate every entry, index.md and the reconciliation
  harvest.py index DIR      rewrite index.md from the entries
"""
import ast
import datetime
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

SCHEMA = 'emulator-run-ledger/1'
REPOSITORY = 'takayuki-ishida-engineer/aws-terraform-portfolio'
RUN_URL = 'https://github.com/' + REPOSITORY + '/actions/runs/'
MAX_LOG_BYTES = 4 * 1024 * 1024
MAX_LOG_LINES = 20000
MAX_ROW_BYTES = 64 * 1024
MAX_ENTRY_BYTES = 64 * 1024
MAX_TEXT = 400
MAX_LIST = 64
STATUSES = {'PASS', 'FAIL', 'BLOCKED', 'NOT_TESTED', 'PARTIAL-SKIP'}
OVERALL = {'PASS', 'FAIL', 'BLOCKED', 'PARTIAL-SKIP', 'INSUFFICIENT_EVIDENCE'}
CONTROLS = [str(i) for i in range(1, 15)]
DEV_ROOTS = {
    'network': 'infra/services/dev/ca-central-1/network',
    'platform': 'infra/services/dev/ca-central-1/platform',
    'api': 'infra/services/dev/ca-central-1/api',
    'serverless-api': 'infra/services/dev/ca-central-1/serverless-api',
    'developer-access': 'infra/services/dev/ca-central-1/developer-access',
    'tfstate': 'infra/services/dev/ca-central-1/tfstate',
}
WORKFLOWS = {
    '.github/workflows/aws-emulator-rehearsal.yml': {
        'kind': 'step2-rehearsal', 'job': 'rehearsal', 'harness': 'scripts/emulator-rehearsal/rehearse.py'},
    '.github/workflows/aws-emulator-verification.yml': {
        'kind': 'representative', 'job': 'representative', 'harness': 'scripts/emulator-verification/lifecycle.py'},
}
STEP2_OPERATIONS = ['plan', 'create', 'api_create', 'read', 'update_plan', 'update', 'api_update', 'no_op',
                    'teardown_plan', 'teardown', 'destroy_plan', 'destroy', 'state_empty', 'api_absence',
                    'baseline_preserved']
REPRESENTATIVE_OPERATIONS = ['initial_state_empty', 'plan', 'create', 'read', 'api_create', 'update', 'api_update',
                             'no_op', 'destroy_plan', 'destroy', 'api_absence', 'state_empty', 'baseline_preserved',
                             'material_cleanup']
SYNTHETIC_STEPS = {'Set up job', 'Complete job'}

# Harness versions whose output this tool understands well enough to record a
# PASS. Keyed by the SHA-256 of the harness file at the tested SHA. Each pins the
# required lifecycle operations of that version (its OPERATIONS list), the
# reviewed resource inventory of each scenario (count and the SHA-256 of the
# sorted addresses joined by newlines) and which independent evidence the
# harness records. A run of any other harness version can never be PASS: a new
# version must be reviewed and added here, with tests, before its runs register.
STEP2_BASE_OPERATIONS = ['plan', 'create', 'api_create', 'read', 'update_plan', 'update', 'api_update', 'no_op',
                         'destroy_plan', 'destroy', 'state_empty', 'api_absence', 'baseline_preserved']
STEP2_TEARDOWN_OPERATIONS = ['plan', 'create', 'api_create', 'read', 'update_plan', 'update', 'api_update', 'no_op',
                             'teardown_plan', 'teardown', 'destroy_plan', 'destroy', 'state_empty', 'api_absence',
                             'baseline_preserved']
NETWORK_16 = {'resources': 16, 'inventory_sha256': '6070a967904020051d1044a6e742758e19f116924b4696c5e2f5d457f1976953',
              'operations': STEP2_BASE_OPERATIONS, 'api_ids': ['vpc_id']}
KNOWN_HARNESSES = {
    '58a1a15405c945ce23d7e8f04d70df0f38f772bb6e9a32e97c9df34592e4109c': {
        'kind': 'step2-rehearsal', 'format': 'step2-single-root-v1', 'operations': STEP2_BASE_OPERATIONS,
        'records_counts': True, 'root_controls': False,
        'scenarios': {
            'no-interface-endpoints': {'network': NETWORK_16},
            'full': {'network': {'resources': 26, 'inventory_sha256':
                                 '541e7c899f9db30dd2595bbf7a81b3ffb64e95b268c8ca26430710072723f698',
                                 'operations': STEP2_BASE_OPERATIONS, 'api_ids': ['vpc_id']}},
        },
    },
    # PR #75: one run rehearses several roots (multi-root summary-record).
    '6c3b18caa2409cbd10128144788f9751bf0dea605fc90ef65b5ce66e0fe6260f': {
        'kind': 'step2-rehearsal', 'format': 'step2-multi-root-v2', 'operations': STEP2_BASE_OPERATIONS,
        'records_counts': True, 'root_controls': True,
        'scenarios': {
            'all': {'network': NETWORK_16, 'api': {
                'resources': 7, 'inventory_sha256': 'baaaad68febd893ec6f016b2fc587224bcca84e3423b8d779bbd85b357b0347a',
                'operations': STEP2_TEARDOWN_OPERATIONS, 'api_ids': ['user_pool_id', 'rest_api_id']}},
            'network': {'network': NETWORK_16},
            'api': {'api': {
                'resources': 7, 'inventory_sha256': 'baaaad68febd893ec6f016b2fc587224bcca84e3423b8d779bbd85b357b0347a',
                'operations': STEP2_TEARDOWN_OPERATIONS, 'api_ids': ['user_pool_id', 'rest_api_id']}},
        },
    },
    'fe3588082dee12c8ef5f2401475f74df5db5421e8f52d6c71f0766fc8551e621': {
        'kind': 'representative', 'format': 'representative-gate-rows-v1',
        'operations': REPRESENTATIVE_OPERATIONS, 'records_counts': False, 'root_controls': False,
        'scenarios': {
            'aws_vpc.proof': {'representative-vpc-proof': {
                'resources': 1, 'inventory_sha256': 'fe26e2bfaf0782cf4a323fc148844335c86f928df50517491e67e27aa0f8406e',
                'operations': REPRESENTATIVE_OPERATIONS, 'api_ids': ['vpc_id']}},
        },
    },
}
ROOT_CONTROLS = ['9', '10', '11', '12', '13']
VPC_ID = re.compile(r'^vpc-[0-9a-f]{8,17}$')
API_ID_FORMATS = {
    'vpc_id': VPC_ID,
    'user_pool_id': re.compile(r'^[a-z]{2}(?:-[a-z]+)+-[0-9]_[A-Za-z0-9]{1,55}$'),
    'rest_api_id': re.compile(r'^[A-Za-z0-9]{1,32}$'),
}


def inventory_digest(addresses):
    return hashlib.sha256('\n'.join(sorted(addresses)).encode()).hexdigest()

# Text that may appear in an entry: printable ASCII without backslash, braces,
# angle brackets, backticks or control characters, one line.
SAFE_TEXT = re.compile(r'^[A-Za-z0-9 _.,;:/@()\[\]"=+#%&?!\'*-]*$')
DENY = [
    (re.compile(r'(?:AKIA|ASIA|AROA|AIDA)[A-Z0-9]{16}'), 'aws-access-key-id'),
    (re.compile(r'-----BEGIN|PRIVATE KEY'), 'private-key'),
    (re.compile(r'(?i)aws_secret_access_key|secret_access_key|x-amz-security-token|session_token'), 'aws-secret-field'),
    (re.compile(r'(?i)\bauthorization\s*:|\bbearer\s+[A-Za-z0-9]'), 'authorization-header'),
    (re.compile(r'gh[pousr]_[A-Za-z0-9]{20,}|github_pat_'), 'github-token'),
    (re.compile(r'eyJ[A-Za-z0-9_-]{10,}\.'), 'jwt'),
    (re.compile(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+\.[A-Za-z0-9.-]*[A-Za-z]{2,}'), 'email-address'),
    (re.compile(r'(?i)"?(?:lineage|serial|terraform_version)"?\s*[:=]|planned_values|resource_changes|prior_state|'
                r'resource_drift|"instances"'), 'state-or-plan-form'),
    (re.compile(r'(?i)password|passwd|client_secret|private_key|secret_string|SecretString'), 'secret-field'),
]
ACCOUNT = re.compile(r'(?<![0-9A-Za-z])[0-9]{12}(?![0-9A-Za-z])')
LONG_TOKEN = re.compile(r'[A-Za-z0-9+/=]{32,}')
HEX = re.compile(r'^(?:[0-9a-f]{40}|[0-9a-f]{64}|[0-9A-F]{40})$')
SHA = re.compile(r'^[0-9a-f]{40}$')
SHA256 = re.compile(r'^[0-9a-f]{64}$')
TIME = re.compile(r'^20[0-9]{2}-[01][0-9]-[0-3][0-9]T[0-2][0-9]:[0-5][0-9]:[0-5][0-9]Z$')
ROW = re.compile(r'^﻿?(20[0-9]{2}-[0-9]{2}-[0-9]{2}T[0-9:.]+Z) (\{"gate".*\})$')


class Invalid(Exception):
    """Rejected input or entry; the message is a stable label."""


def require(condition, label):
    if not condition:
        raise Invalid(label)


# ---------------------------------------------------------------- text safety

def check_text(value, label='text'):
    require(isinstance(value, str), label + '-type')
    require(len(value) <= MAX_TEXT, label + '-too-long')
    require(SAFE_TEXT.match(value) is not None, label + '-unsafe-characters')
    for pattern, name in DENY:
        require(pattern.search(value) is None, label + '-' + name)
    if not re.fullmatch(re.escape(RUN_URL) + r'[0-9]{1,20}(?:/job/[0-9]{1,20})?', value):
        for match in ACCOUNT.finditer(value):
            require(match.group(0) == '000000000000', label + '-real-account-id')
    for token in LONG_TOKEN.findall(value):
        mixed = re.search('[a-z]', token) and re.search('[A-Z]', token) and re.search('[0-9]', token)
        require(HEX.match(token) is not None or not mixed, label + '-opaque-token')
    return value


def walk_strings(value, label='entry'):
    if isinstance(value, str):
        check_text(value, label)
    elif isinstance(value, dict):
        for key, item in value.items():
            check_text(key, label + '-key')
            walk_strings(item, label)
    elif isinstance(value, list):
        require(len(value) <= MAX_LIST, label + '-list-too-long')
        for item in value:
            walk_strings(item, label)
    else:
        require(value is None or isinstance(value, (bool, int)), label + '-value-type')


# ---------------------------------------------------------------- schema

def exact_keys(obj, required, optional=(), label='keys'):
    require(isinstance(obj, dict), label + '-not-object')
    keys = set(obj)
    require(set(required) <= keys, label + '-missing')
    require(keys <= set(required) | set(optional), label + '-unknown')


def status_map(obj, names, label):
    exact_keys(obj, [], names, label)
    require(all(v in STATUSES for v in obj.values()), label + '-status')


def validate(entry, filename=None):
    """Validate one ledger entry; raise Invalid with a label on any problem."""
    raw = json.dumps(entry, sort_keys=True)
    require(len(raw.encode()) <= MAX_ENTRY_BYTES, 'entry-too-large')
    exact_keys(entry, ['schema', 'workflow', 'run', 'job', 'source', 'harvest', 'result', 'tested', 'controls',
                       'roots', 'out_of_scope_roots', 'cleanup', 'observations', 'untested', 'residual_risk',
                       'evidence_gaps'], label='entry')
    require(entry['schema'] == SCHEMA, 'schema')
    walk_strings(entry)

    workflow = entry['workflow']
    exact_keys(workflow, ['file', 'kind'], label='workflow')
    require(workflow['file'] in WORKFLOWS and WORKFLOWS[workflow['file']]['kind'] == workflow['kind'], 'workflow-known')

    run = entry['run']
    exact_keys(run, ['id', 'attempt', 'number', 'event', 'head_branch', 'head_sha', 'status', 'conclusion',
                     'created_at', 'updated_at', 'actor_is_repository_owner', 'triggering_actor_is_repository_owner',
                     'url'], label='run')
    require(isinstance(run['id'], int) and run['id'] > 0 and isinstance(run['attempt'], int) and run['attempt'] >= 1
            and isinstance(run['number'], int) and run['number'] >= 1, 'run-ids')
    require(run['event'] in ('push', 'workflow_dispatch'), 'run-event')
    require(SHA.match(run['head_sha']) is not None, 'run-head-sha')
    require(run['status'] == 'completed' and run['conclusion'] in ('success', 'failure', 'cancelled', 'skipped'),
            'run-completed')
    require(TIME.match(run['created_at']) and TIME.match(run['updated_at']) and run['created_at'] <= run['updated_at'],
            'run-times')
    require(isinstance(run['actor_is_repository_owner'], bool)
            and isinstance(run['triggering_actor_is_repository_owner'], bool), 'run-actor')
    require(run['url'] == RUN_URL + str(run['id']), 'run-url')
    if filename is not None:
        require(filename == '%d-attempt-%d.json' % (run['id'], run['attempt']), 'filename')

    job = entry['job']
    if job is not None:
        exact_keys(job, ['id', 'name', 'conclusion', 'runner_label', 'started_at', 'completed_at', 'url', 'steps'],
                   label='job')
        require(job['name'] == WORKFLOWS[workflow['file']]['job'], 'job-name')
        require(job['runner_label'] == 'ubuntu-24.04', 'job-runner')
        require(job['url'] == run['url'] + '/job/' + str(job['id']), 'job-url')
        require(TIME.match(job['started_at']) and TIME.match(job['completed_at'])
                and run['created_at'] <= job['started_at'] <= job['completed_at'] <= run['updated_at'], 'job-times')
        require(isinstance(job['steps'], list) and job['steps'], 'job-steps')
        numbers = []
        for step in job['steps']:
            exact_keys(step, ['number', 'name', 'conclusion'], label='step')
            require(step['conclusion'] in ('success', 'failure', 'skipped', 'cancelled'), 'step-conclusion')
            numbers.append(step['number'])
        require(numbers == sorted(set(numbers)), 'step-order')
        require(job['conclusion'] == run['conclusion'], 'job-conclusion')

    source = entry['source']
    exact_keys(source, ['log', 'log_lines', 'structured_rows', 'summary_record'], label='source')
    require(source['log'] in ('full', 'excerpt', 'unavailable'), 'source-log')
    require(isinstance(source['log_lines'], int) and isinstance(source['structured_rows'], int)
            and isinstance(source['summary_record'], bool), 'source-counts')
    require(job is not None or source['log'] == 'unavailable', 'source-without-job')

    harvest = entry['harvest']
    exact_keys(harvest, ['harvested_at', 'tool', 'registration'], label='harvest')
    require(TIME.match(harvest['harvested_at']) and harvest['tool'] == 'scripts/emulator-evidence/harvest.py'
            and harvest['registration'] in ('initial-backfill', 'regular'), 'harvest')
    require(harvest['harvested_at'] >= run['updated_at'], 'harvest-after-run')

    result = entry['result']
    exact_keys(result, ['overall', 'basis', 'failure'], label='result')
    require(result['overall'] in OVERALL, 'result-overall')
    require(result['basis'] in ('summary-record', 'gate-rows', 'run-metadata'), 'result-basis')
    if result['failure'] is not None:
        exact_keys(result['failure'], ['step', 'stage', 'diagnostic', 'cause'], label='failure')

    tested = entry['tested']
    exact_keys(tested, ['sha', 'harness', 'harness_sha256', 'harness_verified_against_git', 'required_operations',
                        'versions', 'scenario_id', 'scenario'], label='tested')
    require(tested['sha'] == run['head_sha'], 'tested-sha')
    require(tested['harness'] == WORKFLOWS[workflow['file']]['harness'], 'tested-harness')
    require(tested['harness_sha256'] is None or SHA256.match(tested['harness_sha256']), 'tested-harness-hash')
    require(isinstance(tested['harness_verified_against_git'], bool), 'tested-harness-verified')
    require(tested['versions'] is None or set(tested['versions']) == {'emulator', 'terraform', 'awscli', 'provider'},
            'tested-versions')
    vocabulary = STEP2_OPERATIONS if workflow['kind'] == 'step2-rehearsal' else REPRESENTATIVE_OPERATIONS
    required_ops = tested['required_operations']
    require(required_ops is None or (isinstance(required_ops, list) and required_ops
                                     and len(set(required_ops)) == len(required_ops)
                                     and set(required_ops) <= set(vocabulary)), 'tested-required-operations')

    status_map(entry['controls'], CONTROLS, 'controls')
    require(set(entry['controls']) == set(CONTROLS), 'controls-complete')

    names = set()
    for root in entry['roots']:
        exact_keys(root, ['name', 'kind', 'path', 'result', 'resources', 'resource_addresses', 'address_source',
                          'operations', 'api_ids', 'evidence', 'resource_cleanup'],
                   ['required_operations', 'controls'], label='root')
        require(root['kind'] in ('dev-root', 'disposable-adapter'), 'root-kind')
        if root['kind'] == 'dev-root':
            require(DEV_ROOTS.get(root['name']) == root['path'], 'root-mismatch')
        else:
            require(workflow['kind'] == 'representative' and root['path'] == 'scripts/emulator-verification/adapter',
                    'adapter-mismatch')
        require(root['result'] in STATUSES | {'INSUFFICIENT_EVIDENCE'}, 'root-result')
        require(isinstance(root['resources'], int) and len(root['resource_addresses']) == root['resources'],
                'root-resource-count')
        require(len(set(root['resource_addresses'])) == root['resources'], 'root-resource-duplicates')
        root_ops = root.get('required_operations', required_ops)
        require(root_ops is None or (isinstance(root_ops, list) and root_ops and len(set(root_ops)) == len(root_ops)
                                     and set(root_ops) <= set(vocabulary)), 'root-required-operations')
        status_map(root['operations'], root_ops or vocabulary, 'root-operations')
        if 'controls' in root:
            status_map(root['controls'], ROOT_CONTROLS, 'root-controls')
        exact_keys(root['api_ids'], [], list(API_ID_FORMATS), label='root-api-ids')
        require(all(isinstance(v, str) and API_ID_FORMATS[k].match(v) for k, v in root['api_ids'].items()),
                'root-api-id-format')
        evidence = root['evidence']
        exact_keys(evidence, ['plan_gate', 'plan_resources', 'api_owned_create', 'api_owned_update', 'inventory_sha256'],
                   label='root-evidence')
        require(evidence['plan_gate'] in STATUSES, 'root-evidence-plan-gate')
        require(all(evidence[k] is None or (isinstance(evidence[k], int) and not isinstance(evidence[k], bool))
                    for k in ('plan_resources', 'api_owned_create', 'api_owned_update')), 'root-evidence-counts')
        require(evidence['inventory_sha256'] == inventory_digest(root['resource_addresses']), 'root-inventory-digest')
        require(root['resource_cleanup'] in STATUSES, 'root-cleanup')
        require(root['name'] not in names, 'root-duplicate')
        names.add(root['name'])
    for root in entry['out_of_scope_roots']:
        exact_keys(root, ['name', 'status', 'reason'], label='out-of-scope')
        require(root['name'] in DEV_ROOTS and root['name'] not in names, 'out-of-scope-root')
        require(root['status'] in ('NOT_TESTED', 'EMULATOR_COMPATIBILITY_BLOCKED'), 'out-of-scope-status')
        names.add(root['name'])
    require(names >= set(DEV_ROOTS), 'roots-not-accounted')

    cleanup = entry['cleanup']
    exact_keys(cleanup, ['resources', 'material', 'process', 'host'], label='cleanup')
    require(all(v in STATUSES for v in cleanup.values()), 'cleanup-status')
    for key in ('observations', 'untested', 'residual_risk', 'evidence_gaps'):
        require(isinstance(entry[key], list), key + '-list')

    # Invariants: success is never inferred.
    if result['overall'] == 'PASS':
        require(run['conclusion'] == 'success' and job is not None and job['conclusion'] == 'success', 'pass-needs-success')
        require(source['log'] == 'full' and result['failure'] is None, 'pass-needs-full-log')
        require(all(v == 'PASS' for v in entry['controls'].values()), 'pass-needs-all-controls')
        require(tested['harness_verified_against_git'] and tested['versions'] is not None, 'pass-needs-verified-harness')
        pinned = KNOWN_HARNESSES.get(tested['harness_sha256'])
        require(pinned is not None and pinned['kind'] == workflow['kind'], 'pass-unknown-harness')
        require(required_ops == pinned['operations'], 'pass-required-operations-mismatch')
        scenario = pinned['scenarios'].get(tested['scenario_id'])
        require(scenario is not None, 'pass-unknown-scenario')
        require(sorted(r['name'] for r in entry['roots']) == sorted(scenario), 'pass-root-scope')
        for r in entry['roots']:
            spec = scenario[r['name']]
            require(r.get('required_operations', required_ops) == spec['operations'], 'pass-required-operations-mismatch')
            require(r['result'] == 'PASS' and r['resource_cleanup'] == 'PASS'
                    and list(r['operations']) and set(r['operations']) == set(spec['operations'])
                    and all(v == 'PASS' for v in r['operations'].values()), 'pass-needs-every-operation')
            require(r['resources'] == spec['resources']
                    and r['evidence']['inventory_sha256'] == spec['inventory_sha256'], 'pass-inventory-mismatch')
            ev = r['evidence']
            require(ev['plan_gate'] == 'PASS', 'pass-needs-plan-evidence')
            if pinned['records_counts']:
                require(ev['plan_resources'] == r['resources'], 'pass-needs-plan-evidence')
                require(ev['api_owned_create'] == r['resources'] and ev['api_owned_update'] == r['resources'],
                        'pass-needs-api-evidence')
            require(all(k in r['api_ids'] for k in spec['api_ids']), 'pass-needs-api-id')
            if pinned['root_controls']:
                require(set(r.get('controls') or {}) == set(ROOT_CONTROLS)
                        and all(v == 'PASS' for v in r['controls'].values()), 'pass-needs-root-controls')
        require(all(v == 'PASS' for v in cleanup.values()), 'pass-needs-cleanup')
        if workflow['kind'] == 'step2-rehearsal':
            require(source['summary_record'] and result['basis'] == 'summary-record', 'pass-needs-summary-record')
    else:
        require(result['failure'] is not None or result['overall'] == 'INSUFFICIENT_EVIDENCE', 'non-pass-needs-failure')
    if run['conclusion'] != 'success':
        require(result['overall'] != 'PASS', 'failed-run-not-pass')
    if not source['summary_record'] and result['basis'] != 'gate-rows':
        require(all(v == 'NOT_TESTED' for v in entry['controls'].values()), 'no-record-no-controls')
    if source['log'] != 'full':
        require(result['overall'] != 'PASS', 'partial-log-not-pass')
    return entry


# ---------------------------------------------------------------- log parsing

def parse_rows(text):
    """Structured gate rows emitted by the harness (timestamped JSON lines only)."""
    data = text.encode()
    require(len(data) <= MAX_LOG_BYTES, 'log-too-large')
    lines = text.splitlines()
    require(len(lines) <= MAX_LOG_LINES, 'log-too-many-lines')
    rows = []
    for line in lines:
        match = ROW.match(line)
        if not match:
            continue
        require(len(line.encode()) <= MAX_ROW_BYTES, 'row-too-large')
        try:
            row = json.loads(match.group(2))
        except ValueError:
            raise Invalid('row-not-json')
        require(isinstance(row, dict) and isinstance(row.get('gate'), str) and row.get('status') in STATUSES,
                'row-shape')
        require(re.fullmatch(r'[a-z0-9_-]{1,80}', row['gate']) is not None, 'row-gate-name')
        rows.append(row)
    return rows, len(lines)


def git_show(repo, sha, path):
    if repo is None:
        return None
    try:
        return subprocess.run(['git', '-C', str(repo), 'show', sha + ':' + path], check=True, capture_output=True,
                              timeout=30).stdout
    except (subprocess.SubprocessError, OSError):
        return None


class Literal(ast.NodeVisitor):
    """Evaluate the reviewed literals of a harness file without running it.

    Only constants, names already evaluated, string concatenation, f-strings,
    list/set/tuple/dict displays (with ** unpacking), single-generator dict
    comprehensions (optionally over NAME.items() and with in/not in filters)
    and dict()/set()/list() of one argument are understood. Anything else is
    refused, so no harness code ever runs.
    """

    def __init__(self, names):
        self.names = names

    def value(self, node):
        if isinstance(node, ast.Constant) and isinstance(node.value, (str, int, bool, type(None))):
            return node.value
        if isinstance(node, ast.Name) and node.id in self.names:
            return self.names[node.id]
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            left, right = self.value(node.left), self.value(node.right)
            require(isinstance(left, str) and isinstance(right, str), 'inventory-literal')
            return left + right
        if isinstance(node, ast.JoinedStr):
            return ''.join(self.value(v.value) if isinstance(v, ast.FormattedValue) else self.value(v)
                           for v in node.values)
        if isinstance(node, (ast.List, ast.Set, ast.Tuple)):
            return [self.value(e) for e in node.elts]
        if isinstance(node, ast.Dict):
            out = {}
            for key, val in zip(node.keys, node.values):
                if key is None:
                    out.update(self.value(val))
                else:
                    out[self.value(key)] = self.value(val)
            return out
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in ('dict', 'set', 'list') \
                and len(node.args) == 1 and not node.keywords:
            inner = self.value(node.args[0])
            require(isinstance(inner, (dict, list)), 'inventory-literal')
            return dict(inner) if node.func.id == 'dict' else list(inner)
        if isinstance(node, ast.DictComp) and len(node.generators) == 1:
            gen = node.generators[0]
            out = {}
            for item in self.iterate(gen.iter):
                inner = Literal(dict(self.names, **self.bind(gen.target, item)))
                if all(inner.condition(c) for c in gen.ifs):
                    out[inner.value(node.key)] = inner.value(node.value)
            return out
        raise Invalid('inventory-literal')

    def iterate(self, node):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == 'items' \
                and not node.args and not node.keywords:
            mapping = self.value(node.func.value)
            require(isinstance(mapping, dict), 'inventory-comprehension')
            return list(mapping.items())
        items = self.value(node)
        require(isinstance(items, list), 'inventory-comprehension')
        return items

    def bind(self, target, item):
        if isinstance(target, ast.Name):
            return {target.id: item}
        require(isinstance(target, ast.Tuple) and all(isinstance(e, ast.Name) for e in target.elts)
                and isinstance(item, (tuple, list)) and len(item) == len(target.elts), 'inventory-comprehension')
        return {e.id: v for e, v in zip(target.elts, item)}

    def condition(self, node):
        require(isinstance(node, ast.Compare) and len(node.ops) == 1 and isinstance(node.ops[0], (ast.In, ast.NotIn)),
                'inventory-comprehension')
        member = self.value(node.left) in self.value(node.comparators[0])
        return member if isinstance(node.ops[0], ast.In) else not member


def module_literals(source):
    """Every module-level assignment of a harness that Literal can evaluate, in order."""
    names = {}
    for node in ast.parse(source).body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        try:
            if isinstance(target, ast.Name):
                names[target.id] = Literal(names).value(node.value)
            elif isinstance(target, ast.Tuple) and all(isinstance(e, ast.Name) for e in target.elts) \
                    and isinstance(node.value, ast.Tuple) and len(node.value.elts) == len(target.elts):
                values = [Literal(names).value(v) for v in node.value.elts]
                names.update({e.id: v for e, v in zip(target.elts, values)})
        except (Invalid, TypeError, ValueError):
            continue
    return names


def step2_v2_spec(source):
    """Roots, inventories and operations of the multi-root harness (PR #75 format)."""
    names = module_literals(source)
    require({'SCENARIOS', 'ALL', 'OPERATIONS'} <= set(names), 'v2-spec-missing')
    require(isinstance(names['ALL'], list) and isinstance(names['OPERATIONS'], list), 'v2-spec-shape')
    scenarios = {}
    for sid, spec in names['SCENARIOS'].items():
        require(isinstance(spec, dict) and isinstance(spec.get('root'), str) and isinstance(spec.get('expected'), dict),
                'v2-spec-scenario')
        scenarios[sid] = {'root': spec['root'], 'addresses': sorted(spec['expected']), 'teardown': 'teardown' in spec}
    require(set(names['ALL']) <= set(scenarios), 'v2-spec-all')
    return {'ALL': list(names['ALL']), 'OPERATIONS': list(names['OPERATIONS']), 'scenarios': scenarios}


def with_teardown(operations):
    ops = list(operations)
    require('destroy_plan' in ops, 'v2-spec-operations')
    position = ops.index('destroy_plan')
    return ops[:position] + ['teardown_plan', 'teardown'] + ops[position:]


def step2_inventory(source, scenario_id):
    names = module_literals(source)
    require({'M', 'EXPECTED', 'ENDPOINT_TYPES'} <= set(names), 'inventory-missing')
    expected = names['EXPECTED']
    require(isinstance(expected, dict), 'inventory-missing')
    if scenario_id == 'no-interface-endpoints':
        return sorted(a for a, kind in expected.items() if kind not in set(names['ENDPOINT_TYPES']))
    require(scenario_id == 'full', 'inventory-scenario')
    return sorted(expected)


def operations_literal(source):
    """The module-level OPERATIONS list of a harness file, evaluated without running it."""
    value = module_literals(source).get('OPERATIONS')
    require(value is not None, 'operations-missing')
    require(isinstance(value, list) and value and all(isinstance(v, str) for v in value), 'operations-literal')
    return value


def adapter_inventory(source):
    text = source.decode()
    found = re.findall(r'^resource\s+"([a-z0-9_]+)"\s+"([a-z0-9_]+)"', text, re.M)
    require(found and not re.search(r'^(?:module|data)\s+"', text, re.M), 'adapter-inventory')
    return sorted(t + '.' + n for t, n in found)


# ---------------------------------------------------------------- metadata

def check_meta(meta):
    exact_keys(meta, ['workflow', 'run', 'job', 'log'], label='meta')
    require(meta['workflow'] in WORKFLOWS, 'meta-workflow')
    walk_strings(meta, 'meta')
    exact_keys(meta['log'], ['kind', 'lines'], label='meta-log')
    require(meta['log']['kind'] in ('full', 'excerpt', 'unavailable'), 'meta-log-kind')


def step_names_in_workflow(repo, meta):
    """Every non-synthetic step name must exist in the workflow file at the run's SHA."""
    source = git_show(repo, meta['run']['head_sha'], meta['workflow'])
    if source is None:
        return False
    text = source.decode()
    for step in meta['job']['steps']:
        name = step['name']
        if name in SYNTHETIC_STEPS:
            continue
        name = name[len('Post '):] if name.startswith('Post ') else name
        require(re.search(r'^\s*-?\s*name:\s*' + re.escape(name) + r'\s*$', text, re.M) is not None,
                'meta-step-not-in-workflow')
    return True


def first_failed_step(job):
    for step in (job or {}).get('steps', []):
        if step['conclusion'] == 'failure':
            return step['name']
    return None


# ---------------------------------------------------------------- harvesting

COMMON_UNTESTED = [
    'Real AWS behavior, IAM enforcement, networking, DNS, cost, quotas and availability: never tested by an emulator',
]
OUT_OF_SCOPE = {
    'network': 'NOT_TESTED in this run',
    'platform': 'NOT_TESTED: security group gap expected; EKS and AMI paths untested',
    'api': 'NOT_TESTED in a formal run',
    'serverless-api': 'NOT_TESTED: S3 Control gap expected',
    'developer-access': 'NOT_TESTED: security group gap expected',
    'tfstate': 'EMULATOR_COMPATIBILITY_BLOCKED: S3 Control account-ID host prefix not served under strict TLS',
}


def out_of_scope(exclude):
    rows = []
    for name in sorted(DEV_ROOTS):
        if name in exclude:
            continue
        reason = OUT_OF_SCOPE[name]
        status = 'EMULATOR_COMPATIBILITY_BLOCKED' if reason.startswith('EMULATOR_COMPATIBILITY_BLOCKED') else 'NOT_TESTED'
        rows.append({'name': name, 'status': status, 'reason': reason})
    return rows


def base_entry(meta, harvested_at, log_kind, log_lines, rows, has_record, registration='regular'):
    run, job = meta['run'], meta['job']
    return {
        'schema': SCHEMA,
        'workflow': {'file': meta['workflow'], 'kind': WORKFLOWS[meta['workflow']]['kind']},
        'run': dict(run, url=RUN_URL + str(run['id'])),
        'job': None if job is None else dict(job, url=RUN_URL + str(run['id']) + '/job/' + str(job['id'])),
        'source': {'log': log_kind, 'log_lines': log_lines, 'structured_rows': len(rows), 'summary_record': has_record},
        'harvest': {'harvested_at': harvested_at, 'tool': 'scripts/emulator-evidence/harvest.py',
                    'registration': registration},
        'result': None,
        'tested': {'sha': run['head_sha'], 'harness': WORKFLOWS[meta['workflow']]['harness'], 'harness_sha256': None,
                   'harness_verified_against_git': False, 'required_operations': None, 'versions': None,
                   'scenario_id': None, 'scenario': None},
        'controls': {k: 'NOT_TESTED' for k in CONTROLS},
        'roots': [],
        'out_of_scope_roots': [],
        'cleanup': {'resources': 'NOT_TESTED', 'material': 'NOT_TESTED', 'process': 'NOT_TESTED', 'host': 'NOT_TESTED'},
        'observations': [],
        'untested': list(COMMON_UNTESTED),
        'residual_risk': [],
        'evidence_gaps': [],
    }


def completeness_gaps(required, operations, pinned, scenario_id, addresses, evidence, api_ids, root=None,
                      root_required=None, root_controls=None):
    """Reasons why measured results cannot support PASS (empty when complete)."""
    gaps = []
    prefix = root + ': ' if root else ''
    effective = root_required if root_required is not None else required
    if effective is None:
        gaps.append(prefix + 'Required operations unknown: the harness operation list at the tested SHA is not available')
    else:
        missing = [op for op in effective if op not in operations]
        extra = [op for op in operations if op not in effective]
        if missing:
            gaps.append(prefix + 'Required operations not recorded: ' + ', '.join(missing))
        if extra:
            gaps.append(prefix + 'Operations outside the harness list: ' + ', '.join(extra))
    if pinned is None:
        gaps.append('Harness version not pinned in harvest.py KNOWN_HARNESSES: PASS cannot be recorded')
        return gaps
    if required is not None and required != pinned['operations']:
        gaps.append('Harness operation list differs from the pinned list')
    scenario = pinned['scenarios'].get(scenario_id)
    if scenario is None:
        gaps.append('Scenario not pinned for this harness version')
        return gaps
    name = root if root is not None else (next(iter(scenario)) if len(scenario) == 1 else None)
    spec = scenario.get(name)
    if spec is None:
        gaps.append(prefix + 'Root not pinned for this scenario')
        return gaps
    if effective is not None and effective != spec['operations']:
        gaps.append(prefix + 'Root operation list differs from the pinned list')
    if len(addresses) != spec['resources'] or inventory_digest(addresses) != spec['inventory_sha256']:
        gaps.append(prefix + 'Resource inventory differs from the pinned inventory of the scenario')
    if evidence['plan_gate'] != 'PASS':
        gaps.append(prefix + 'Plan gate evidence missing')
    if pinned['records_counts']:
        if evidence['plan_resources'] != len(addresses):
            gaps.append(prefix + 'Plan resource count missing or different from the inventory')
        if evidence['api_owned_create'] != len(addresses) or evidence['api_owned_update'] != len(addresses):
            gaps.append(prefix + 'Independent API identity counts missing or different from the inventory')
    for key in spec['api_ids']:
        if key not in api_ids:
            gaps.append(prefix + 'Independent API resource ID missing: ' + key)
    if pinned['root_controls'] and set(root_controls or {}) != set(ROOT_CONTROLS):
        gaps.append(prefix + 'Per-root controls 9 to 13 not recorded')
    return gaps


RECORD_KEYS = {'run_id', 'tested_sha', 'harness_sha256', 'execution', 'scenario', 'versions', 'controls',
               'operations', 'resource_cleanup', 'material_cleanup', 'process_cleanup', 'unsupported_apis',
               'scenario_id', 'notes', 'failure'}
EXECUTION_KEYS = {'kind', 'repository', 'workflow_ref', 'event', 'run_id', 'run_attempt', 'run_url', 'runner'}
PROBE_KEYS = {'egress_rules', 'ingress_rules', 'ip_permissions_egress', 'revoke_provider_form_ports_0',
              'revoke_without_ports', 'egress_rules_after', 'stored_default_rule', 'interface_endpoint'}


def harvest_step2_record(entry, meta, rows, repo):
    run = meta['run']
    records = [r for r in rows if r['gate'] == 'summary-record']
    require(len(records) == 1, 'summary-record-count')
    record = records[0].get('record')
    multi = isinstance(record, dict) and 'roots' in record
    require(isinstance(record, dict) and set(record) <= (V2_RECORD_KEYS if multi else RECORD_KEYS), 'summary-record-keys')
    execution = record.get('execution') or {}
    require(set(execution) <= EXECUTION_KEYS, 'summary-execution-keys')
    require(record.get('run_id') == '%d-%d' % (run['id'], run['attempt'])
            and execution.get('run_id') == str(run['id']) and execution.get('run_attempt') == str(run['attempt'])
            and execution.get('kind') == 'github-actions' and execution.get('repository') == REPOSITORY
            and execution.get('workflow_ref') == REPOSITORY + '/' + meta['workflow'] + '@refs/heads/main'
            and execution.get('run_url') == RUN_URL + str(run['id']), 'summary-identity')
    require(record.get('tested_sha') == run['head_sha'], 'summary-tested-sha')
    if 'event' in execution:
        require(execution['event'] == run['event'], 'summary-event')
    versions = record.get('versions')
    require(isinstance(versions, dict) and set(versions) == {'emulator', 'terraform', 'awscli', 'provider'}, 'summary-versions')
    controls = record.get('controls')
    require(isinstance(controls, dict) and set(controls) == set(CONTROLS)
            and all(v in STATUSES for v in controls.values()), 'summary-controls')
    harness = git_show(repo, run['head_sha'], WORKFLOWS[meta['workflow']]['harness'])
    verified = harness is not None and hashlib.sha256(harness).hexdigest() == record.get('harness_sha256')
    require(harness is None or verified, 'summary-harness-hash-mismatch')
    if multi:
        harvest_step2_multi_root(entry, meta, rows, record, versions, controls, harness if verified else None)
        return
    operations = record.get('operations')
    require(isinstance(operations, dict) and set(operations) <= set(STEP2_OPERATIONS)
            and all(v in STATUSES for v in operations.values()), 'summary-operations')
    scenario_id = record.get('scenario_id')
    require(scenario_id in ('no-interface-endpoints', 'full'), 'summary-scenario')
    required = operations_literal(harness.decode()) if verified else None
    pinned = KNOWN_HARNESSES.get(record.get('harness_sha256')) if verified else None
    entry['tested'].update(harness_sha256=record.get('harness_sha256'), harness_verified_against_git=verified,
                           required_operations=required, versions=dict(versions), scenario_id=scenario_id,
                           scenario=record.get('scenario'))
    entry['controls'] = dict(controls)

    plan = [r for r in rows if r['gate'] == 'plan']
    created = [r for r in rows if r['gate'] == 'api-identity-create']
    updated = [r for r in rows if r['gate'] == 'api-identity-updated']
    addresses = step2_inventory(harness.decode(), scenario_id) if verified else []
    if plan and verified:
        require(plan[-1].get('resources') == len(addresses), 'summary-plan-count')
    for row in created + updated:
        if verified:
            require(row.get('owned') == len(addresses), 'summary-owned-count')
    api_ids = {}
    vpc_ids = {r.get('vpc_id') for r in created + updated if r.get('vpc_id')}
    if vpc_ids:
        require(len(vpc_ids) == 1 and VPC_ID.match(next(iter(vpc_ids))), 'summary-vpc-id')
        api_ids['vpc_id'] = next(iter(vpc_ids))

    def count(rows_, key):
        value = rows_[-1].get(key) if rows_ else None
        return value if isinstance(value, int) and not isinstance(value, bool) else None
    evidence = {'plan_gate': plan[-1]['status'] if plan else 'NOT_TESTED', 'plan_resources': count(plan, 'resources'),
                'api_owned_create': count(created, 'owned'), 'api_owned_update': count(updated, 'owned'),
                'inventory_sha256': inventory_digest(addresses)}
    resource_cleanup = record.get('resource_cleanup', 'NOT_TESTED')
    measured_fail = record.get('failure') is not None or resource_cleanup != 'PASS' \
        or any(v != 'PASS' for v in controls.values()) or any(v != 'PASS' for v in operations.values())
    gaps = completeness_gaps(required, operations, pinned, scenario_id, addresses, evidence, api_ids)
    ok = not measured_fail and not gaps and run['conclusion'] == 'success'
    entry['roots'] = [{
        'name': 'network', 'kind': 'dev-root', 'path': DEV_ROOTS['network'],
        'result': 'PASS' if ok else 'FAIL' if measured_fail else 'INSUFFICIENT_EVIDENCE',
        'resources': len(addresses), 'resource_addresses': addresses,
        'address_source': ('reviewed inventory EXPECTED and expected_for() in scripts/emulator-rehearsal/rehearse.py at '
                           'the tested SHA, whose SHA-256 equals the run harness_sha256; the plan gate requires exactly '
                           'this inventory' if verified else 'harness not verifiable against git'),
        'operations': dict(operations), 'api_ids': api_ids, 'evidence': evidence, 'resource_cleanup': resource_cleanup}]
    entry['evidence_gaps'].extend(gaps)
    if not verified:
        entry['evidence_gaps'].append('Harness source at the tested SHA not available: resource addresses not recorded')
    entry['out_of_scope_roots'] = out_of_scope({'network'})
    host = [r['status'] for r in rows if r['gate'] == 'host-cleanup']
    entry['cleanup'] = {'resources': resource_cleanup, 'material': record.get('material_cleanup', 'NOT_TESTED'),
                        'process': record.get('process_cleanup', 'NOT_TESTED'),
                        'host': host[-1] if len(host) == 1 else 'NOT_TESTED'}
    if len(host) != 1:
        entry['evidence_gaps'].append('Host cleanup row missing or duplicated')
    for note in record.get('notes') or []:
        probe = note.get('security_group_probe') if isinstance(note, dict) else None
        if probe is not None:
            require(set(probe) <= PROBE_KEYS, 'summary-probe-keys')
            endpoint = probe.get('interface_endpoint') or {}
            entry['observations'].append(
                'Security group probe (direct API, not Terraform): provider-form default egress revoke with ports 0 '
                'returned ' + str(probe.get('revoke_provider_form_ports_0')) + '; revoke without ports '
                + str(probe.get('revoke_without_ports')))
            entry['observations'].append(
                'Interface endpoint probe (direct API, not Terraform): create ' + str(endpoint.get('create'))
                + ', state ' + str(endpoint.get('state')) + ', delete ' + str(endpoint.get('delete')))
    for row in rows:
        if row['gate'] == 'refresh-convergence' and row.get('drift'):
            entry['observations'].append(
                'Refresh: reviewed computed-field convergence on '
                + ', '.join(sorted(d.get('address', '?') for d in row['drift'])) + '; second refresh unchanged')
        if row['gate'] == 'auth-reject-secret' or row['gate'] == 'auth-reject-access':
            entry['observations'].append('Authentication probe ' + row['gate'] + ': ' + str(row.get('code')))
        if row['gate'] == 'external-probe-errno':
            results = row.get('results') or {}
            entry['observations'].append('Real AWS endpoint probes: ' + ', '.join(
                k + ' ' + '/'.join(v) for k, v in sorted(results.items())))
    if scenario_id == 'no-interface-endpoints':
        entry['untested'].append('network: the endpoint security group, its rule and the 8 interface endpoints through '
                                 'Terraform (emulator default egress revoke gap)')
    entry['untested'].append('Packet forwarding, NAT, routing, DNS resolution and endpoint reachability: the emulator '
                             'models API state only')
    entry['residual_risk'].append('The refresh allowlist is a reviewed judgment that the observed computed-field '
                                  'convergence is normal; it is covered by offline mutation tests')
    if ok:
        entry['result'] = {'overall': 'PASS', 'basis': 'summary-record', 'failure': None}
    elif not measured_fail:
        entry['result'] = {'overall': 'INSUFFICIENT_EVIDENCE', 'basis': 'summary-record', 'failure': {
            'step': first_failed_step(meta['job']), 'stage': 'evidence completeness', 'diagnostic': 'EVIDENCE_INCOMPLETE',
            'cause': 'the record cannot support PASS; see evidence_gaps'}}
    else:
        failure = record.get('failure') or {}
        entry['result'] = {'overall': 'FAIL', 'basis': 'summary-record', 'failure': {
            'step': first_failed_step(meta['job']), 'stage': failure.get('operation') if isinstance(failure, dict) else None,
            'diagnostic': failure.get('label') if isinstance(failure, dict) else None,
            'cause': 'recorded by the harness summary record'}}


V2_RECORD_KEYS = {'run_id', 'tested_sha', 'harness_sha256', 'execution', 'scenario_id', 'scenario', 'versions',
                  'controls', 'roots', 'known_gaps', 'material_cleanup', 'process_cleanup', 'notes', 'failure'}
V2_ROOT_KEYS = {'description', 'resources', 'status', 'operations', 'controls', 'resource_cleanup', 'unsupported_apis',
                'failure'}
V2_IDENTITY_FIELDS = {'vpc_id': 'vpc_id', 'user_pool': 'user_pool_id', 'rest_api': 'rest_api_id'}
SEVERITY = ['BLOCKED', 'FAIL', 'PARTIAL-SKIP']


def segment_rows(rows):
    """Attribute gate rows to roots: a row names its root, or follows the latest root-start until root-result."""
    segments, current = {}, None
    for row in rows:
        if row['gate'] == 'root-start':
            require(isinstance(row.get('root'), str) and row['root'] in DEV_ROOTS, 'root-start-name')
            current = row['root']
        name = row.get('root', current)
        if isinstance(name, str):
            segments.setdefault(name, []).append(row)
        if row['gate'] == 'root-result':
            current = None
    return segments


def unique(items):
    out = []
    for item in items:
        if item not in out:
            out.append(item)
    return out


def harvest_step2_multi_root(entry, meta, rows, record, versions, controls, harness):
    """The multi-root summary-record of the consolidated harness (PR #75): one entry, one root per rehearsed root."""
    run = meta['run']
    roots_record = record.get('roots')
    require(isinstance(roots_record, dict) and roots_record and all(n in DEV_ROOTS for n in roots_record),
            'summary-roots')
    scenario_id = record.get('scenario_id')
    spec = step2_v2_spec(harness.decode()) if harness is not None else None
    if spec is not None:
        require(scenario_id == 'all' or scenario_id in spec['scenarios'], 'summary-scenario')
        expected_roots = spec['ALL'] if scenario_id == 'all' else [scenario_id]
        require(sorted(roots_record) == sorted(expected_roots), 'summary-roots-scope')
    else:
        require(isinstance(scenario_id, str) and re.fullmatch(r'[a-z-]{1,40}', scenario_id), 'summary-scenario')
        expected_roots = sorted(roots_record)
    required = spec['OPERATIONS'] if spec is not None else None
    pinned = KNOWN_HARNESSES.get(record.get('harness_sha256')) if harness is not None else None
    if pinned is not None:
        require(pinned['kind'] == 'step2-rehearsal' and pinned['format'] == 'step2-multi-root-v2', 'summary-format')
    entry['tested'].update(harness_sha256=record.get('harness_sha256'), harness_verified_against_git=harness is not None,
                           required_operations=required, versions=dict(versions), scenario_id=scenario_id,
                           scenario=record.get('scenario'))
    entry['controls'] = dict(controls)
    known = record.get('known_gaps') or {}
    require(isinstance(known, dict) and all(isinstance(v, str) for v in known.values()), 'summary-known-gaps')
    segments = segment_rows(rows)
    measured_fail = record.get('failure') is not None or any(v != 'PASS' for v in controls.values()) \
        or record.get('material_cleanup') != 'PASS' or record.get('process_cleanup') != 'PASS'
    gaps, statuses, failure_root = [], [], None
    for name in expected_roots:
        rr = roots_record[name]
        require(isinstance(rr, dict) and set(rr) <= V2_ROOT_KEYS, 'summary-root-keys')
        ops = rr.get('operations')
        require(isinstance(ops, dict) and set(ops) <= set(STEP2_OPERATIONS)
                and all(v in STATUSES for v in ops.values()), 'summary-root-operations')
        root_controls = rr.get('controls') or {}
        require(isinstance(root_controls, dict) and set(root_controls) <= set(ROOT_CONTROLS)
                and all(v in STATUSES for v in root_controls.values()), 'summary-root-controls')
        status, cleanup = rr.get('status'), rr.get('resource_cleanup', 'NOT_TESTED')
        require(status in STATUSES and cleanup in STATUSES, 'summary-root-status')
        scenario = spec['scenarios'].get(name) if spec is not None else None
        if spec is not None:
            require(scenario is not None and scenario['root'] == DEV_ROOTS[name], 'summary-root-path')
        addresses = scenario['addresses'] if scenario is not None else []
        root_required = (with_teardown(required) if scenario['teardown'] else list(required)) if scenario else None
        if scenario is not None:
            require(rr.get('resources') == len(addresses), 'summary-root-resources')
        segment = segments.get(name, [])
        plan = [r for r in segment if r['gate'] == 'plan']
        created = [r for r in segment if r['gate'] == 'api-identity-create']
        updated = [r for r in segment if r['gate'] == 'api-identity-updated']
        if scenario is not None:
            if plan:
                require(plan[-1].get('resources') == len(addresses), 'summary-plan-count')
            for row in created + updated:
                require(row.get('owned') == len(addresses), 'summary-owned-count')
        api_ids = {}
        for field, key in V2_IDENTITY_FIELDS.items():
            values = {r.get(field) for r in created + updated if r.get(field) is not None}
            if values:
                value = next(iter(values))
                require(len(values) == 1 and isinstance(value, str) and API_ID_FORMATS[key].match(value), 'summary-api-id')
                api_ids[key] = value

        def count(rows_, key):
            value = rows_[-1].get(key) if rows_ else None
            return value if isinstance(value, int) and not isinstance(value, bool) else None
        evidence = {'plan_gate': plan[-1]['status'] if plan else 'NOT_TESTED', 'plan_resources': count(plan, 'resources'),
                    'api_owned_create': count(created, 'owned'), 'api_owned_update': count(updated, 'owned'),
                    'inventory_sha256': inventory_digest(addresses)}
        root_fail = status != 'PASS' or cleanup != 'PASS' or rr.get('failure') is not None \
            or any(v != 'PASS' for v in ops.values()) or any(v != 'PASS' for v in root_controls.values())
        measured_fail = measured_fail or root_fail
        if root_fail and status in SEVERITY:
            statuses.append(status)
            failure_root = failure_root or (name, rr.get('failure'))
        root_gaps = completeness_gaps(required, ops, pinned, scenario_id, addresses, evidence, api_ids, root=name,
                                      root_required=root_required, root_controls=root_controls)
        gaps.extend(root_gaps)
        entry['roots'].append({
            'name': name, 'kind': 'dev-root', 'path': DEV_ROOTS[name],
            'result': (status if status != 'PASS' else 'FAIL') if root_fail
            else 'INSUFFICIENT_EVIDENCE' if root_gaps else 'PASS',
            'resources': len(addresses), 'resource_addresses': addresses,
            'address_source': ('reviewed inventory SCENARIOS[' + name + '] in scripts/emulator-rehearsal/rehearse.py at the '
                               'tested SHA, whose SHA-256 equals the run harness_sha256; the plan gate requires exactly '
                               'this inventory' if scenario is not None else 'harness not verifiable against git'),
            'operations': dict(ops), 'api_ids': api_ids, 'evidence': evidence, 'resource_cleanup': cleanup,
            'required_operations': root_required, 'controls': dict(root_controls)})
        if root_required is None:
            del entry['roots'][-1]['required_operations']
    entry['evidence_gaps'].extend(unique(gaps))
    if harness is None:
        entry['evidence_gaps'].append('Harness source at the tested SHA not available: resource addresses not recorded')
    out = []
    for item in out_of_scope(set(expected_roots)):
        if item['name'] in known:
            item['reason'] = (item['status'] + ': known gap reported by the harness: ' + known[item['name']])[:MAX_TEXT]
        out.append(item)
    entry['out_of_scope_roots'] = out
    host = [r['status'] for r in rows if r['gate'] == 'host-cleanup']
    root_cleanups = [r['resource_cleanup'] for r in entry['roots']]
    entry['cleanup'] = {'resources': 'PASS' if root_cleanups and all(c == 'PASS' for c in root_cleanups)
                        else 'FAIL' if 'FAIL' in root_cleanups else 'NOT_TESTED',
                        'material': record.get('material_cleanup', 'NOT_TESTED'),
                        'process': record.get('process_cleanup', 'NOT_TESTED'),
                        'host': host[-1] if len(host) == 1 else 'NOT_TESTED'}
    if len(host) != 1:
        entry['evidence_gaps'].append('Host cleanup row missing or duplicated')
    for note in record.get('notes') or []:
        probe = note.get('security_group_probe') if isinstance(note, dict) else None
        if probe is not None:
            require(set(probe) <= PROBE_KEYS, 'summary-probe-keys')
            entry['observations'].append(
                'Security group probe (direct API, not Terraform): provider-form default egress revoke with ports 0 '
                'returned ' + str(probe.get('revoke_provider_form_ports_0')) + '; revoke without ports '
                + str(probe.get('revoke_without_ports')))
    for row in rows:
        if row['gate'] == 'refresh-convergence' and row.get('drift'):
            entry['observations'].append(
                'Refresh (' + str(row.get('root', 'network')) + '): reviewed computed-field convergence on '
                + ', '.join(sorted(d.get('address', '?') for d in row['drift'])) + '; second refresh unchanged')
        if row['gate'] in ('auth-reject-secret', 'auth-reject-access'):
            entry['observations'].append('Authentication probe ' + row['gate'] + ': ' + str(row.get('code')))
        if row['gate'] == 'external-probe-errno':
            results = row.get('results') or {}
            entry['observations'].append('Real AWS endpoint probes: ' + ', '.join(
                k + ' ' + '/'.join(v) for k, v in sorted(results.items())))
    if 'network-full' in known:
        entry['untested'].append(('network: the endpoint security group, its rule and the interface endpoints through '
                                  'Terraform (known gap: ' + known['network-full'] + ')')[:MAX_TEXT])
    entry['untested'].append('Packet forwarding, NAT, routing, DNS resolution, Cognito sign-in and REST API invocation: '
                             'the emulator models API state only')
    entry['residual_risk'].append('The refresh allowlists are reviewed judgments that the observed computed-field '
                                  'convergence is normal; they are covered by offline mutation tests')
    if not measured_fail and not gaps and run['conclusion'] == 'success':
        entry['result'] = {'overall': 'PASS', 'basis': 'summary-record', 'failure': None}
    elif not measured_fail:
        entry['result'] = {'overall': 'INSUFFICIENT_EVIDENCE', 'basis': 'summary-record', 'failure': {
            'step': first_failed_step(meta['job']), 'stage': 'evidence completeness', 'diagnostic': 'EVIDENCE_INCOMPLETE',
            'cause': 'the record cannot support PASS; see evidence_gaps'}}
    else:
        overall = next((s for s in SEVERITY if s in statuses), 'BLOCKED' if record.get('failure') else 'FAIL')
        failure = (failure_root[1] if failure_root else record.get('failure')) or {}
        entry['result'] = {'overall': overall, 'basis': 'summary-record', 'failure': {
            'step': first_failed_step(meta['job']),
            'stage': ((failure_root[0] + ': ') if failure_root else '') + str(failure.get('operation', 'unknown'))
            if isinstance(failure, dict) else None,
            'diagnostic': failure.get('label') if isinstance(failure, dict) else None,
            'cause': 'recorded by the harness summary record'}}


REP_ROW_KEYS = {'gate', 'status', 'diagnostic', 'exit_code', 'resource_id', 'api', 'sha', 'run_id', 'emulator',
                'terraform', 'awscli', 'provider', 'package_sha256', 'publisher', 'awscli_sha256', 'awscli_publisher',
                'terraform_sha256', 'provider_lock_sha256', 'billing'}


def harvest_representative_rows(entry, meta, rows, repo):
    run = meta['run']
    for row in rows:
        require(set(row) <= REP_ROW_KEYS, 'gate-row-keys')
        if row.get('diagnostic') is not None:
            require(re.fullmatch(r'[A-Z][A-Z0-9_]{2,60}', row['diagnostic']) is not None, 'gate-row-diagnostic')
    last = {}
    for row in rows:
        last[row['gate']] = row
    identity = last.get('execution-identity')
    if identity is not None:
        require(identity.get('sha') == run['head_sha'] and identity.get('run_id') == '%d-%d' % (run['id'], run['attempt']),
                'gate-identity')
    else:
        entry['evidence_gaps'].append('No execution-identity row: run identity inside the container not recorded')
    prepared = last.get('verified-preparation')
    if prepared is not None:
        require(prepared.get('sha') == run['head_sha'], 'gate-preparation-sha')
        entry['tested']['versions'] = {k: prepared.get(k) for k in ('emulator', 'terraform', 'awscli', 'provider')}
    harness = git_show(repo, run['head_sha'], WORKFLOWS[meta['workflow']]['harness'])
    gates = git_show(repo, run['head_sha'], 'scripts/emulator-verification/gates.py')
    required = operations_literal(gates.decode()) if gates is not None else None
    pinned = None
    if harness is not None:
        digest = hashlib.sha256(harness).hexdigest()
        pinned = KNOWN_HARNESSES.get(digest)
        entry['tested'].update(harness_sha256=digest, harness_verified_against_git=True)
    entry['tested'].update(required_operations=required, scenario_id='aws_vpc.proof',
                           scenario='disposable single-VPC adapter lifecycle')
    for key in CONTROLS:
        if 'control-' + key in last:
            entry['controls'][key] = last['control-' + key]['status']
    operations = {op: last[op]['status'] for op in REPRESENTATIVE_OPERATIONS if op in last}
    adapter = git_show(repo, run['head_sha'], 'scripts/emulator-verification/adapter/main.tf')
    addresses = adapter_inventory(adapter) if adapter is not None else []
    api_ids = {}
    for row in rows:
        if row.get('resource_id'):
            require(VPC_ID.match(row['resource_id']) is not None, 'gate-resource-id')
            api_ids['vpc_id'] = row['resource_id']
    evidence = {'plan_gate': last['plan']['status'] if 'plan' in last else 'NOT_TESTED', 'plan_resources': None,
                'api_owned_create': None, 'api_owned_update': None, 'inventory_sha256': inventory_digest(addresses)}
    cleanup = last.get('resource-cleanup', {}).get('status', 'NOT_TESTED')
    execution = last.get('execution')
    complete = last.get('lifecycle-evidence-complete', {}).get('status') == 'PASS'
    measured_pass = complete and execution is None and bool(operations) \
        and all(v == 'PASS' for v in operations.values()) \
        and all(v == 'PASS' for v in entry['controls'].values()) and cleanup == 'PASS'
    gaps = completeness_gaps(required, operations, pinned, 'aws_vpc.proof', addresses, evidence, api_ids) \
        if measured_pass else []
    ok = measured_pass and not gaps and run['conclusion'] == 'success'
    entry['roots'] = [{
        'name': 'representative-vpc-proof', 'kind': 'disposable-adapter', 'path': 'scripts/emulator-verification/adapter',
        'result': 'PASS' if ok else 'INSUFFICIENT_EVIDENCE' if measured_pass
        else (execution or {}).get('status', 'BLOCKED') if execution else 'BLOCKED',
        'resources': len(addresses), 'resource_addresses': addresses,
        'address_source': 'resource blocks of scripts/emulator-verification/adapter/main.tf at the tested SHA',
        'operations': operations, 'api_ids': api_ids, 'evidence': evidence, 'resource_cleanup': cleanup}]
    entry['evidence_gaps'].extend(gaps)
    entry['out_of_scope_roots'] = out_of_scope(set())
    host = [r['status'] for r in rows if r['gate'] == 'host-cleanup']
    entry['cleanup'] = {'resources': cleanup, 'material': last.get('material_cleanup', {}).get('status', 'NOT_TESTED'),
                        'process': last.get('process-cleanup', {}).get('status', 'NOT_TESTED'),
                        'host': host[-1] if len(host) == 1 else 'NOT_TESTED'}
    if len(host) != 1:
        entry['evidence_gaps'].append('Host cleanup row missing: host cleanup (container, image, context) not evidenced')
    recovery = sorted(r['gate'] for r in rows if r['gate'].startswith('recovery-') and r['status'] == 'PASS')
    if recovery:
        entry['observations'].append('Recovery after the failure: ' + ', '.join(recovery) + ' PASS')
    entry['untested'].append('Every DEV root and module: the representative scenario covers only the disposable '
                             'aws_vpc.proof adapter')
    if ok:
        entry['result'] = {'overall': 'PASS', 'basis': 'gate-rows', 'failure': None}
        return
    if measured_pass:
        entry['result'] = {'overall': 'INSUFFICIENT_EVIDENCE', 'basis': 'gate-rows', 'failure': {
            'step': first_failed_step(meta['job']), 'stage': 'evidence completeness', 'diagnostic': 'EVIDENCE_INCOMPLETE',
            'cause': 'the gate rows cannot support PASS; see evidence_gaps'}}
        return
    failed = [r for r in rows if r['status'] in ('FAIL', 'BLOCKED') and r['gate'] not in
              ('execution', 'complete-evidence-and-cleanup')]
    stage_row = failed[0] if failed else None
    if stage_row is None and execution is not None:
        before = rows[:rows.index(execution)]
        stage_row = before[-1] if before else None
        stage = 'after ' + stage_row['gate'] + ' (no failing stage row)' if stage_row else None
    else:
        stage = stage_row['gate'] if stage_row else None
    diagnostic = (stage_row or {}).get('diagnostic') if failed else None
    diagnostic = diagnostic or (execution or {}).get('diagnostic')
    overall = (execution or {}).get('status') or (stage_row or {}).get('status') or 'INSUFFICIENT_EVIDENCE'
    if overall not in OVERALL:
        overall = 'INSUFFICIENT_EVIDENCE'
    entry['result'] = {'overall': overall, 'basis': 'gate-rows', 'failure': {
        'step': first_failed_step(meta['job']), 'stage': stage, 'diagnostic': diagnostic,
        'cause': 'recorded by the harness gate rows' if diagnostic else 'no diagnostic recorded by the harness'}}
    if not diagnostic:
        entry['evidence_gaps'].append('The harness recorded no diagnostic code for the failure')


RUN_GATE_CAUSES = [
    (re.compile(r'ValueError: Invalid isoformat string'), 'RUN_GATE_ATTESTATION_NOT_A_TIMESTAMP',
     'the Owner attestation time was not an ISO 8601 timestamp'),
    (re.compile(r'AssertionError'), 'RUN_GATE_ASSERTION', 'a run gate assertion failed'),
]


def harvest_metadata_only(entry, meta, text):
    job = meta['job']
    step = first_failed_step(job)
    entry['out_of_scope_roots'] = out_of_scope(set())
    if job is None:
        entry['result'] = {'overall': 'BLOCKED', 'basis': 'run-metadata', 'failure': {
            'step': None, 'stage': 'workflow', 'diagnostic': 'NO_JOB_CREATED',
            'cause': 'GitHub created no job for this run; nothing executed'}}
        entry['evidence_gaps'].append('No job and no log exist: the reason GitHub created no job is not recorded')
        return
    diagnostic, cause = None, 'no structured record; failing step from job metadata'
    if text:
        for pattern, code, description in RUN_GATE_CAUSES:
            if pattern.search(text):
                diagnostic, cause = code, description
                break
        if diagnostic == 'RUN_GATE_ASSERTION':
            stamp = re.search(r'OWNER_CHECKED_AT: (20[0-9-]{8}T[0-9:]{8}(?:Z|[+-][0-9]{2}:[0-9]{2}))', text)
            line = re.search(r'File "<stdin>", line ([0-9]+)', text)
            if stamp and line:
                cause = ('a run gate assertion failed at line ' + line.group(1) + '; the Owner attestation time was '
                         + stamp.group(1))
                gate = re.search(r'^\ufeff?(20[0-9-]{8}T[0-9:]{8})\.[0-9]+Z ##\[group\]Run set -euo pipefail$', text, re.M)
                when = datetime.datetime.fromisoformat(stamp.group(1).replace('Z', '+00:00'))
                ran = datetime.datetime.fromisoformat(gate.group(1) + '+00:00') if gate else None
                if ran is not None and when > ran:
                    cause += (', %d s after the gate ran at %sZ (an attestation must be 0 to 1800 s old)'
                              % ((when - ran).total_seconds(), gate.group(1)))
    gate_steps = [s['name'] for s in job['steps'] if s['conclusion'] == 'failure']
    stage = 'run gate' if gate_steps and gate_steps[0].startswith('Require') else None
    entry['result'] = {'overall': 'BLOCKED' if stage == 'run gate' else 'INSUFFICIENT_EVIDENCE', 'basis': 'run-metadata',
                       'failure': {'step': step, 'stage': stage, 'diagnostic': diagnostic, 'cause': cause}}
    skipped = [s['name'] for s in job['steps'] if s['conclusion'] == 'skipped']
    if skipped:
        entry['observations'].append('Skipped steps: ' + '; '.join(skipped))
    entry['observations'].append('No resource operation ran: no structured record exists for any control or operation')


def build(meta, log_text, repo, harvested_at, registration='regular'):
    require(registration in ('regular', 'initial-backfill'), 'registration')
    check_meta(meta)
    rows, lines = parse_rows(log_text) if log_text is not None else ([], 0)
    if log_text is not None:
        require(meta['log']['kind'] != 'unavailable', 'meta-log-kind-mismatch')
        if meta['log']['kind'] == 'full':
            require(lines == meta['log']['lines'], 'meta-log-lines')
        require(meta['run']['head_sha'] in log_text or meta['log']['kind'] == 'excerpt', 'log-head-sha')
    else:
        require(meta['log']['kind'] == 'unavailable', 'meta-log-missing')
    if meta['job'] is not None and repo is not None:
        step_names_in_workflow(repo, meta)
    kind = WORKFLOWS[meta['workflow']]['kind']
    has_record = any(r['gate'] == 'summary-record' for r in rows)
    entry = base_entry(meta, harvested_at, meta['log']['kind'], meta['log']['lines'], rows, has_record, registration)
    if kind == 'step2-rehearsal' and has_record:
        harvest_step2_record(entry, meta, rows, repo)
    elif kind == 'representative' and rows:
        harvest_representative_rows(entry, meta, rows, repo)
    else:
        harvest_metadata_only(entry, meta, log_text)
    if meta['log']['kind'] == 'excerpt':
        entry['evidence_gaps'].append('Only the relevant log lines were harvested (excerpt), not the full log')
    entry['residual_risk'].append('GitHub keeps this run log and job summary for its retention period only; this '
                                  'entry is the durable sanitized record')
    validate(entry)
    return entry


# ---------------------------------------------------------------- index and reconciliation

def load_entries(directory):
    entries = {}
    for path in sorted(Path(directory).glob('*.json')):
        if path.name == 'actions-runs.json':
            continue
        try:
            entry = json.loads(path.read_text())
        except ValueError:
            raise Invalid('entry-not-json:' + path.name)
        try:
            validate(entry, path.name)
        except Invalid as error:
            raise Invalid(str(error) + ':' + path.name)
        key = (entry['run']['id'], entry['run']['attempt'])
        require(key not in entries, 'duplicate-entry')
        entries[key] = entry
    return entries


def reconcile(snapshot, entries):
    """Compare the ledger with the static run list snapshot; every list empty means it matches the snapshot."""
    exact_keys(snapshot, ['retrieved_at', 'source', 'workflows'], label='snapshot')
    walk_strings(snapshot, 'snapshot')
    problems = {'unregistered': [], 'not_in_actions': [], 'missing_attempts': [], 'mismatched': [], 'incomplete': [],
                'log_unavailable': []}
    seen = set()
    for workflow, runs in sorted(snapshot['workflows'].items()):
        require(workflow in WORKFLOWS, 'snapshot-workflow')
        for run in runs:
            exact_keys(run, ['id', 'attempt', 'number', 'event', 'head_branch', 'head_sha', 'status', 'conclusion',
                             'created_at'], label='snapshot-run')
            if run['status'] != 'completed':
                problems['incomplete'].append(run['id'])
                continue
            for attempt in range(1, run['attempt'] + 1):
                key = (run['id'], attempt)
                seen.add(key)
                entry = entries.get(key)
                if entry is None:
                    (problems['unregistered'] if attempt == run['attempt'] else problems['missing_attempts']).append(
                        '%d-attempt-%d' % key)
                    continue
                if attempt == run['attempt']:
                    fields = ('number', 'event', 'head_branch', 'head_sha', 'status', 'conclusion', 'created_at')
                    if entry['workflow']['file'] != workflow or any(entry['run'][f] != run[f] for f in fields):
                        problems['mismatched'].append('%d-attempt-%d' % key)
    for key, entry in sorted(entries.items()):
        if key not in seen:
            problems['not_in_actions'].append('%d-attempt-%d' % key)
        if entry['source']['log'] == 'unavailable' and entry['job'] is not None:
            problems['log_unavailable'].append('%d-attempt-%d' % key)
    return problems


def render_index(entries, snapshot, problems):
    counts = {w: len(r) for w, r in snapshot['workflows'].items()}
    blocking = {k: v for k, v in problems.items() if v and k != 'log_unavailable'}
    out = ['# AWS Emulator run evidence ledger', '',
           'Generated by `scripts/emulator-evidence/harvest.py index`; do not edit by hand. One sanitized entry per',
           'formal GitHub Actions run and attempt (Master Policy v14.4 §13.4), whatever its result. Entries are',
           'append-only: a correction is a new reviewed pull request that states its reason. The commit that',
           'registered an entry is the commit that added its file (`git log --diff-filter=A -- <file>`).', '',
           'An entry is a structured, sanitized record. It is not a copy of the full log, and it never holds raw State,',
           'saved plans, credentials, private keys or secret values. A value the run did not record is absent or',
           'NOT_TESTED, never inferred. Emulator results are not evidence of real AWS behavior.', '',
           '## Reconciliation with the run list snapshot', '',
           'This compares the ledger with `actions-runs.json`, a static snapshot of the GitHub Actions run list that',
           'the operator retrieved at ' + snapshot['retrieved_at'] + ' and committed with the entries. It is not a live',
           'query: runs started after that time, or anything GitHub changed since, are not covered until a later',
           'reviewed pull request updates the snapshot. Snapshot: ' +
           ', '.join('`%s` %d runs' % (Path(w).name, n) for w, n in sorted(counts.items())) + '; ' +
           '%d entries.' % len(entries), '',
           '| Check | Result |', '| --- | --- |']
    labels = [('unregistered', 'Runs in the snapshot without an entry'), ('missing_attempts', 'Missing attempts'),
              ('not_in_actions', 'Entries not in the snapshot'), ('mismatched', 'Entries that disagree with the snapshot'),
              ('incomplete', 'Runs still in progress (register after completion)'),
              ('log_unavailable', 'Runs whose log could not be retrieved')]
    for key, label in labels:
        out.append('| ' + label + ' | ' + (', '.join(str(x) for x in problems[key]) if problems[key] else 'none') + ' |')
    out += ['', 'Status: ' + ('MATCHES THE SNAPSHOT' if not blocking else 'DOES NOT MATCH THE SNAPSHOT'), '',
            '## Runs', '',
            '| Run | Workflow | Trigger | Head SHA | Scope | Result | Failure | Log | Registered |',
            '| --- | --- | --- | --- | --- | --- | --- | --- | --- |']
    for key in sorted(entries, key=lambda k: (entries[k]['run']['created_at'], k)):
        e = entries[key]
        run, result = e['run'], e['result']
        scope = ', '.join(r['name'] + ' (' + str(r['resources']) + ')' for r in e['roots']) or 'none'
        failure = result['failure'] or {}
        detail = ' / '.join(str(x) for x in (failure.get('stage'), failure.get('diagnostic')) if x) or ('n/a' if not failure
                                                                                                      else 'see entry')
        out.append('| [%d](%s) attempt %d (#%d, %s) | %s | %s | `%s` | %s | **%s** | %s | %s | [%s](%d-attempt-%d.json) %s |' % (
            run['id'], run['url'], run['attempt'], run['number'], run['created_at'][:10], Path(e['workflow']['file']).name,
            run['event'], run['head_sha'][:12], scope, result['overall'], detail, e['source']['log'],
            e['harvest']['harvested_at'][:10], run['id'], run['attempt'], e['harvest']['registration']))
    out += ['', 'Out-of-scope DEV roots are never PASS: each entry lists them as NOT_TESTED or',
            'EMULATOR_COMPATIBILITY_BLOCKED. See [Step 2 emulator rehearsals](../../step2-emulator-rehearsals.md).', '']
    return '\n'.join(out)


def check(directory):
    directory = Path(directory)
    entries = load_entries(directory)
    snapshot = json.loads((directory / 'actions-runs.json').read_text())
    problems = reconcile(snapshot, entries)
    require(not any(v for k, v in problems.items() if k != 'log_unavailable'), 'not-reconciled')
    index = (directory / 'index.md').read_text()
    require(index == render_index(entries, snapshot, problems), 'index-out-of-date')
    return entries, problems


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    try:
        if argv[:1] == ['build']:
            args = dict(zip(argv[1::2], argv[2::2]))
            require(set(args) <= {'--meta', '--log', '--repo', '--out', '--harvested-at', '--registration'}
                    and {'--meta', '--out', '--harvested-at'} <= set(args), 'usage')
            meta = json.loads(Path(args['--meta']).read_text())
            log = Path(args['--log']).read_text(encoding='utf-8-sig') if '--log' in args else None
            entry = build(meta, log, args.get('--repo'), args['--harvested-at'], args.get('--registration', 'regular'))
            target = Path(args['--out']) / ('%d-attempt-%d.json' % (entry['run']['id'], entry['run']['attempt']))
            require(not target.exists(), 'entry-exists-append-only')
            target.write_text(json.dumps(entry, indent=2, sort_keys=True) + '\n')
            print(target)
        elif argv[:1] == ['index'] and len(argv) == 2:
            directory = Path(argv[1])
            entries = load_entries(directory)
            snapshot = json.loads((directory / 'actions-runs.json').read_text())
            (directory / 'index.md').write_text(render_index(entries, snapshot, reconcile(snapshot, entries)))
        elif argv[:1] == ['check'] and len(argv) == 2:
            entries, problems = check(argv[1])
            print('ledger OK: %d entries; matches the run list snapshot retrieved %s (static, not a live API query)'
                  % (len(entries), json.loads((Path(argv[1]) / 'actions-runs.json').read_text())['retrieved_at']))
        else:
            raise Invalid('usage')
    except Invalid as error:
        print('ledger REJECTED: ' + str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
