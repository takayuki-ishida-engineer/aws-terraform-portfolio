#!/usr/bin/env python3
"""Prove missing Root inputs/network fields fail in actual credential-free tests."""
import argparse
import copy
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.dont_write_bytecode=True
sys.path.insert(0,str(ROOT.parents[3]/'modules/eks_platform/tests'))
from check_platform_configuration import parse,require
sys.path.insert(0, str(Path(__file__).resolve().parents[6] / "scripts/terraform-testing"))
from isolated_root import tfvars_free_copy  # noqa: E402

REQUIRED=['aws_account_id','active_workload_az','network_reference','project','kubernetes_version','service_ipv4_cidr','cluster_subnet_keys','node_group','bootstrap_admin_role_arn','api_client_cidrs','node_https_egress_cidrs','addon_versions','ingress_subnet_key','gateway_target_port']
NETWORK=['interface_version','scope','vpc_id','vpc_cidr','private_subnet_ids','public_subnet_ids','subnet_azs','private_route_table_ids_by_subnet','public_route_table_id','nat_gateway_ids_by_az','routing_mode']


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--terraform',default='terraform');args=parser.parse_args()
    try:
        values=parse((ROOT.parents[3]/'modules/eks_platform/tests/cases.json').read_text())['root_positive']['private_dev']
        header=(ROOT/'tests/platform.tftest.hcl').read_text().split('\nrun "',1)[0]
        # Each rejection fixture supplies its own complete variable block; omit
        # native-suite global ingress defaults so missing inputs really are missing.
        header=re.sub(r'(?m)^variables \{[^}]*\}\n','',header)
        env={k:v for k,v in os.environ.items() if not k.startswith(('AWS_','TF_VAR_','TF_CLI_ARGS'))}
        env.update(TF_INPUT='0',TF_IN_AUTOMATION='1',AWS_EC2_METADATA_DISABLED='true',AWS_SHARED_CREDENTIALS_FILE='/dev/null',AWS_CONFIG_FILE='/dev/null')
        reports=[]
        # Committed terraform.tfvars would satisfy the omitted inputs; run in a tfvars-free copy.
        with tfvars_free_copy(ROOT) as (workspace,isolation):
            env.update(isolation);temporary=workspace/'tests'
            for field in REQUIRED+['network_reference.'+field for field in NETWORK]:
                supplied=copy.deepcopy(values)
                if '.' in field:supplied['network_reference'].pop(field.split('.',1)[1])
                else:supplied.pop(field)
                fixture=Path(temporary)/field;fixture.mkdir()
                variables='\n'.join(f'  {k} = {json.dumps(v)}' for k,v in supplied.items())
                (fixture/'missing.tftest.hcl').write_text(header+'\nvariables {\n'+variables+'\n}\nrun "missing_input" {\n command = plan\n}\n')
                process=subprocess.run([args.terraform,'test','-json','-verbose','-no-color','-test-directory='+str(fixture.relative_to(workspace))],cwd=workspace,env=env,capture_output=True,text=True,check=False)
                require(process.returncode==1 and not process.stderr.strip(),'required_rejected_process:'+field)
                events=[parse(line) for line in process.stdout.splitlines()]
                errors=[e['diagnostic'] for e in events if e.get('type')=='diagnostic' and e.get('diagnostic',{}).get('severity')=='error']
                allowed={'No value for required variable'} if '.' not in field else {'Invalid value for input variable','Invalid value for variable'}
                require(errors and all(e.get('summary') in allowed for e in errors)
                    and any(field.split('.')[-1] in e.get('detail','') for e in errors),'expected_required_diagnostic:'+field)
                require(not any(e.get('type')=='test_plan' for e in events),'no_successful_plan:'+field)
                terminal=[e['test_run']['status'] for e in events if e.get('type')=='test_run' and 'status' in e['test_run']]
                summaries=[e['test_summary'] for e in events if e.get('type')=='test_summary']
                require(len(terminal)==1 and terminal[0] in {'error','fail'} and len(summaries)==1 and summaries[0].get('passed')==0
                    and summaries[0].get('skipped')==0 and summaries[0].get('failed',0)+summaries[0].get('errored',0)==1,'complete_failed_evidence:'+field)
                reports.append(dict(input=field,rejected=True,terraform_exit=1,successful_plans=0))
        print(json.dumps(dict(status='passed',aws_api_calls=0,required_input_rejections=len(REQUIRED),network_field_rejections=len(NETWORK),cases=reports),indent=2))
    except (ValueError,KeyError,TypeError,OSError) as error:
        print('Platform required-input check failed: '+str(error),file=sys.stderr);return 1
    return 0


if __name__=='__main__':sys.exit(main())
