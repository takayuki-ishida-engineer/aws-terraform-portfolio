#!/usr/bin/env python3
"""R1 source ownership/move contract plus optional old/new actual mock-plan comparison.

Source ordering checks supplement actual-plan validation; they are not live-state
migration or IAM propagation evidence. No Terraform/AWS/state operation is run.
"""
import argparse
import json
from pathlib import Path
import re
import subprocess

MODULE = Path(__file__).resolve().parents[1]
REPO = MODULE.parents[2]
ROOT = REPO / 'infra/services/dev/ca-central-1/serverless-api'
MOVES = {f'module.{old}.{kind}.this': f'module.lambda_workload.{kind}.this' for old, kind in (
    ('lambda_function', 'aws_lambda_function'), ('lambda_execution_role', 'aws_iam_role'),
    ('lambda_execution_role', 'aws_iam_role_policy'), ('lambda_logs', 'aws_cloudwatch_log_group'))}
RESOURCES = {destination.split('.', 2)[2] for destination in MOVES.values()}
RUNS = {'default_secret_read_disabled', 'enabled_exact_secret_read', 'node_runtime', 'java_runtime'}


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def verify_structure(module_sources=None):
    sources = module_sources or {p.name: p.read_text() for p in MODULE.glob('*.tf')}
    whole = '\n'.join(sources.values())
    declarations = re.findall(r'^resource "([^"]+)" "([^"]+)"', whole, re.M)
    require(len(declarations) == 4 and {kind + '.' + name for kind, name in declarations} == RESOURCES, 'owned_resource_inventory')
    require(not re.search(r'^\s*(?:provider\s+"|backend\s+"|data\s+")', whole, re.M), 'child_provider_backend_or_data')
    require(not re.search(r'variable\s+"(?:execution_role_arn|log_group_arn)"', whole), 'external_owned_arn_input')
    function = sources['main.tf']
    for pattern, reason in [
        (r'\brole\s*=\s*aws_iam_role\.this\.arn\b', 'source_role_binding'),
        (r'\blog_group\s*=\s*aws_cloudwatch_log_group\.this\.name\b', 'source_log_binding'),
        (r'\bdepends_on\s*=\s*\[\s*aws_iam_role_policy\.this\s*\]', 'source_policy_readiness'),
    ]:
        require(re.search(pattern, function), reason)
    require('aws_cloudwatch_log_group.this.arn' in sources['policies.tf'], 'source_policy_group_binding')
    moved = (ROOT / 'moved.tf').read_text()
    pairs = re.findall(r'moved\s*\{\s*from\s*=\s*(\S+)\s+to\s*=\s*(\S+)\s*\}', moved)
    require(len(pairs) == 4 and dict(pairs) == MOVES, 'four_resource_moves')
    calls = re.findall(r'^module "([^"]+)"', (ROOT / 'main.tf').read_text(), re.M)
    require(set(calls) == {'artifact_bucket', 'secret_metadata', 'api_access_logs', 'lambda_workload', 'http_api'} and len(calls) == 5, 'root_five_modules')
    return {'moves': MOVES, 'resources': sorted(RESOURCES), 'root_module_instances': 5,
            'ordering_evidence': 'Source dependency contract plus actual resource bindings; no service propagation or live state verified.'}


def structure_mutations():
    source = {p.name: p.read_text() for p in MODULE.glob('*.tf')}
    cases = [
        ('remove-policy-readiness', 'main.tf', 'depends_on = [aws_iam_role_policy.this]', 'depends_on = []'),
        ('wrong-role-reference', 'main.tf', 'aws_iam_role.this.arn', '"synthetic-unrelated-role"'),
        ('wrong-log-reference', 'main.tf', 'aws_cloudwatch_log_group.this.name', '"/synthetic/unrelated"'),
    ]
    for name, file, before, after in cases:
        changed = dict(source)
        require(before in changed[file], 'mutation_source_precondition:' + name)
        changed[file] = changed[file].replace(before, after)
        try:
            verify_structure(changed)
        except ValueError:
            continue
        raise ValueError('unsafe_source_mutation_accepted:' + name)
    return len(cases)


def capture(path):
    plans, passed, summaries = {}, set(), []
    schemas = None
    for line in Path(path).open():
        event = json.loads(line)
        if event.get('type') == 'test_run' and 'status' in event.get('test_run', {}):
            require(event['test_run']['status'] == 'pass', 'comparison_nonpassing_run')
            passed.add(event['@testrun'])
        if event.get('type') == 'test_plan':
            name = event['@testrun']
            require(name in passed and name not in plans, 'comparison_plan_order')
            p = event['test_plan']
            if name in RUNS:
                require(len(p.get('resource_changes', [])) == 17, 'comparison_inventory')
                plans[name] = {key: p.get(key, {}) for key in ('resource_changes', 'output_changes')}
                schemas = schemas or p.get('provider_schemas')
        if event.get('type') == 'test_summary':
            summaries.append(event['test_summary'])
    require(summaries == [{'status': 'pass', 'passed': 5, 'failed': 0, 'errored': 0, 'skipped': 0}]
        and set(plans) == RUNS and passed == RUNS | {'invalid_account_id'}, 'comparison_capture_incomplete')
    return plans, schemas


def configured_fields(source):
    """Formatted top-level resource attributes; nested configured blocks compare whole.

    The inspected implementations format resource attributes at two spaces. This
    is used only to refuse ignoring a changed configured optional-computed field.
    """
    return set(re.findall(r'^  ([a-zA-Z0-9_]+)\s*=', source, re.M))


def compare(before, after, baseline):
    old, schemas = capture(before)
    new, _ = capture(after)
    require(schemas is not None, 'comparison_provider_schema_required')
    provider = schemas['registry.terraform.io/hashicorp/aws']['resource_schemas']
    # These are source locations, not IDs or state. Reject an unavailable baseline.
    module_map = {'artifact_bucket': 's3_artifact_bucket', 'secret_metadata': 'secrets_manager',
        'api_access_logs': 'cloudwatch_logs', 'lambda_logs': 'cloudwatch_logs',
        'lambda_function': 'lambda', 'lambda_execution_role': 'lambda_execution_role', 'http_api': 'api_gateway_http'}
    fields = {}
    for instance, module in module_map.items():
        files = subprocess.check_output(['git', 'ls-tree', '-r', '--name-only', baseline, '--', f'infra/modules/{module}'], cwd=REPO, text=True).splitlines()
        old_source = '\n'.join(subprocess.check_output(['git', 'show', baseline + ':' + name], cwd=REPO, text=True)
            for name in files if name.endswith('.tf') and '/tests/' not in name)
        current = 'lambda_workload' if instance in {'lambda_logs', 'lambda_function', 'lambda_execution_role'} else module
        new_source = '\n'.join(p.read_text() for p in (REPO / 'infra/modules' / current).glob('*.tf'))
        fields[instance] = configured_fields(old_source) | configured_fields(new_source)
    ignored = set()
    for run in sorted(RUNS):
        expected = {MOVES.get(r['address'], r['address']): r for r in old[run]['resource_changes']}
        actual = {r['address']: r for r in new[run]['resource_changes']}
        require(len(expected) == len(actual) == 17 and set(actual) == set(expected), 'comparison_address_inventory')
        unchanged = sum(r['address'] not in MOVES for r in old[run]['resource_changes'])
        require(unchanged == 13, 'comparison_thirteen_retained')
        for address, old_resource in expected.items():
            current = actual[address]
            require(old_resource['type'] == current['type'] and old_resource['mode'] == current['mode'] == 'managed'
                and old_resource['change']['actions'] == current['change']['actions'] == ['create'], 'comparison_type_mode_actions')
            a, b = old_resource['change']['after'], current['change']['after']
            attrs = provider[current['type']]['block']['attributes']
            instance = old_resource['module_address'].split('.')[1]
            for field in set(a) | set(b):
                if a.get(field) == b.get(field):
                    continue
                schema = attrs.get(field, {})
                # Native mocks generate unconfigured SDK-computed metadata randomly.
                # Never ignore a configured field or a bound/operational ARN.
                require(schema.get('computed') is True and field not in fields[instance]
                    and field not in {'arn', 'invoke_arn', 'execution_arn'},
                    'comparison_effective_setting:' + address + ':' + field)
                ignored.add(current['type'] + '.' + field)
        require(old[run]['output_changes'] == new[run]['output_changes'], 'comparison_root_output_changes')
    return {'positive_plan_pairs': len(RUNS), 'managed_resources_per_plan': 17,
        'mapped_resources': 4, 'unchanged_addresses': 13, 'root_outputs_equal': 8,
        'unconfigured_provider_computed_metadata_differences': sorted(ignored),
        'limitations': 'Native empty-state mock create plans do not prove actual state moves, recreation avoidance or AWS propagation.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--before')
    parser.add_argument('--after')
    parser.add_argument('--baseline', default='43adc3a827a265520ff822595355a91001e7e1af')
    args = parser.parse_args()
    report = {'structure': verify_structure(), 'source_dependency_mutations': structure_mutations()}
    if args.before or args.after:
        require(args.before and args.after, 'comparison_requires_both_captures')
        report['actual_plan_comparison'] = compare(args.before, args.after, args.baseline)
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
