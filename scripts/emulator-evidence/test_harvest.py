#!/usr/bin/env python3
"""Offline negative, mutation and tamper tests for the emulator run evidence ledger.

Synthetic logs and the committed ledger only: no network, GitHub API, emulator or
Terraform. Every mutation must be rejected with its specific label, and no run
without complete structured evidence may become PASS.
"""
import copy
import io
import contextlib
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import harvest  # noqa: E402
from harvest import Invalid  # noqa: E402

REPO = HERE.parents[1]
LEDGER = REPO / 'docs/evidence/emulator-runs'
REHEARSAL = '.github/workflows/aws-emulator-rehearsal.yml'
REPRESENTATIVE = '.github/workflows/aws-emulator-verification.yml'
SHA = 'a' * 40
RUN_ID = 900000000001

HARNESS = b'''
M = 'module.network.'
SERVICES = ['sts']
EXPECTED = {
    M + 'aws_vpc.this': 'aws_vpc',
    M + 'aws_subnet.private["private1"]': 'aws_subnet',
    M + 'aws_security_group.endpoints[0]': 'aws_security_group',
    **{M + f'aws_vpc_endpoint.interface["{s}"]': 'aws_vpc_endpoint' for s in SERVICES},
}
ENDPOINT_TYPES = {'aws_security_group', 'aws_vpc_security_group_ingress_rule', 'aws_vpc_endpoint'}
'''
HARNESS_SHA256 = hashlib.sha256(HARNESS).hexdigest()
ADAPTER = b'resource "aws_vpc" "proof" {\n  cidr_block = "10.0.0.0/16"\n}\n'
WORKFLOW_SOURCE = '\n'.join('      - name: ' + n for n in [
    'Require main, the Owner and a public repository', 'Checkout reviewed target without credentials',
    'Prepare verified packages, provider mirror and image context',
    'Build temporary image and run the isolated rehearsal', 'Nonsecret summary',
    'Require owner cost confirmation and reviewed main SHA', 'Prepare verified packages and offline dependencies',
    'Build temporary image and run isolated verification']).encode()
OPS = ['plan', 'create', 'api_create', 'read', 'update_plan', 'update', 'api_update', 'no_op', 'destroy_plan',
       'destroy', 'state_empty', 'api_absence', 'baseline_preserved']


def fake_git(repo, sha, path):
    if repo is None or sha != SHA:
        return None
    return {'scripts/emulator-rehearsal/rehearse.py': HARNESS,
            'scripts/emulator-verification/lifecycle.py': b'# lifecycle\n',
            'scripts/emulator-verification/adapter/main.tf': ADAPTER,
            REHEARSAL: WORKFLOW_SOURCE, REPRESENTATIVE: WORKFLOW_SOURCE}.get(path)


def steps(conclusions, names=None):
    names = names or ['Require main, the Owner and a public repository', 'Checkout reviewed target without credentials',
                      'Prepare verified packages, provider mirror and image context',
                      'Build temporary image and run the isolated rehearsal', 'Nonsecret summary']
    out = [{'number': 1, 'name': 'Set up job', 'conclusion': 'success'}]
    out += [{'number': i + 2, 'name': n, 'conclusion': c} for i, (n, c) in enumerate(zip(names, conclusions))]
    return out + [{'number': 13, 'name': 'Complete job', 'conclusion': 'success'}]


def meta(workflow=REHEARSAL, conclusion='success', lines=None, kind='full', step_conclusions=None):
    run = {'id': RUN_ID, 'attempt': 1, 'number': 7, 'event': 'push', 'head_branch': 'main', 'head_sha': SHA,
           'status': 'completed', 'conclusion': conclusion, 'created_at': '2026-11-20T01:00:00Z',
           'updated_at': '2026-11-20T01:05:00Z', 'actor_is_repository_owner': True,
           'triggering_actor_is_repository_owner': True}
    names = None if workflow == REHEARSAL else [
        'Require owner cost confirmation and reviewed main SHA', 'Checkout reviewed target without credentials',
        'Prepare verified packages and offline dependencies', 'Build temporary image and run isolated verification',
        'Nonsecret summary']
    job = {'id': 900000000002, 'name': 'rehearsal' if workflow == REHEARSAL else 'representative',
           'conclusion': conclusion, 'runner_label': 'ubuntu-24.04', 'started_at': '2026-11-20T01:00:05Z',
           'completed_at': '2026-11-20T01:04:59Z',
           'steps': steps(step_conclusions or ['success'] * 5, names)}
    return {'workflow': workflow, 'run': run, 'job': job, 'log': {'kind': kind, 'lines': lines or 0}}


def record(**changes):
    rec = {'run_id': '%d-1' % RUN_ID, 'tested_sha': SHA, 'harness_sha256': HARNESS_SHA256,
           'execution': {'kind': 'github-actions', 'repository': harvest.REPOSITORY,
                         'workflow_ref': harvest.REPOSITORY + '/' + REHEARSAL + '@refs/heads/main', 'event': 'push',
                         'run_id': str(RUN_ID), 'run_attempt': '1', 'run_url': harvest.RUN_URL + str(RUN_ID),
                         'runner': 'ubuntu-24.04 (GitHub-hosted)'},
           'scenario': 'network root without interface_endpoints',
           'versions': {'emulator': '1.0.385', 'terraform': '1.17.0', 'awscli': '2.35.0', 'provider': '6.72.0'},
           'controls': {k: 'PASS' for k in harvest.CONTROLS}, 'operations': {k: 'PASS' for k in OPS},
           'resource_cleanup': 'PASS', 'material_cleanup': 'PASS', 'process_cleanup': 'PASS', 'unsupported_apis': [],
           'scenario_id': 'no-interface-endpoints', 'notes': [], 'failure': None}
    rec.update(changes)
    return rec


def log(rows, extra=()):
    lines = ['2026-11-20T01:00:06.0000000Z   TARGET_SHA: ' + SHA]
    lines += ['2026-11-20T01:01:00.%07dZ %s' % (i, json.dumps(r)) for i, r in enumerate(rows)]
    lines += list(extra)
    return '\n'.join(lines) + '\n'


def step2_rows(rec=None, plan=2, extra=()):
    return [{'gate': 'plan', 'status': 'PASS', 'resources': plan},
            {'gate': 'api-identity-create', 'status': 'PASS', 'vpc_id': 'vpc-0000000000000009c', 'owned': 2},
            *extra,
            {'gate': 'summary-record', 'status': 'PASS', 'record': rec or record()},
            {'gate': 'host-cleanup', 'status': 'PASS'}]


class Harvest(unittest.TestCase):
    def setUp(self):
        self.original = harvest.git_show
        harvest.git_show = fake_git

    def tearDown(self):
        harvest.git_show = self.original

    def build(self, rows, m=None, text=None):
        text = text if text is not None else log(rows)
        m = m or meta(lines=len(text.splitlines()))
        return harvest.build(m, text, REPO, '2026-11-20T02:00:00Z')

    def rejects(self, label, fn, *args):
        with self.assertRaises(Invalid) as caught:
            fn(*args)
        self.assertEqual(str(caught.exception), label)


class Step2Build(Harvest):
    def test_complete_record_is_pass_with_reviewed_addresses(self):
        entry = self.build(step2_rows())
        self.assertEqual(entry['result']['overall'], 'PASS')
        self.assertEqual(entry['roots'][0]['resource_addresses'],
                         ['module.network.aws_subnet.private["private1"]', 'module.network.aws_vpc.this'])
        self.assertTrue(entry['tested']['harness_verified_against_git'])
        self.assertEqual([r['status'] for r in entry['out_of_scope_roots'] if r['name'] == 'tfstate'],
                         ['EMULATOR_COMPATIBILITY_BLOCKED'])

    def test_failed_control_or_operation_is_never_pass(self):
        for rec in (record(controls=dict({k: 'PASS' for k in harvest.CONTROLS}, **{'7': 'FAIL'})),
                    record(operations=dict({k: 'PASS' for k in OPS}, destroy='FAIL')),
                    record(resource_cleanup='FAIL')):
            text = log(step2_rows(rec))
            entry = self.build(None, meta(conclusion='failure', lines=len(text.splitlines()),
                                          step_conclusions=['success'] * 3 + ['failure', 'failure']), text)
            self.assertEqual(entry['result']['overall'], 'FAIL')
            self.assertEqual(entry['roots'][0]['result'], 'FAIL')

    def test_success_conclusion_with_failed_record_is_still_fail(self):
        rec = record(controls=dict({k: 'PASS' for k in harvest.CONTROLS}, **{'7': 'FAIL'}))
        text = log(step2_rows(rec))
        self.assertEqual(self.build(None, meta(lines=len(text.splitlines())), text)['result']['overall'], 'FAIL')

    def test_record_identity_and_shape_mutations(self):
        cases = [
            ('summary-record-count', step2_rows() + [{'gate': 'summary-record', 'status': 'PASS', 'record': record()}]),
            ('summary-record-keys', step2_rows(dict(record(), state={'serial': 1}))),
            ('summary-identity', step2_rows(record(run_id='1-1'))),
            ('summary-identity', step2_rows(record(execution=dict(record()['execution'], run_attempt='2')))),
            ('summary-identity', step2_rows(record(execution=dict(record()['execution'],
                                                                 workflow_ref='x/y/.github/workflows/z.yml@refs/heads/main')))),
            ('summary-execution-keys', step2_rows(record(execution=dict(record()['execution'], token='x')))),
            ('summary-tested-sha', step2_rows(record(tested_sha='b' * 40))),
            ('summary-event', step2_rows(record(execution=dict(record()['execution'], event='workflow_dispatch')))),
            ('summary-harness-hash-mismatch', step2_rows(record(harness_sha256='0' * 64))),
            ('summary-plan-count', step2_rows(plan=3)),
            ('summary-versions', step2_rows(record(versions={'emulator': '1'}))),
            ('summary-controls', step2_rows(record(controls={'1': 'PASS'}))),
            ('summary-operations', step2_rows(record(operations={'apply_everything': 'PASS'}))),
            ('summary-scenario', step2_rows(record(scenario_id='all-roots'))),
        ]
        for label, rows in cases:
            with self.subTest(label=label):
                self.rejects(label, self.build, rows)

    def test_sensitive_values_in_records_are_rejected(self):
        for text, label in [('AKIA' + 'ABCDEFGHIJKLMNOP', 'entry-aws-access-key-id'),
                            ('-----BEGIN RSA PRIVATE KEY', 'entry-private-key'),
                            ('aws_secret_access_key=x', 'entry-aws-secret-field'),
                            ('owner@example.com', 'entry-email-address'),
                            ('account 123456789012', 'entry-real-account-id'),
                            ('ghp_' + 'a' * 30, 'entry-github-token'),
                            ('wJalrXUtnFEMIK7MDENG' + 'bPxRfiCYEXAMPLEKEY12', 'entry-opaque-token'),
                            ('line\nbreak', 'entry-unsafe-characters'),
                            ('pipe | breaks tables', 'entry-unsafe-characters')]:
            with self.subTest(label=label):
                self.rejects(label, self.build, step2_rows(record(scenario=text)))

    def test_log_limits_and_row_shapes(self):
        base = log(step2_rows())
        cases = [
            ('log-too-large', base + 'x' * (harvest.MAX_LOG_BYTES + 1)),
            ('log-too-many-lines', base + '\n' * (harvest.MAX_LOG_LINES + 1)),
            ('row-too-large', base + '2026-11-20T01:02:00.0Z {"gate": "x", "status": "PASS", "pad": "%s"}\n'
             % ('y' * harvest.MAX_ROW_BYTES)),
            ('row-not-json', base + '2026-11-20T01:02:00.0Z {"gate": "x", "status": }\n'),
            ('row-shape', base + '2026-11-20T01:02:00.0Z {"gate": "x", "status": "GREAT"}\n'),
            ('row-gate-name', base + '2026-11-20T01:02:00.0Z {"gate": "X Y", "status": "PASS"}\n'),
        ]
        for label, text in cases:
            with self.subTest(label=label):
                self.rejects(label, self.build, None, meta(lines=len(text.splitlines())), text)

    def test_metadata_consistency(self):
        text = log(step2_rows())
        lines = len(text.splitlines())
        m = meta(lines=lines)
        m['run']['token'] = 'x'
        self.rejects('run-unknown', self.build, None, m, text)
        self.rejects('meta-log-lines', self.build, None, meta(lines=lines + 1), text)
        self.rejects('log-head-sha', self.build, None, meta(lines=lines), text.replace(SHA, 'c' * 40))
        m = meta(lines=lines)
        m['job']['steps'][2]['name'] = 'Upload artifact'
        self.rejects('meta-step-not-in-workflow', self.build, None, m, text)
        m = meta(lines=lines, kind='unavailable')
        self.rejects('meta-log-kind-mismatch', self.build, None, m, text)

    def test_no_record_is_blocked_with_untested_controls(self):
        text = '\n'.join(['2026-11-20T01:00:06.1000000Z ##[group]Run set -euo pipefail',
                          '2026-11-20T01:00:06.2000000Z   OWNER_CHECKED_AT: 2026-11-20T10:30:00+09:00',
                          '2026-11-20T01:00:06.3000000Z   File "<stdin>", line 7, in <module>',
                          '2026-11-20T01:00:06.4000000Z AssertionError']) + '\n'
        m = meta(conclusion='failure', kind='excerpt', lines=80,
                 step_conclusions=['failure', 'skipped', 'skipped', 'skipped', 'failure'])
        entry = self.build(None, m, text)
        self.assertEqual(entry['result']['overall'], 'BLOCKED')
        self.assertEqual(entry['result']['failure']['diagnostic'], 'RUN_GATE_ASSERTION')
        self.assertIn('1794 s after the gate ran', entry['result']['failure']['cause'])
        self.assertTrue(all(v == 'NOT_TESTED' for v in entry['controls'].values()))
        self.assertEqual(entry['roots'], [])

    def test_inventory_evaluator_refuses_code(self):
        self.rejects('inventory-literal', harvest.step2_inventory,
                     "M = 'x'\nEXPECTED = {__import__('os').getcwd(): 'aws_vpc'}\nENDPOINT_TYPES = set()\n",
                     'full')
        self.rejects('inventory-missing', harvest.step2_inventory, "M = 'x'\n", 'full')


class RepresentativeBuild(Harvest):
    def rows(self, **identity):
        out = [{'gate': 'verified-preparation', 'status': 'PASS', 'sha': SHA, 'emulator': '1.0.385',
                'terraform': '1.17.0', 'awscli': '2.35.0', 'provider': '6.72.0'},
               dict({'gate': 'execution-identity', 'status': 'PASS', 'sha': SHA, 'run_id': '%d-1' % RUN_ID}, **identity)]
        out += [{'gate': 'control-' + k, 'status': 'PASS'} for k in harvest.CONTROLS]
        out += [{'gate': op, 'status': 'PASS'} for op in harvest.REPRESENTATIVE_OPERATIONS]
        out += [{'gate': 'api_create', 'status': 'PASS', 'resource_id': 'vpc-0000000000000009b'},
                {'gate': 'resource-cleanup', 'status': 'PASS'}, {'gate': 'process-cleanup', 'status': 'PASS'},
                {'gate': 'lifecycle-evidence-complete', 'status': 'PASS'}, {'gate': 'host-cleanup', 'status': 'PASS'}]
        return out

    def test_complete_rows_are_pass(self):
        text = log(self.rows())
        entry = self.build(None, meta(REPRESENTATIVE, lines=len(text.splitlines())), text)
        self.assertEqual(entry['result']['overall'], 'PASS')
        self.assertEqual(entry['roots'][0]['resource_addresses'], ['aws_vpc.proof'])

    def test_failure_rows_keep_harness_status_and_diagnostic(self):
        rows = self.rows()[:20] + [{'gate': 'auth-invalid-signature', 'status': 'BLOCKED',
                                    'diagnostic': 'AUTH_UNCLASSIFIED_REJECTION'},
                                   {'gate': 'execution', 'status': 'BLOCKED', 'diagnostic': 'AUTH_REJECTION_UNPROVEN'},
                                   {'gate': 'host-cleanup', 'status': 'PASS'}]
        text = log(rows)
        m = meta(REPRESENTATIVE, 'failure', len(text.splitlines()), step_conclusions=['success'] * 3 + ['failure'] * 2)
        entry = self.build(None, m, text)
        self.assertEqual(entry['result']['overall'], 'BLOCKED')
        self.assertEqual(entry['result']['failure']['diagnostic'], 'AUTH_UNCLASSIFIED_REJECTION')
        self.assertNotEqual(entry['roots'][0]['result'], 'PASS')

    def test_row_mutations(self):
        for label, rows in [('gate-row-keys', self.rows() + [{'gate': 'x', 'status': 'PASS', 'state': 'y'}]),
                            ('gate-identity', self.rows(run_id='1-1')),
                            ('gate-row-diagnostic', self.rows() + [{'gate': 'x', 'status': 'FAIL', 'diagnostic': 'bad code'}]),
                            ('gate-resource-id', self.rows() + [{'gate': 'x', 'status': 'PASS', 'resource_id': 'i-1'}])]:
            with self.subTest(label=label):
                text = log(rows)
                self.rejects(label, self.build, None, meta(REPRESENTATIVE, lines=len(text.splitlines())), text)


class CommittedLedger(unittest.TestCase):
    def setUp(self):
        self.entries = harvest.load_entries(LEDGER)
        self.snapshot = json.loads((LEDGER / 'actions-runs.json').read_text())
        self.passing = next(e for e in self.entries.values() if e['result']['overall'] == 'PASS'
                            and e['workflow']['kind'] == 'step2-rehearsal')
        self.blocked = next(e for e in self.entries.values() if not e['source']['summary_record']
                            and e['result']['basis'] == 'run-metadata' and e['job'] is not None)

    def rejects(self, label, entry, filename=None):
        with self.assertRaises(Invalid) as caught:
            harvest.validate(entry, filename)
        self.assertEqual(str(caught.exception), label)

    def test_committed_ledger_checks_and_reconciles(self):
        entries, problems = harvest.check(LEDGER)
        self.assertGreaterEqual(len(entries), 15)
        for run_id in (44279371023, 44279751946, 44664010985, 43791639228):
            self.assertIn((run_id, 1), entries)
        self.assertEqual(entries[(44279371023, 1)]['result']['overall'], 'BLOCKED')
        self.assertEqual(entries[(44279751946, 1)]['result']['overall'], 'PASS')
        self.assertEqual(entries[(44664010985, 1)]['result']['overall'], 'PASS')

    def test_no_out_of_scope_root_is_pass(self):
        for entry in self.entries.values():
            for root in entry['out_of_scope_roots']:
                self.assertIn(root['status'], ('NOT_TESTED', 'EMULATOR_COMPATIBILITY_BLOCKED'))
            if entry['workflow']['kind'] == 'step2-rehearsal':
                self.assertTrue(all(r['name'] in ('network', 'api') for r in entry['roots']))

    def test_pass_entry_mutations(self):
        cases = [
            ('pass-needs-all-controls', lambda e: e['controls'].update({'3': 'FAIL'})),
            ('pass-needs-every-operation', lambda e: e['roots'][0]['operations'].update(destroy='NOT_TESTED')),
            ('pass-needs-cleanup', lambda e: e['cleanup'].update(host='NOT_TESTED')),
            ('pass-needs-full-log', lambda e: e['source'].update(log='excerpt')),
            ('pass-needs-summary-record', lambda e: e['source'].update(summary_record=False)),
            ('pass-needs-success', lambda e: (e['run'].update(conclusion='failure'), e['job'].update(conclusion='failure'))),
            ('pass-needs-verified-harness', lambda e: e['tested'].update(harness_verified_against_git=False)),
            ('entry-unknown', lambda e: e.update(raw_log='x')),
            ('entry-missing', lambda e: e.pop('evidence_gaps')),
            ('run-url', lambda e: e['run'].update(url='https://example.org/run')),
            ('job-url', lambda e: e['job'].update(url=e['run']['url'] + '/job/1')),
            ('root-mismatch', lambda e: e['roots'][0].update(path='infra/services/prod/ca-central-1/network')),
            ('out-of-scope-status', lambda e: e['out_of_scope_roots'][0].update(status='PASS')),
            ('roots-not-accounted', lambda e: e['out_of_scope_roots'].pop()),
            ('out-of-scope-root', lambda e: e['out_of_scope_roots'].append(
                {'name': 'network', 'status': 'NOT_TESTED', 'reason': 'x'})),
            ('root-resource-count', lambda e: e['roots'][0]['resource_addresses'].pop()),
            ('tested-sha', lambda e: e['tested'].update(sha='b' * 40)),
            ('harvest-after-run', lambda e: e['harvest'].update(harvested_at='2020-01-01T00:00:00Z')),
            ('job-times', lambda e: e['job'].update(started_at='2020-01-01T00:00:00Z')),
            ('controls-complete', lambda e: e['controls'].pop('14')),
            ('entry-aws-access-key-id', lambda e: e['observations'].append('AKIA' + 'ABCDEFGHIJKLMNOP')),
            ('entry-state-or-plan-form', lambda e: e['observations'].append('"serial": 7')),
            ('entry-real-account-id', lambda e: e['observations'].append('arn:aws:iam::210987654321:root')),
            ('entry-too-large', lambda e: e['observations'].extend(['x' * 390] * 60) or e['untested'].extend(
                ['y' * 390] * 60) or e['residual_risk'].extend(['z' * 390] * 60)),
            ('schema', lambda e: e.update(schema='emulator-run-ledger/0')),
        ]
        for label, mutate in cases:
            with self.subTest(label=label):
                entry = copy.deepcopy(self.passing)
                mutate(entry)
                self.rejects(label, entry)

    def test_filename_must_match_run_and_attempt(self):
        self.rejects('filename', copy.deepcopy(self.passing), '1-attempt-1.json')

    def test_blocked_entry_cannot_claim_controls(self):
        entry = copy.deepcopy(self.blocked)
        entry['controls']['6'] = 'PASS'
        self.rejects('no-record-no-controls', entry)
        entry = copy.deepcopy(self.blocked)
        entry['result']['overall'] = 'PASS'
        self.rejects('pass-needs-success', entry)
        entry = copy.deepcopy(self.blocked)
        entry['result']['failure'] = None
        self.rejects('non-pass-needs-failure', entry)

    def test_reconciliation_detects_every_gap(self):
        def run(problems_key, mutate_snapshot=None, mutate_entries=None):
            snapshot, entries = copy.deepcopy(self.snapshot), dict(self.entries)
            if mutate_snapshot:
                mutate_snapshot(snapshot)
            if mutate_entries:
                mutate_entries(entries)
            return harvest.reconcile(snapshot, entries)[problems_key]

        first = sorted(self.entries)[0]
        rehearsal = self.snapshot['workflows'][REHEARSAL]
        self.assertEqual(run('unregistered', mutate_entries=lambda e: e.pop(first)), ['%d-attempt-%d' % first])
        self.assertEqual(run('not_in_actions', mutate_snapshot=lambda s: s['workflows'][REHEARSAL].pop(0)),
                         ['%d-attempt-1' % rehearsal[0]['id']])
        self.assertEqual(run('missing_attempts', mutate_snapshot=lambda s: s['workflows'][REHEARSAL][0].update(attempt=2)),
                         [])  # attempt 1 exists; attempt 2 is the unregistered latest one
        self.assertEqual(run('unregistered', mutate_snapshot=lambda s: s['workflows'][REHEARSAL][0].update(attempt=2)),
                         ['%d-attempt-2' % rehearsal[0]['id']])
        self.assertEqual(run('mismatched', mutate_snapshot=lambda s: s['workflows'][REHEARSAL][0].update(conclusion='failure')),
                         ['%d-attempt-1' % rehearsal[0]['id']])
        self.assertEqual(run('mismatched', mutate_snapshot=lambda s: s['workflows'][REHEARSAL][0].update(head_sha='d' * 40)),
                         ['%d-attempt-1' % rehearsal[0]['id']])
        self.assertEqual(run('incomplete', mutate_snapshot=lambda s: s['workflows'][REHEARSAL].append(
            dict(rehearsal[0], id=1, status='in_progress', conclusion=None))), [1])
        with self.assertRaises(Invalid):
            run('unregistered', mutate_snapshot=lambda s: s['workflows'].update({'.github/workflows/other.yml': []}))

    def test_missing_earlier_attempt_is_reported(self):
        snapshot = copy.deepcopy(self.snapshot)
        entries = dict(self.entries)
        key = (snapshot['workflows'][REHEARSAL][0]['id'], 1)
        second = copy.deepcopy(entries.pop(key))
        second['run']['attempt'] = 2
        entries[(key[0], 2)] = second
        snapshot['workflows'][REHEARSAL][0]['attempt'] = 2
        self.assertEqual(harvest.reconcile(snapshot, entries)['missing_attempts'], ['%d-attempt-1' % key[0]])

    def test_tampered_index_or_entry_fails_check(self):
        with tempfile.TemporaryDirectory() as tmp:
            for path in LEDGER.iterdir():
                (Path(tmp) / path.name).write_bytes(path.read_bytes())
            index = Path(tmp) / 'index.md'
            index.write_text(index.read_text().replace('**BLOCKED**', '**PASS**', 1))
            with self.assertRaises(Invalid) as caught:
                harvest.check(tmp)
            self.assertEqual(str(caught.exception), 'index-out-of-date')
            target = Path(tmp) / ('%d-attempt-%d.json' % sorted(self.entries)[0])
            target.unlink()
            with self.assertRaises(Invalid) as caught:
                harvest.check(tmp)
            self.assertEqual(str(caught.exception), 'not-reconciled')

    def test_build_cli_is_append_only(self):
        key = sorted(self.entries)[0]
        with tempfile.TemporaryDirectory() as tmp:
            m = Path(tmp) / 'meta.json'
            m.write_text(json.dumps(meta()))
            (Path(tmp) / ('%d-attempt-1.json' % RUN_ID)).write_text('{}')
            original = harvest.git_show
            harvest.git_show = fake_git
            try:
                text = log(step2_rows())
                m.write_text(json.dumps(meta(lines=len(text.splitlines()))))
                (Path(tmp) / 'job.log').write_text(text)
                with contextlib.redirect_stderr(io.StringIO()) as err:
                    code = harvest.main(['build', '--meta', str(m), '--log', str(Path(tmp) / 'job.log'), '--repo',
                                         str(REPO), '--out', tmp, '--harvested-at', '2026-11-20T02:00:00Z'])
            finally:
                harvest.git_show = original
            self.assertEqual(code, 1)
            self.assertIn('entry-exists-append-only', err.getvalue())
        self.assertIn(key, self.entries)

    def test_contracts_workflow_runs_the_ledger_checks(self):
        text = (REPO / '.github/workflows/aws-emulator-contracts.yml').read_text()
        self.assertIn('python3 scripts/emulator-evidence/test_harvest.py', text)
        self.assertIn('python3 scripts/emulator-evidence/harvest.py check docs/evidence/emulator-runs', text)
        self.assertIn('contents: read', text)
        self.assertNotIn('contents: write', text)


if __name__ == '__main__':
    unittest.main(verbosity=1)
