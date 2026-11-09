#!/usr/bin/env python3
"""Re-plan actual unsafe Terraform source copies, with no AWS/backend/state use."""
import argparse
import copy
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.dont_write_bytecode=True
sys.path.insert(0,str(Path(__file__).resolve().parent))
from check_platform_configuration import MODULE,REPO,parse,read_events,require,verify_plan,rejected


VARIANTS=[
 ('public_endpoint','cluster.tf',r'(endpoint_public_access\s*=\s*)false',r'\g<1>true'),
 ('no_private_endpoint','cluster.tf',r'(endpoint_private_access\s*=\s*)true',r'\g<1>false'),
 ('implicit_creator_admin','cluster.tf',r'(bootstrap_cluster_creator_admin_permissions\s*=\s*)false',r'\g<1>true'),
 ('self_managed_addon_collision','cluster.tf',r'(bootstrap_self_managed_addons\s*=\s*)false',r'\g<1>true'),
 ('wrong_node_trust','iam.tf',r'ec2\.amazonaws\.com','lambda.amazonaws.com'),
 ('admin_cni_permissions','iam.tf',r'AmazonEKS_CNI_Policy','AdministratorAccess'),
 ('public_node_interface','compute.tf',r'(associate_public_ip_address\s*=\s*)false',r'\g<1>true'),
 ('cni_uses_node_role','addons.tf',r'(service_account_role_arn\s*=\s*)aws_iam_role\.cni\.arn',r'\g<1>aws_iam_role.nodes.arn'),
 ('wrong_peer_dns','security.tf',r'(resource "aws_vpc_security_group_egress_rule" "nodes_peer_dns" \{[\s\S]*?referenced_security_group_id\s*=\s*)aws_security_group\.nodes\.id',r'\g<1>"sg-11111111111111111"'),
 ('world_sg_source','security.tf',r'referenced_security_group_id\s*=\s*aws_security_group\.nodes\.id','cidr_ipv4 = "0.0.0.0/0"'),
]


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--terraform',default='terraform');args=parser.parse_args()
    try:
        inputs=parse((MODULE/'tests/cases.json').read_text())['child_positive']['private_dev']
        header=(MODULE/'tests/platform.tftest.hcl').read_text().split('\nrun "',1)[0]
        variables='\n'.join(f'  {k} = {json.dumps(v)}' for k,v in inputs.items())
        test=header+'\nrun "unsafe_source" {\n command = plan\n variables {\n'+variables+'\n }\n assert {\n condition = aws_eks_cluster.this.vpc_config[0].endpoint_private_access && !aws_eks_cluster.this.vpc_config[0].endpoint_public_access && !aws_eks_cluster.this.access_config[0].bootstrap_cluster_creator_admin_permissions\n error_message = "Private API and explicit bootstrap access only."\n }\n}\n'
        env={k:v for k,v in os.environ.items() if not k.startswith(('AWS_','TF_VAR_','TF_CLI_ARGS'))}
        env.update(TF_DATA_DIR=str(MODULE/'.terraform'),TF_INPUT='0',TF_IN_AUTOMATION='1',AWS_EC2_METADATA_DISABLED='true',AWS_SHARED_CREDENTIALS_FILE='/dev/null',AWS_CONFIG_FILE='/dev/null')
        records=[]
        with tempfile.TemporaryDirectory(prefix='eks-unsafe-source-',dir=os.environ.get('RUNNER_TEMP','/tmp')) as temporary:
            for identifier,filename,pattern,replacement in VARIANTS:
                fixture=Path(temporary)/identifier;fixture.mkdir();(fixture/'tests').mkdir()
                for source in MODULE.glob('*.tf'):shutil.copy2(source,fixture/source.name)
                shutil.copy2(REPO/'infra/services/dev/ca-central-1/platform/.terraform.lock.hcl',fixture/'.terraform.lock.hcl')
                target=fixture/filename;modified,count=re.subn(pattern,replacement,target.read_text(),count=1);require(count==1,'source_witness:'+identifier);target.write_text(modified)
                (fixture/'tests/unsafe.tftest.hcl').write_text(test)
                with (fixture/'stderr.txt').open('w+') as stderr:
                    process=subprocess.Popen([args.terraform,'-chdir='+str(fixture),'test','-json','-verbose','-no-color'],env=env,stdout=subprocess.PIPE,stderr=stderr,text=True)
                    events=list(read_events(process.stdout));exit_code=process.wait();stderr.seek(0);require(not stderr.read().strip(),'native_source_stderr:'+identifier)
                summaries=[e['test_summary'] for e in events if e.get('type')=='test_summary'];require(len(summaries)==1,'source_summary')
                plans=[e['test_plan'] for e in events if e.get('type')=='test_plan']
                if identifier in {'public_endpoint','no_private_endpoint','implicit_creator_admin'}:
                    errors=[e.get('diagnostic',{}) for e in events if e.get('type')=='diagnostic' and e.get('diagnostic',{}).get('severity')=='error']
                    require(exit_code==1 and errors and all(e.get('summary')=='Test assertion failed' for e in errors) and len(plans)==1
                        and summaries[0].get('passed')==0 and summaries[0].get('failed')==1 and summaries[0].get('skipped')==0,'unsafe_native_rejection:'+identifier)
                    rejected(lambda:verify_plan(plans[0],inputs,'child'),identifier)
                    detected='native_assertion_and_actual_plan_rejection'
                else:
                    require(exit_code==0 and len(plans)==1 and summaries[0]==dict(status='pass',passed=1,failed=0,errored=0,skipped=0),'unsafe_plan_capture:'+identifier)
                    rejected(lambda:verify_plan(plans[0],inputs,'child'),identifier);detected='independent_actual_plan_rejection'
                records.append(dict(id=identifier,detected=True,method=detected))
        print(json.dumps(dict(status='passed',aws_api_calls=0,native_source_mutations=len(records),cases=records),indent=2))
    except (ValueError,KeyError,TypeError,OSError) as error:
        print('Native source mutation check failed: '+str(error),file=sys.stderr);return 1
    return 0


if __name__=='__main__':sys.exit(main())
