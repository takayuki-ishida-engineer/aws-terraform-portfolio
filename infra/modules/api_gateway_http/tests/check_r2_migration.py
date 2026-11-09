#!/usr/bin/env python3
"""R2 source/move guards and optional complete before/after native-root comparison.

This never runs Terraform or accesses AWS/state. Source checks supplement actual
plan checks. Empty-state mocks cannot prove deployed-state migration safety.
"""
import argparse
import importlib.util
import json
from pathlib import Path
import re
import subprocess

MODULE = Path(__file__).resolve().parents[1]
REPO = MODULE.parents[2]
ROOT = REPO / 'infra/services/dev/ca-central-1/serverless-api'
BASELINE = '87f415f5290e2cab63696e1850a6c362eef97292'
spec = importlib.util.spec_from_file_location('r1_migration', REPO / 'infra/modules/lambda_workload/tests/check_r1_migration.py')
r1 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r1)
MOVES = r1.R2_MOVES
EXPECTED = {'aws_apigatewayv2_api', 'aws_apigatewayv2_integration', 'aws_apigatewayv2_route',
            'aws_apigatewayv2_stage', 'aws_lambda_permission', 'aws_cloudwatch_log_group'}


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def verify_structure(sources=None):
    sources = sources or {p.name: p.read_text() for p in MODULE.glob('*.tf')}
    whole = '\n'.join(sources.values())
    resources = re.findall(r'^resource "([^"]+)" "([^"]+)"', whole, re.M)
    require(len(resources) == 6 and set(resources) == {(kind, 'this') for kind in EXPECTED}, 'six_owned_api_resources')
    require(not re.search(r'^\s*(?:provider\s+"|backend\s+"|data\s+")', whole, re.M), 'child_provider_backend_data')
    require('variable "access_log_group_arn"' not in whole and 'var.access_log_group_arn' not in whole, 'external_log_input_retired')
    require(re.search(r'destination_arn\s*=\s*aws_cloudwatch_log_group\.this\.arn\b', sources['main.tf']), 'stage_owned_log_source')
    require(re.search(r'depends_on\s*=\s*\[aws_apigatewayv2_route\.this, aws_lambda_permission\.this\]', sources['main.tf']), 'stage_route_permission_readiness')
    for name, attr in {'group_name':'name', 'group_arn':'arn', 'retention_in_days':'retention_in_days',
                       'deletion_protection_enabled':'deletion_protection_enabled', 'group_class':'log_group_class', 'kms_key_arn':'kms_key_id'}.items():
        require(re.search(r'output "access_log_' + name + r'"\s*\{[^}]*value\s*=\s*aws_cloudwatch_log_group\.this\.' + attr + r'\b', sources['outputs.tf']), 'provider_backed_log_output:' + name)
    for name in ('api_id', 'invoke_url', 'execution_arn'):
        block = re.search(r'output "' + name + r'"\s*\{([^}]+)\}', sources['outputs.tf'])[1]
        require(re.search(r'depends_on\s*=\s*\[aws_apigatewayv2_stage\.this, aws_lambda_permission\.this\]', block), 'output_readiness:' + name)
    retained = r1.verify_structure()
    return {'r2_move': MOVES, 'retained_r1_moves': r1.MOVES, 'root_module_instances': 4,
            'api_owned_resources': 6, 'r1_source': retained}


def source_mutations():
    require(r1.configured_fields('locals {\n  region = "local-only"\n}\nresource "test" "this" {\n  name = "configured"\n}\n') == {'name'}, 'configured_fields_excludes_locals')
    require(r1.configured_fields('resource "test" "this" {\n  region = "configured"\n}\n') == {'region'}, 'configured_fields_retains_resource_region')
    sources = {p.name:p.read_text() for p in MODULE.glob('*.tf')}
    for file, before, after in [
        ('main.tf', 'destination_arn = aws_cloudwatch_log_group.this.arn', 'destination_arn = "unrelated"'),
        ('main.tf', 'depends_on = [aws_apigatewayv2_route.this, aws_lambda_permission.this]', 'depends_on = [aws_apigatewayv2_route.this]'),
        ('outputs.tf', 'aws_cloudwatch_log_group.this.arn', '"reconstructed-unrelated-arn"'),
        ('outputs.tf', 'depends_on = [aws_apigatewayv2_stage.this, aws_lambda_permission.this]', 'depends_on = []'),
    ]:
        require(before in sources[file], 'source_mutation_precondition')
        changed = dict(sources)
        changed[file] = changed[file].replace(before, after)
        try:
            verify_structure(changed)
        except ValueError:
            continue
        raise ValueError('unsafe_source_mutation_accepted')
    return 4


def compare(before_path, after_path):
    before, schemas = r1.capture(before_path)
    after, _ = r1.capture(after_path)
    require(schemas is not None, 'provider_schema_required')
    provider = schemas['registry.terraform.io/hashicorp/aws']['resource_schemas']
    modules = {'artifact_bucket':'s3_artifact_bucket', 'secret_metadata':'secrets_manager',
               'api_access_logs':'cloudwatch_logs', 'lambda_workload':'lambda_workload', 'http_api':'api_gateway_http'}
    fields = {}
    for instance, module in modules.items():
        files = subprocess.check_output(['git','ls-tree','-r','--name-only',BASELINE,'--',f'infra/modules/{module}'], cwd=REPO, text=True).splitlines()
        old = '\n'.join(subprocess.check_output(['git','show',BASELINE+':'+f],cwd=REPO,text=True) for f in files if f.endswith('.tf') and '/tests/' not in f)
        current = 'api_gateway_http' if instance == 'api_access_logs' else module
        new = '\n'.join(p.read_text() for p in (REPO/'infra/modules'/current).glob('*.tf'))
        fields[instance] = r1.configured_fields(old) | r1.configured_fields(new)
    ignored = set()
    for run in sorted(r1.RUNS):
        old_resources = before[run]['resource_changes']
        new_resources = after[run]['resource_changes']
        require({r['module_address'] for r in old_resources} == {'module.'+m for m in modules}, 'five_baseline_modules')
        require({r['module_address'] for r in new_resources} == {'module.'+m for m in modules if m != 'api_access_logs'}, 'four_current_modules')
        require(sum(r['module_address']=='module.http_api' for r in old_resources)==5 and
                sum(r['module_address']=='module.http_api' for r in new_resources)==6, 'api_five_to_six_resources')
        expected = {MOVES.get(r['address'],r['address']):r for r in old_resources}
        actual = {r['address']:r for r in new_resources}
        require(len(expected)==len(actual)==len(new_resources)==len(old_resources)==17 and set(expected)==set(actual), 'complete_seventeen_resource_address_map')
        require(sum(r['address'] not in MOVES for r in old_resources)==16, 'sixteen_retained_addresses')
        for address, old in expected.items():
            new = actual[address]
            require(old['type']==new['type'] and old['mode']==new['mode']=='managed' and
                    old['provider_name']==new['provider_name']=='registry.terraform.io/hashicorp/aws' and
                    old['change']['before'] is None and new['change']['before'] is None and
                    old['change']['actions']==new['change']['actions']==['create'], 'resource_type_provider_lifecycle_actions')
            a,b=old['change']['after'],new['change']['after']
            attrs=provider[new['type']]['block']['attributes']
            for field in set(a)|set(b):
                if a.get(field)==b.get(field):continue
                require(attrs.get(field,{}).get('computed') is True and field not in fields[old['module_address'].split('.')[1]] and
                        field not in {'arn','invoke_arn','execution_arn'}, 'configured_or_critical_difference:'+address+':'+field)
                ignored.add(new['type']+'.'+field)
        require(len(before[run]['output_changes'])==len(after[run]['output_changes'])==8 and
                before[run]['output_changes']==after[run]['output_changes'], 'eight_root_outputs_equal')
    return {'baseline':BASELINE,'positive_plan_pairs':4,'root_module_instances_before':5,'root_module_instances_after':4,
            'resources_before':17,'resources_after':17,'api_resources_before':5,'api_resources_after':6,
            'r2_mappings':MOVES,'retained_r1_mappings':r1.MOVES,'unchanged_post_r1_addresses':16,'equal_root_outputs':8,
            'unconfigured_provider_computed_metadata_differences':sorted(ignored),
            'limitation':'Complete empty-state native mock create plans; no actual state migration, AWS identity/authorization or replacement avoidance proved.'}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--before')
    parser.add_argument('--after')
    parser.add_argument('--self-test',action='store_true')
    args=parser.parse_args()
    report={'status':'passed','structure':verify_structure(),'aws_api_calls':0,'state_operations':0}
    if args.self_test:
        report.update(r2_source_mutations=source_mutations(),r1_source_mutations=r1.structure_mutations(),move_set_mutations=r1.migration_mutations())
    if args.before or args.after:
        require(args.before and args.after, 'both_actual_captures_required')
        report['actual_plan_comparison']=compare(args.before,args.after)
    print(json.dumps(report,indent=2))


if __name__=='__main__':
    main()
