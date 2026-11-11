#!/usr/bin/env python3
"""Actual unsafe child source re-plans, including deliberately bypassed validation."""
import argparse,json,os,re,shutil,subprocess,sys,tempfile
from pathlib import Path
sys.dont_write_bytecode=True
sys.path.insert(0,str(Path(__file__).resolve().parent))
from check_ingress import MODULE,ROOT,definitions,read_events,require,verify_plan,reject

def main():
    a=argparse.ArgumentParser();a.add_argument('--terraform',default='terraform');args=a.parse_args()
    variants=[
      ('wildcard_irsa','iam.tf',r'Federated\s*=\s*var.controller_oidc.provider_arn','Federated = "*"'),
      ('unrestricted_registration','iam.tf',r'Resource\s*=\s*aws_lb_target_group.gateway.arn','Resource = "*"'),
      ('controller_sg_write','iam.tf',r'"elasticloadbalancing:DeregisterTargets"','"elasticloadbalancing:DeregisterTargets", "ec2:AuthorizeSecurityGroupIngress"'),
      ('public_nlb','main.tf',r'(internal\s*=\s*)true',r'\g<1>false'),
      ('tls_listener','main.tf',r'(resource "aws_lb_listener"[\s\S]*?protocol\s*=\s*)"TCP"',r'\g<1>"TLS"'),
      ('instance_targets','main.tf',r'(target_type\s*=\s*)"ip"',r'\g<1>"instance"'),
      ('no_nlb_sg','main.tf',r'(security_groups\s*=\s*)\[aws_security_group.nlb.id\]',r'\g<1>[]'),
      ('world_ingress','security.tf',r'(resource "aws_vpc_security_group_ingress_rule" "nlb_clients" \{[\s\S]*?)referenced_security_group_id\s*=\s*aws_security_group.vpc_link_client.id',r'\g<1>cidr_ipv4 = "0.0.0.0/0"'),
      ('no_node_ingress','security.tf',r'resource "aws_vpc_security_group_ingress_rule" "nodes_targets" \{[^}]*\{[^}]*\}\)[\s\S]*?\n\}', ''),
      ('fabricated_node_sg','security.tf',r'(referenced_security_group_id\s*=\s*)var.eks_security_groups.nodes',r'\g<1>"sg-11111111111111111"'),
      ('dynamic_target','main.tf',None,'\nresource "aws_lb_target_group_attachment" "forbidden" {\n target_group_arn=aws_lb_target_group.gateway.arn\n target_id="192.0.2.10"\n port=var.backend_target_port\n}\n'),
      ('disabled_interface_validation','variables.tf',r'condition\s*=\s*try\(var.network_reference.interface_version[^\n]*','condition = var.network_reference.interface_version == var.network_reference.interface_version'),
    ]
    env={k:v for k,v in os.environ.items() if not k.startswith(('AWS_','TF_VAR_','TF_CLI_ARGS'))}
    env.update(TF_DATA_DIR=str(MODULE/'.terraform'),TF_INPUT='0',TF_IN_AUTOMATION='1',AWS_EC2_METADATA_DISABLED='true',AWS_SHARED_CREDENTIALS_FILE='/dev/null',AWS_CONFIG_FILE='/dev/null')
    header=(MODULE/'tests/ingress.tftest.hcl').read_text().split('\nrun "',1)[0];results=[]
    with tempfile.TemporaryDirectory(prefix='ingress-source-',dir=os.environ.get('RUNNER_TEMP','/tmp')) as temp:
      for name,file,pattern,replacement in variants:
        fixture=Path(temp)/name;fixture.mkdir();(fixture/'tests').mkdir()
        for source in MODULE.glob('*.tf'):shutil.copy2(source,fixture/source.name)
        shutil.copy2(ROOT/'.terraform.lock.hcl',fixture/'.terraform.lock.hcl')
        p=fixture/file
        if pattern is None:p.write_text(p.read_text()+replacement)
        elif name=='no_node_ingress':
          text=p.read_text();start=text.index('resource "aws_vpc_security_group_ingress_rule" "nodes_targets"');end=text.index('\nresource ',start+1);p.write_text(text[:start]+text[end:]);main=fixture/'main.tf';main.write_text(main.read_text().replace(', aws_vpc_security_group_ingress_rule.nodes_targets',''))
        else:
          text,count=re.subn(pattern,replacement,p.read_text(),count=1);require(count==1,'mutation_witness:'+name);p.write_text(text)
        values=definitions('child')[0]['private_dev'].copy()
        if name=='disabled_interface_validation':values['network_reference']=dict(values['network_reference'],interface_version=2)
        inputs='\n'.join(k+' = '+json.dumps(v) for k,v in values.items())
        (fixture/'tests/source.tftest.hcl').write_text(header+'\nrun "unsafe" {\n command=plan\n variables {\n'+inputs+'\n}\n}\n')
        process=subprocess.Popen([args.terraform,'-chdir='+str(fixture),'test','-json','-verbose','-no-color'],env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        events=list(read_events(process.stdout));stderr=process.stderr.read();code=process.wait()
        require(code==0 and not stderr.strip(),'mutation_actual_plan:'+name+':'+str([(e.get('diagnostic',{}).get('summary'),e.get('diagnostic',{}).get('detail')) for e in events if e.get('type')=='diagnostic']))
        plans=[e['test_plan'] for e in events if e.get('type')=='test_plan'];summary=[e['test_summary'] for e in events if e.get('type')=='test_summary']
        require(len(plans)==1 and summary==[dict(status='pass',passed=1,failed=0,errored=0,skipped=0)],'source_complete_capture:'+name)
        reject(lambda:verify_plan(plans[0],values,'child'),name);results.append(name)
    print(json.dumps(dict(status='passed',aws_api_calls=0,actual_source_mutations=len(results),detected=results),indent=2))
if __name__=='__main__':main()
