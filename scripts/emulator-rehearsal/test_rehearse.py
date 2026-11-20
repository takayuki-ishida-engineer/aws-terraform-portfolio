#!/usr/bin/env python3
"""Offline negative and mutation tests for the Step 2 rehearsal gates.

Synthetic plan and refresh documents only: no emulator, Terraform, AWS call or
network access. Each mutation must be rejected with its specific gate label.
"""
import contextlib
import re
import copy
import io
import sys
import unittest
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import rehearse  # noqa: E402
from gates import Blocked  # noqa: E402
import summarize  # noqa: E402
import workflow_contract  # noqa: E402
import importlib.util  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402
import tempfile  # noqa: E402

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(1, str(REPO / 'kubernetes/vendor/pyyaml'))
import yaml  # noqa: E402

_spec = importlib.util.spec_from_file_location('step2_prepare', HERE / 'prepare.py')
step2_prepare = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(step2_prepare)
WORKFLOW = REPO / '.github/workflows/aws-emulator-rehearsal.yml'

RUN_ID = '20261118000000-1'
M = rehearse.M


def harness(scenario='network-full'):
    r = rehearse.Rehearsal.__new__(rehearse.Rehearsal)
    r.run_id = RUN_ID
    r.scenario = r.name = scenario
    r.spec = rehearse.SCENARIOS[scenario]
    r.expected = rehearse.expected_for(scenario)
    r.controls = {str(i): 'NOT_TESTED' for i in range(1, 15)}
    r.root_controls = {}
    r.state_ids = {a: 'id-%d' % i for i, a in enumerate(sorted(r.expected))}
    return r


def tags(phase):
    return {'VerificationRun': RUN_ID, 'Phase': phase, 'project': rehearse.PROJECT, 'env': 'dev',
            'managed': 'terraform', 'Name': 'step2-dev-x', 'service': 'x'}


def plan(r, action, phase='create'):
    changes = []
    for address, kind in r.expected.items():
        taggable = kind not in r.spec['untagged']
        body = {'id': r.state_ids[address], 'cidr_block': '10.40.0.0/16'}
        before = dict(body, **({'tags_all': tags('create')} if taggable else {}))
        after = dict(body, **({'tags_all': tags(phase)} if taggable else {}))
        acts = {'create': ['create'], 'delete': ['delete'], 'no-op': ['no-op'],
                'update': ['no-op'] if not taggable else ['update']}[action]
        changes.append({'address': address, 'mode': 'managed', 'type': kind,
                        'module_address': r.spec['module'] or address.rsplit('.', 2)[0],
                        'provider_name': 'registry.terraform.io/hashicorp/aws',
                        'change': {'actions': acts, 'before': None if action == 'create' else before,
                                   'after': None if action == 'delete' else after}})
    endpoint = {'constant_value': rehearse.ENDPOINT}
    return {'terraform_version': '1.17.0', 'resource_changes': changes,
            'configuration': {'provider_config': {'aws': {'expressions': {
                'allowed_account_ids': {'constant_value': ['000000000000']},
                'endpoints': [{e: dict(endpoint) for e in r.spec['endpoints']}]}}}}}


def change(doc, address):
    return next(c for c in doc['resource_changes'] if c['address'] == address)


EIP = M + 'aws_eip.nat["ca-central-1a"]'
RTB = M + 'aws_route_table.private_by_az["ca-central-1a"]'
NAT = M + 'aws_nat_gateway.this["ca-central-1a"]'
VPC = M + 'aws_vpc.this'


def refresh(r):
    return {'output_changes': {'network': {'actions': ['no-op']}}, 'resource_drift': [
        {'address': EIP, 'change': {'actions': ['update'],
                                    'before': {'network_interface': '', 'private_ip': '', 'association_id': '', 'private_dns': ''},
                                    'after': {'network_interface': 'eni-1', 'private_ip': '10.40.10.4',
                                              'association_id': 'eipassoc-1', 'private_dns': 'ip-10-40-10-4'}}},
        {'address': RTB, 'change': {'actions': ['update'], 'before': {'route': []},
                                    'after': {'route': [{'cidr_block': '0.0.0.0/0', 'nat_gateway_id': r.state_ids[NAT]}]}}}]}


def nat(r):
    return {'NatGatewayId': r.state_ids[NAT], 'NatGatewayAddresses': [
        {'AllocationId': r.state_ids[EIP], 'NetworkInterfaceId': 'eni-1', 'PrivateIp': '10.40.10.4'}]}


class Quiet(unittest.TestCase):
    def run(self, result=None):
        with contextlib.redirect_stdout(io.StringIO()):
            return super().run(result)

    def rejects(self, label, func, *args):
        with self.assertRaises(Blocked) as caught:
            func(*args)
        self.assertEqual(str(caught.exception), label)


class InventoryTests(Quiet):
    def test_scenarios(self):
        self.assertEqual(len(rehearse.expected_for('network-full')), 26)
        self.assertEqual(len(rehearse.expected_for('tfstate')), 7)
        self.assertEqual(len(rehearse.expected_for('api')), 7)
        self.assertTrue(set(rehearse.ALL) <= set(rehearse.SCENARIOS) and not set(rehearse.ALL) & set(rehearse.KNOWN_GAPS))
        reduced = rehearse.expected_for('network')
        self.assertEqual(len(reduced), 16)
        self.assertFalse(set(reduced.values()) & rehearse.ENDPOINT_TYPES)
        self.rejects('scenario', rehearse.expected_for, 'everything')

    def test_normal_ignores_order_only(self):
        self.assertEqual(rehearse.normal({'a': [{'k': 2}, {'k': 1}]}), rehearse.normal({'a': [{'k': 1}, {'k': 2}]}))
        self.assertNotEqual(rehearse.normal({'a': [1]}), rehearse.normal({'a': [2]}))

    def test_redaction(self):
        rehearse.REDACT.append('SECRETVALUE123')
        try:
            self.assertNotIn('SECRETVALUE123', rehearse.safe('error near SECRETVALUE123'))
        finally:
            rehearse.REDACT.remove('SECRETVALUE123')


class PlanTests(Quiet):
    def test_valid_plans_pass(self):
        for scenario in rehearse.SCENARIOS:
            r = harness(scenario)
            for action, phase in [('create', 'create'), ('update', 'updated'), ('no-op', 'updated'), ('delete', 'updated')]:
                r.inspect(plan(r, action, phase), action, phase)
        self.assertEqual(r.root_controls['11'], 'PASS')

    def test_rejections(self):
        r = harness()
        cases = []

        def case(label, action, phase, mutate):
            doc = plan(r, action, phase)
            mutate(doc)
            cases.append((label, doc, action, phase))

        case('plan-version', 'create', 'create', lambda d: d.update(terraform_version='1.16.0'))
        case('plan-errored-or-deferred', 'create', 'create', lambda d: d.update(errored=True))
        case('plan-drift', 'update', 'updated', lambda d: d.update(resource_drift=[{'address': VPC}]))
        case('provider-endpoint-guard', 'create', 'create', lambda d: d['configuration']['provider_config']['aws']['expressions']
             ['endpoints'][0]['ec2'].update(constant_value='https://ec2.ca-central-1.amazonaws.com'))
        case('provider-endpoint-guard', 'create', 'create', lambda d: d['configuration']['provider_config']['aws']['expressions']
             ['endpoints'][0].update(s3={'constant_value': rehearse.ENDPOINT}))
        case('provider-endpoint-guard', 'create', 'create', lambda d: d['configuration']['provider_config']['aws']['expressions']
             ['allowed_account_ids'].update(constant_value=['123456789012']))
        case('plan-resource-inventory', 'create', 'create', lambda d: d['resource_changes'].append(
            dict(copy.deepcopy(d['resource_changes'][0]), address=M + 'aws_instance.extra')))
        case('plan-resource-inventory', 'create', 'create', lambda d: d['resource_changes'].pop())
        case('plan-resource-identity', 'create', 'create', lambda d: change(d, VPC).update(type='aws_subnet'))
        case('plan-resource-identity', 'create', 'create', lambda d: change(d, VPC).update(mode='data'))
        case('plan-resource-identity', 'create', 'create', lambda d: change(d, VPC).update(provider_name='registry.example/aws'))
        case('plan-actions-create', 'create', 'create', lambda d: change(d, VPC)['change'].update(actions=['delete', 'create']))
        case('plan-tags', 'create', 'create', lambda d: change(d, VPC)['change']['after']['tags_all'].pop('VerificationRun'))
        case('plan-tags', 'create', 'create', lambda d: change(d, VPC)['change']['after'].pop('tags_all'))
        case('plan-tags', 'update', 'updated', lambda d: change(d, VPC)['change']['after']['tags_all'].update(Phase='create'))
        case('plan-actions-update', 'update', 'updated', lambda d: change(d, VPC)['change'].update(actions=['delete', 'create']))
        case('plan-actions-update', 'update', 'updated', lambda d: change(d, RTB.replace('aws_route_table.private_by_az', 'aws_route.private_nat'))
             ['change'].update(actions=['update']))
        case('update-changes-only-tags', 'update', 'updated', lambda d: change(d, VPC)['change']['after'].update(cidr_block='10.0.0.0/8'))
        case('plan-actions-no-op', 'no-op', 'updated', lambda d: change(d, VPC)['change'].update(actions=['update']))
        case('plan-actions-delete', 'delete', 'updated', lambda d: change(d, VPC)['change'].update(actions=['no-op']))
        case('destroy-target-identity', 'delete', 'updated', lambda d: change(d, VPC)['change']['before'].update(id='vpc-preexisting'))
        for label, doc, action, phase in cases:
            with self.subTest(label=label):
                self.rejects(label, r.inspect, doc, action, phase)
        self.assertGreaterEqual(len(cases), 20)


class RefreshTests(Quiet):
    def test_reviewed_convergence_passes(self):
        r = harness()
        doc = refresh(r)
        r.check_refresh(doc, r.drift_summary(doc), nat(r))
        empty = {'resource_drift': []}
        r.check_refresh(empty, [], nat(r))

    def test_rejections(self):
        r = harness()
        cases = [
            ('refresh-output-changes', lambda d, n: d['output_changes']['network'].update(actions=['update'])),
            ('refresh-nat-identity', lambda d, n: n.update(NatGatewayId='nat-other')),
            ('nat-eip-association', lambda d, n: n.update(NatGatewayAddresses=[])),
            ('refresh-drift-unexpected', lambda d, n: d['resource_drift'].append(
                {'address': VPC, 'change': {'actions': ['update'], 'before': {'cidr_block': 'a'}, 'after': {'cidr_block': 'b'}}})),
            ('refresh-drift-unexpected', lambda d, n: d['resource_drift'][0]['change']['after'].update(allocation_id='eipalloc-x')),
            ('refresh-drift-unexpected', lambda d, n: d['resource_drift'][0]['change'].update(actions=['delete', 'create'])),
            ('refresh-eip-values', lambda d, n: d['resource_drift'][0]['change']['after'].update(network_interface='eni-other')),
            ('refresh-eip-values', lambda d, n: d['resource_drift'][0]['change']['after'].update(private_ip='10.40.10.99')),
            ('refresh-route-values', lambda d, n: d['resource_drift'][1]['change']['after']['route'][0].update(nat_gateway_id='nat-other')),
            ('refresh-route-values', lambda d, n: d['resource_drift'][1]['change']['after']['route'].append(
                {'cidr_block': '10.0.0.0/8', 'nat_gateway_id': r.state_ids[NAT]})),
        ]
        for label, mutate in cases:
            with self.subTest(label=label):
                doc, nat_row = refresh(r), nat(r)
                mutate(doc, nat_row)
                self.rejects(label, r.check_refresh, doc, r.drift_summary(doc), nat_row)


POOL = rehearse.CA + 'aws_cognito_user_pool.this'
CLIENT = rehearse.CA + 'aws_cognito_user_pool_client.this'


def teardown_plan(r):
    doc = plan(r, 'no-op', 'updated')
    pool = change(doc, POOL)
    pool['change'].update(actions=['update'])
    pool['change']['before']['tags_all'] = dict(pool['change']['after']['tags_all'])
    pool['change']['before']['deletion_protection'] = 'ACTIVE'
    pool['change']['after']['deletion_protection'] = 'INACTIVE'
    return doc


class TeardownAndTagDriftTests(Quiet):
    def test_teardown_plan(self):
        r = harness('api')
        r.inspect(teardown_plan(r), 'teardown', 'updated')
        cases = [
            lambda d: change(d, POOL)['change']['after'].update(mfa_configuration='OFF'),
            lambda d: change(d, POOL)['change']['after'].update(deletion_protection='ACTIVE'),
            lambda d: change(d, POOL)['change']['before'].update(deletion_protection='INACTIVE'),
            lambda d: change(d, POOL)['change'].update(actions=['delete', 'create']),
            lambda d: change(d, CLIENT)['change'].update(actions=['update']),
        ]
        for mutate in cases:
            with self.subTest(mutate=mutate):
                doc = teardown_plan(r)
                mutate(doc)
                self.rejects('plan-actions-teardown', r.inspect, doc, 'teardown', 'updated')

    def test_tag_transition_drift(self):
        r = harness('api')
        good = [{'address': POOL, 'change': {'actions': ['update'], 'before': {'tags': {'Name': 'n'}, 'x': 1},
                                             'after': {'tags': {'Name': 'n', 'Phase': 'create'}, 'x': 1}}}]
        r.tag_transition_drift(good, 'update')
        r.tag_transition_drift([], 'create')
        for action in ('create', 'no-op', 'delete', 'teardown'):
            with self.subTest(action=action):
                self.rejects('plan-drift', r.tag_transition_drift, copy.deepcopy(good), action)
        for mutate in [lambda d: d[0]['change']['after']['tags'].update(Phase='updated'),
                       lambda d: d[0]['change']['after']['tags'].update(Owner='x'),
                       lambda d: d[0]['change']['after'].update(x=2),
                       lambda d: d[0].update(address=rehearse.CA + 'unknown.this'),
                       lambda d: d[0]['change'].update(actions=['delete', 'create']),
                       lambda d: d[0].pop('change')]:
            with self.subTest(mutate=mutate):
                doc = copy.deepcopy(good)
                mutate(doc)
                self.rejects('plan-drift', r.tag_transition_drift, doc, 'update')


def cognito_refresh():
    schema_before = [{'attribute_data_type': 'String', 'developer_only_attribute': None, 'mutable': True, 'name': 'email'}]
    schema_after = [{'attribute_data_type': 'String', 'developer_only_attribute': False, 'mutable': True, 'name': 'email'}]
    return {'output_changes': {}, 'resource_drift': [{'address': POOL, 'change': {'actions': ['update'],
            'before': {'domain': '', 'last_modified_date': 't1', 'auto_verified_attributes': None, 'schema': schema_before},
            'after': {'domain': 'step2-dev-auth', 'last_modified_date': 't2', 'auto_verified_attributes': [], 'schema': schema_after}}}]}


class CognitoRefreshTests(Quiet):
    def test_reviewed_convergence_and_rejections(self):
        r = harness('api')
        doc = cognito_refresh()
        r.check_refresh_api(doc, r.drift_summary(doc), 'step2-dev-auth')
        cases = [
            ('refresh-cognito-domain', 'step2-dev-other', lambda d: None),
            ('refresh-cognito-schema', 'step2-dev-auth', lambda d: d['resource_drift'][0]['change']['after']['schema'][0].update(mutable=False)),
            ('refresh-cognito-auto-verified', 'step2-dev-auth', lambda d: d['resource_drift'][0]['change']['after'].update(auto_verified_attributes=['email'])),
            ('refresh-drift-unexpected', 'step2-dev-auth', lambda d: d['resource_drift'][0]['change']['after'].update(mfa_configuration='OFF')),
            ('refresh-drift-unexpected', 'step2-dev-auth', lambda d: d['resource_drift'][0].update(address=CLIENT)),
            ('refresh-output-changes', 'step2-dev-auth', lambda d: d['output_changes'].update(x={'actions': ['update']})),
        ]
        for label, domain, mutate in cases:
            with self.subTest(label=label):
                doc = cognito_refresh()
                mutate(doc)
                self.rejects(label, r.check_refresh_api, doc, r.drift_summary(doc), domain)


def workflow():
    return yaml.load(WORKFLOW.read_text(), Loader=yaml.BaseLoader)


class WorkflowTests(Quiet):
    def test_committed_workflow_passes(self):
        workflow_contract.workflow_gate(workflow())

    def test_unsafe_mutations_rejected(self):
        def steps(w):
            return w['jobs']['rehearsal']['steps']

        def docker(w, old, new):
            s = steps(w)[3]
            assert old in s['run'], old
            s['run'] = s['run'].replace(old, new, 1)

        cases = [
            ('push-or-dispatch-only', lambda w: w['on'].update(pull_request={'branches': ['main']})),
            ('push-or-dispatch-only', lambda w: w['on'].update(pull_request_target={})),
            ('push-main-exact-paths', lambda w: w['on']['push'].update(branches=['**'])),
            ('push-main-exact-paths', lambda w: w['on']['push'].pop('paths')),
            ('push-main-exact-paths', lambda w: w['on']['push']['paths'].append('docs/**')),
            ('permissions-concurrency', lambda w: w.update(permissions={'contents': 'write'})),
            ('permissions-concurrency', lambda w: w['concurrency'].update({'cancel-in-progress': 'true'})),
            ('standard-free-runner', lambda w: w['jobs']['rehearsal'].update({'runs-on': 'ubuntu-latest-8-cores'})),
            ('no-extra-runtime-privileges', lambda w: w['jobs']['rehearsal'].update(permissions={'id': 'write'})),
            ('job-env-contract', lambda w: w['jobs']['rehearsal']['env'].update(TARGET_SHA='${{ inputs.target_sha }}')),
            ('job-env-contract', lambda w: w['jobs']['rehearsal']['env'].update(AWS_ACCESS_KEY_ID='x')),
            ('dispatch-contract', lambda w: w['on']['workflow_dispatch']['inputs'].update(extra={'required': 'true'})),
            ('scenario-choice', lambda w: w['on']['workflow_dispatch']['inputs']['scenario'].update(options=['anything'])),
            ('consent-before-checkout', lambda w: steps(w).insert(0, steps(w).pop(1))),
            ('checkout-no-auth-lfs', lambda w: steps(w)[1]['with'].update({'persist-credentials': 'true'})),
            ('pinned-approved-checkout-only', lambda w: steps(w)[1].update(uses='actions/checkout@v4')),
            ('no-external-writes-or-host-network', lambda w: steps(w)[4].update(run=steps(w)[4]['run'] + '\n# actions/upload-artifact')),
            ('run-gate-e[\'ACTOR\']==e[\'OWNER\']', lambda w: steps(w)[0].update(
                run=steps(w)[0]['run'].replace("e['ACTOR']==e['OWNER']", 'True'))),
            ('run-gate-e[\'GITHUB_RUN_ATTEMPT\']==\'1\'', lambda w: steps(w)[0].update(
                run=steps(w)[0]['run'].replace("e['GITHUB_RUN_ATTEMPT']=='1'", 'True'))),
            ('run-gate-e[\'VISIBILITY\']==\'public\'', lambda w: steps(w)[0].update(
                run=steps(w)[0]['run'].replace("e['VISIBILITY']=='public'", 'True'))),
            ('docker-option-value', lambda w: docker(w, '--network none', '--network bridge')),
            ('unexpected-docker-option', lambda w: docker(w, '--read-only', '--read-only --ipc host')),
            ('docker-options-missing', lambda w: docker(w, ' --read-only', '')),
            ('docker-option-value', lambda w: docker(w, '--cap-drop ALL', '--cap-drop NET_RAW')),
            ('no-port-or-host-mount', lambda w: docker(w, '--rm', '--rm -v /:/host')),
            ('docker-tmpfs-bounds', lambda w: docker(w, 'size=3g', 'size=30g')),
            ('docker-image-and-report', lambda w: docker(w, '| tee "$RUNNER_TEMP/step2-safe-report.jsonl"', '')),
            ('strict-host-cleanup', lambda w: docker(w, 'trap cleanup EXIT', 'true')),
            ('summary-real-outcome', lambda w: steps(w)[4].pop('if')),
            ('verified-preparation-step', lambda w: steps(w)[2].update(run='python3 scripts/emulator-rehearsal/prepare.py')),
        ]
        for label, mutate in cases:
            with self.subTest(label=label):
                w = workflow()
                mutate(w)
                self.rejects(label, workflow_contract.workflow_gate, w)


GITHUB = {'GITHUB_ACTIONS': 'true', 'GITHUB_EVENT_NAME': 'push', 'GITHUB_REF': 'refs/heads/main', 'GITHUB_REPOSITORY': 'owner/repo',
          'GITHUB_WORKFLOW_REF': 'owner/repo/.github/workflows/aws-emulator-rehearsal.yml@refs/heads/main'}


class ContextTests(Quiet):
    def test_allowed_contexts(self):
        self.assertEqual(step2_prepare.execution_context(GITHUB), 'github-actions')
        self.assertEqual(step2_prepare.execution_context(dict(GITHUB, GITHUB_EVENT_NAME='workflow_dispatch')), 'github-actions')
        self.assertEqual(step2_prepare.execution_context({}), 'local')

    def test_refused_contexts(self):
        for change in [{'GITHUB_EVENT_NAME': 'pull_request'}, {'GITHUB_EVENT_NAME': 'schedule'},
                       {'GITHUB_REF': 'refs/heads/feature'}, {'GITHUB_REF': 'refs/pull/1/merge'},
                       {'GITHUB_WORKFLOW_REF': 'owner/repo/.github/workflows/terraform-offline-ci.yml@refs/heads/main'},
                       {'GITHUB_WORKFLOW_REF': 'owner/repo/.github/workflows/aws-emulator-rehearsal.yml@refs/heads/feature'},
                       {'GITHUB_REPOSITORY': 'fork/repo'}]:
            with self.subTest(change=change):
                self.assertIsNone(step2_prepare.execution_context(dict(GITHUB, **change)))
        self.assertIsNone(step2_prepare.execution_context({'CI': 'true'}))

    def test_actions_preflight_refusals(self):
        head = 'a' * 40
        good = dict(GITHUB, ACTOR='owner', TRIGGERING_ACTOR='owner', OWNER='owner', VISIBILITY='public',
                    GITHUB_RUN_ATTEMPT='1', TARGET_SHA=head, GITHUB_SHA=head, RUNNER_KIND='self-hosted',
                    RUNNER_OS='Linux', RUNNER_ARCH='X64')
        # With a valid run identity the next gate (runner eligibility) is reached and refuses a self-hosted runner.
        self.assertEqual(step2_prepare.actions_preflight(good, head), 'runner-eligibility')
        for change in [{'ACTOR': 'someone'}, {'TRIGGERING_ACTOR': 'someone'}, {'VISIBILITY': 'private'},
                       {'GITHUB_REF': 'refs/heads/feature'}, {'GITHUB_RUN_ATTEMPT': '2'}, {'TARGET_SHA': 'b' * 40}]:
            with self.subTest(change=change):
                self.assertEqual(step2_prepare.actions_preflight(dict(good, **change), head), 'run-identity')
        self.assertEqual(step2_prepare.actions_preflight(good, 'c' * 40), 'run-identity')


def root_record(**override):
    base = {'description': 'network root', 'resources': 16, 'status': 'PASS',
            'operations': dict.fromkeys(summarize.REQUIRED_OPERATIONS, 'PASS'), 'controls': {}, 'resource_cleanup': 'PASS',
            'unsupported_apis': [], 'failure': None}
    base.update(override)
    return base


def record(roots=None, **override):
    base = {'run_id': '123-1', 'tested_sha': 'a' * 40, 'harness_sha256': 'b' * 64, 'scenario': 'all supported roots: network, api',
            'scenario_id': 'all',
            'versions': {'emulator': '1.0.385', 'terraform': '1.17.0', 'awscli': '2.35.0', 'provider': '6.72.0'},
            'execution': {'kind': 'github-actions', 'repository': 'owner/repo', 'run_id': '123', 'run_attempt': '1', 'event': 'push',
                          'run_url': 'https://github.com/owner/repo/actions/runs/123',
                          'workflow_ref': 'owner/repo/.github/workflows/aws-emulator-rehearsal.yml@refs/heads/main',
                          'runner': 'ubuntu-24.04 (GitHub-hosted)'},
            'controls': {str(i): 'PASS' for i in range(1, 15)},
            'roots': roots if roots is not None else {
                'network': root_record(),
                'api': root_record(description='api root', resources=7, operations=dict(
                    dict.fromkeys(summarize.REQUIRED_OPERATIONS, 'PASS'), teardown_plan='PASS', teardown='PASS'))},
            'known_gaps': {'tfstate': 'S3 Control gap'},
            'material_cleanup': 'PASS', 'process_cleanup': 'PASS', 'failure': None}
    base.update(override)
    return base


SUMMARY_ENV = dict(GITHUB, GITHUB_RUN_ID='123', GITHUB_RUN_ATTEMPT='1', TARGET_SHA='a' * 40,
                   EXECUTION_STATUS='success', CONSENT_ACCEPTED='true')


def report(rows):
    handle = tempfile.NamedTemporaryFile('w', suffix='.jsonl', delete=False)
    handle.write(''.join(json.dumps(r) + '\n' for r in rows))
    handle.close()
    return handle.name


class SummaryTests(Quiet):
    def run_summary(self, rows, env=SUMMARY_ENV):
        path = report(rows)
        out = Path(tempfile.mkdtemp()) / 'summary.md'
        saved = dict(os.environ)
        try:
            os.environ.clear(); os.environ.update(env, GITHUB_STEP_SUMMARY=str(out))
            code = summarize.main([path])
        finally:
            os.environ.clear(); os.environ.update(saved)
            os.unlink(path)
        return code, out.read_text()

    def good(self, **override):
        return [{'gate': 'control-1', 'status': 'PASS'},
                {'gate': 'refresh-convergence', 'status': 'PASS', 'drift': [{'address': 'module.network.aws_eip.nat["ca-central-1a"]'}]},
                {'gate': 'summary-record', 'status': 'PASS', 'record': record(**override)},
                {'gate': 'host-cleanup', 'status': 'PASS'}]

    def test_complete_pass_names_the_ci_run(self):
        code, text = self.run_summary(self.good())
        self.assertEqual(code, 0)
        self.assertIn('**Result: PASS**', text)
        self.assertIn('https://github.com/owner/repo/actions/runs/123', text)
        self.assertIn('aws-emulator-rehearsal.yml@refs/heads/main', text)
        self.assertIn('automatic on push to main', text)
        self.assertIn('Owner decision 2026-11-20', text)
        self.assertEqual(sum(1 for line in text.splitlines() if re.fullmatch(r'\| \d+ \| .+ \| PASS \|', line)), 14)
        self.assertIn('| teardown | n/a | PASS |', text)
        self.assertIn('tfstate: S3 Control gap', text)

    def test_incomplete_or_missing_evidence_fails(self):
        def roots(**over):
            return {'network': root_record(**over)}
        cases = [
            ('summary record missing', [r for r in self.good() if r['gate'] != 'summary-record']),
            ('host cleanup MISSING', self.good()[:-1]),
            ('host cleanup FAIL', self.good()[:-1] + [{'gate': 'host-cleanup', 'status': 'FAIL'}]),
            ('not every control PASS', self.good(controls=dict({str(i): 'PASS' for i in range(1, 15)}, **{'7': 'NOT_TESTED'}))),
            ('root network FAIL', self.good(roots=roots(status='FAIL'))),
            ('root network operations not all PASS', self.good(roots=roots(operations=dict(
                dict.fromkeys(summarize.REQUIRED_OPERATIONS, 'PASS'), destroy='FAIL')))),
            ('root network operations not all PASS', self.good(roots=roots(operations={'plan': 'PASS'}))),
            ('root network operations not all PASS', self.good(roots=roots(operations=dict(
                dict.fromkeys(summarize.REQUIRED_OPERATIONS, 'PASS'), teardown='FAIL')))),
            ('root network resource cleanup FAIL', self.good(roots=roots(resource_cleanup='FAIL'))),
            ('no root rehearsed', self.good(roots={})),
            ('material cleanup FAIL', self.good(material_cleanup='FAIL')),
            ('run identity mismatch', self.good(run_id='999-1')),
            ('run identity mismatch', self.good(tested_sha='c' * 40)),
            ('failure recorded', self.good(failure={'operation': 'setup', 'label': 'x', 'api': None})),
        ]
        for problem, rows in cases:
            with self.subTest(problem=problem):
                code, text = self.run_summary(rows)
                self.assertEqual(code, 1)
                self.assertNotIn('**Result: PASS**', text)
                self.assertIn(problem, text)
        code, text = self.run_summary(self.good(), dict(SUMMARY_ENV, EXECUTION_STATUS='failure'))
        self.assertEqual(code, 1)
        code, text = self.run_summary(self.good(), dict(SUMMARY_ENV, CONSENT_ACCEPTED=''))
        self.assertEqual(code, 1)
        code, text = self.run_summary(self.good() + [{'gate': 'summary-record', 'status': 'PASS', 'record': record()}])
        self.assertEqual(code, 1)

    def test_unsafe_text_blocks(self):
        code, text = self.run_summary(self.good(scenario='<script>'))
        self.assertEqual(code, 1)
        self.assertIn('**Result: BLOCKED**', text)


if __name__ == '__main__':
    unittest.main(verbosity=1)
