#!/usr/bin/env python3
"""Render the non-secret Step 2 rehearsal report as a readable job summary.

Reads the container's gate rows plus the host-cleanup row, validates the run
identity and completeness, and writes Markdown to $GITHUB_STEP_SUMMARY (stdout
as well). Missing or partial evidence never renders as success: the exit code
is 0 only for a complete PASS with every control, operation and cleanup PASS.
"""
import json
import os
import re
import sys
from pathlib import Path

CONTROLS = {
    '1': 'Verified official tools (SHA-256, publisher GPG, versions)',
    '2': 'Loopback-only HTTPS endpoint',
    '3': 'Emulator-generated credentials; authentication enforced',
    '4': 'Strict TLS verification with the emulator CA',
    '5': 'Telemetry off',
    '6': 'Isolated network namespace (loopback only)',
    '7': 'Real AWS endpoints unreachable (ENETUNREACH)',
    '8': 'Synthetic account 000000000000',
    '9': 'Provider endpoint and account guard',
    '10': 'Disposable root and empty local State',
    '11': 'Plan inspection before every apply',
    '12': 'Exact resource identity',
    '13': 'Independent API checks after create, update and destroy',
    '14': 'Confirmed cleanup (resources, material, process)',
}
OPERATIONS = ['plan', 'create', 'api_create', 'read', 'update_plan', 'update', 'api_update', 'no_op',
              'destroy_plan', 'destroy', 'state_empty', 'api_absence', 'baseline_preserved']
SAFE = re.compile(r'^[A-Za-z0-9 _.,;:/@()\-\[\]"=+]{0,300}$')


class Invalid(Exception):
    pass


def text(value):
    value = str(value)
    if not SAFE.match(value):
        raise Invalid('unsafe-text')
    return value.replace('|', '/')


def load(path):
    rows = []
    for line in Path(path).read_text().splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if not isinstance(row, dict) or not isinstance(row.get('gate'), str) or not isinstance(row.get('status'), str):
            raise Invalid('row-shape')
        rows.append(row)
    return rows


def evaluate(rows, env):
    """Return (record or None, host status, list of problems)."""
    problems = []
    records = [r for r in rows if r['gate'] == 'summary-record']
    record = records[0].get('record') if len(records) == 1 else None
    if len(records) != 1 or not isinstance(record, dict):
        problems.append('summary record missing or duplicated')
        record = None
    host = rows[-1]['status'] if rows and rows[-1]['gate'] == 'host-cleanup' else 'MISSING'
    if host != 'PASS':
        problems.append('host cleanup ' + host)
    if env.get('EXECUTION_STATUS', 'success') != 'success':
        problems.append('execution step ' + env.get('EXECUTION_STATUS', ''))
    if env.get('GITHUB_ACTIONS') == 'true' and env.get('OWNER_ATTESTATION_ACCEPTED') != 'true':
        problems.append('owner attestation not accepted')
    if record is not None:
        execution = record.get('execution') or {}
        if env.get('GITHUB_ACTIONS') == 'true':
            expected = env.get('GITHUB_RUN_ID', '') + '-' + env.get('GITHUB_RUN_ATTEMPT', '')
            if (execution.get('kind') != 'github-actions' or record.get('run_id') != expected
                    or execution.get('run_id') != env.get('GITHUB_RUN_ID') or record.get('tested_sha') != env.get('TARGET_SHA')):
                problems.append('run identity mismatch')
        if any(record.get('controls', {}).get(k) != 'PASS' for k in CONTROLS):
            problems.append('not every control PASS')
        if any(record.get('operations', {}).get(k) != 'PASS' for k in OPERATIONS):
            problems.append('not every operation PASS')
        for key in ('resource_cleanup', 'material_cleanup', 'process_cleanup'):
            if record.get(key) != 'PASS':
                problems.append(key.replace('_', ' ') + ' ' + str(record.get(key)))
        if record.get('failure'):
            problems.append('failure recorded')
    return record, host, problems


def render(record, host, problems, rows, env):
    complete = not problems
    out = ['## AWS Emulator Step 2 rehearsal: network root', '']
    out.append('**Result: ' + ('PASS** (all 14 controls, all 13 lifecycle operations and cleanup)' if complete
                               else 'INCOMPLETE** (' + text('; '.join(problems)) + ')'))
    out.append('')
    if record is None:
        out.append('No summary record was produced; the gate rows below are the only evidence.')
        out += ['', '| Gate | Status |', '| --- | --- |']
        out += ['| ' + text(r['gate']) + ' | ' + text(r['status']) + ' |' for r in rows]
        return '\n'.join(out) + '\n'
    execution = record.get('execution') or {}
    if execution.get('kind') == 'github-actions':
        executed = ('GitHub Actions run [' + text(execution['run_id']) + ' (attempt ' + text(execution['run_attempt']) + ')](' +
                    text(execution['run_url']) + '), workflow `' + text(execution['workflow_ref']) + '`, ' + text(execution['runner']))
    else:
        executed = 'Local operator run (not a CI run)'
    versions = record.get('versions', {})
    out += ['| Item | Value |', '| --- | --- |',
            '| Executed by | ' + executed + ' |',
            '| Tested SHA | `' + text(record.get('tested_sha')) + '` |',
            '| Scenario | ' + text(record.get('scenario')) + ' |',
            '| Harness | `scripts/emulator-rehearsal/rehearse.py`, SHA-256 `' + text(record.get('harness_sha256')) + '` |',
            '| Versions | Emulator ' + text(versions.get('emulator')) + ', Terraform ' + text(versions.get('terraform')) +
            ', AWS provider ' + text(versions.get('provider')) + ', AWS CLI ' + text(versions.get('awscli')) + ' |',
            '| Billing | ' + ('Owner-attested at dispatch; not API-audited' if env.get('OWNER_ATTESTATION_ACCEPTED') == 'true'
                              else 'not applicable (local)' if execution.get('kind') != 'github-actions' else 'NOT VERIFIED') + ' |',
            '', '### Mandatory controls', '', '| # | Control | Result |', '| --- | --- | --- |']
    out += ['| ' + k + ' | ' + v + ' | ' + text(record.get('controls', {}).get(k, 'MISSING')) + ' |' for k, v in CONTROLS.items()]
    out += ['', '### Lifecycle operations', '', '| Operation | Result |', '| --- | --- |']
    out += ['| ' + k + ' | ' + text(record.get('operations', {}).get(k, 'MISSING')) + ' |' for k in OPERATIONS]
    out += ['', '### Observations', '']
    for row in rows:
        if row['gate'] == 'refresh-convergence':
            out.append('- Refresh: reviewed computed-field convergence on ' +
                       text(', '.join(d['address'] for d in row.get('drift', []))) + '; second refresh unchanged')
        if row['gate'] == 'sg-default-egress-probe':
            out.append('- Security group probe: provider-form revoke (ports 0) ' + text(row.get('revoke_provider_form_ports_0')) +
                       ', revoke without ports ' + text(row.get('revoke_without_ports')) + '; interface endpoint API probe ' +
                       text((row.get('interface_endpoint') or {}).get('create')))
        if row['gate'] == 'failure':
            out.append('- Failure: operation ' + text(row.get('operation')) + ', ' + text(row.get('label')) +
                       (', API ' + text(row['api']) if row.get('api') else ''))
    out += ['', '### Cleanup', '', '| Receipt | Result |', '| --- | --- |',
            '| Resources (Terraform destroy or recovery, verified absent) | ' + text(record.get('resource_cleanup')) + ' |',
            '| Material (credentials, CA, State, plans, logs on tmpfs) | ' + text(record.get('material_cleanup')) + ' |',
            '| Emulator process | ' + text(record.get('process_cleanup')) + ' |',
            '| Host (container, image, context) | ' + text(host) + ' |',
            '', 'Emulator results are not evidence of real AWS deployment, IAM enforcement, networking, cost or availability.']
    return '\n'.join(out) + '\n'


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    env = dict(os.environ)
    try:
        rows = load(argv[0])
        record, host, problems = evaluate(rows, env)
        markdown = render(record, host, problems, rows, env)
    except (OSError, ValueError, KeyError, IndexError, TypeError, Invalid) as error:
        markdown = '## AWS Emulator Step 2 rehearsal: network root\n\n**Result: BLOCKED** (evidence unreadable: ' + type(error).__name__ + ')\n'
        problems = ['unreadable']
    print(markdown)
    if env.get('GITHUB_STEP_SUMMARY'):
        with open(env['GITHUB_STEP_SUMMARY'], 'a') as summary:
            summary.write(markdown)
    return 0 if not problems else 1


if __name__ == '__main__':
    sys.exit(main())
