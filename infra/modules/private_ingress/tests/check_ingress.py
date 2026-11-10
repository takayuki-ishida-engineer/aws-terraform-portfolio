#!/usr/bin/env python3
"""Independent actual NLB/SG plan contracts; no AWS calls or source-only acceptance."""
import argparse
import copy
import importlib.util
import json
import re
import sys
from pathlib import Path
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
MODULE=HERE.parent
REPO=HERE.parents[3]
ROOT=REPO/'infra/services/dev/ca-central-1/platform'
PROVIDER='registry.terraform.io/hashicorp/aws'

def require(ok,label):
    if not ok:raise ValueError(label)
def pairs(items):
    d={}
    for k,v in items:
        require(k not in d,'duplicate_key');d[k]=v
    return d
def parse(text):
    return json.loads(text,object_pairs_hook=pairs,parse_constant=lambda x:(_ for _ in ()).throw(ValueError('nonfinite')))
def unknown(x):
    if isinstance(x,dict):return any(unknown(v) for v in x.values())
    if isinstance(x,list):return any(unknown(v) for v in x)
    require(type(x) is bool,'unknown_marker');return x
def read_events(stream):
    for line in stream:
        e=parse(line);require(isinstance(e,dict),'event_object')
        if e.get('type')=='test_plan':e.get('test_plan',{}).pop('provider_schemas',None)
        yield e
def definitions(scope):
    p=HERE/'cases.json' if scope=='child' else REPO/'infra/modules/eks_platform/tests/cases.json'
    d=parse(p.read_text());return (d['positive'],d['negative']) if scope=='child' else (d['root_positive'],d['root_negative'])
def root_values(plan,v):
    rows={r['address']:r for r in plan['resource_changes']}
    def sg(label):
        c=rows['module.eks_platform.aws_security_group.'+label]['change']
        require(not unknown(c['after_unknown'].get('id',False)),'unknown_eks_group');return c['after']['id']
    net=v['network_reference']
    require(net['scope']==dict(environment='dev',region='ca-central-1',partition='aws',account_id=v['aws_account_id']) and net['interface_version']==1,'root_scope')
    require(net['subnet_azs']['private'][v['ingress_subnet_key']]==v['active_workload_az'],'dev_ingress_az')
    return dict(expected_scope=net['scope'],network_reference=net,name=v['ingress_name'],subnet_keys=[v['ingress_subnet_key']],backend_target_port=v['gateway_target_port'],eks_security_groups=dict(cluster=sg('cluster'),nodes=sg('nodes')),cross_zone_enabled=False,deletion_protection=v.get('deletion_protection',True),tags=dict(v.get('tags',{}),Environment='dev',Service='platform',Project='aws-terraform-portfolio',ManagedBy='Terraform'))
def verify_root_ingress(plan,v):return verify_plan(plan,root_values(plan,v),'root')
def verify_plan(plan,v,scope):
    n=v['network_reference'];s=v['expected_scope'];keys=v['subnet_keys'];port=v['backend_target_port'];eks=v['eks_security_groups']
    require(s['partition']=='aws' and s['region']=='ca-central-1' and s['environment'] in {'dev','stg','prod'} and re.fullmatch(r'\d{12}',s['account_id']),'scope')
    require(n['scope']==s and n['interface_version']==1,'network_scope')
    require(re.fullmatch(r'vpc-([0-9a-f]{8}|[0-9a-f]{17})',n['vpc_id']),'vpc_id')
    private=n['private_subnet_ids'];public=n['public_subnet_ids'];az=n['subnet_azs']['private']
    require(private and set(private)==set(az),'private_map')
    ids=list(private.values())+list(public.values());require(len(ids)==len(set(ids)) and all(re.fullmatch(r'subnet-([0-9a-f]{8}|[0-9a-f]{17})',x) for x in ids),'unique_private_public')
    require(all(re.fullmatch(s['region']+'[a-z]',x) for x in az.values()),'az_region')
    require(keys and set(keys)<=set(private) and len({az[k] for k in keys})==len(keys),'private_subnet_selection')
    require(type(port) is int and 1<=port<=65535,'backend_port')
    require(re.fullmatch(r'[a-z][a-z0-9-]{0,19}',v['name']) and not v['name'].startswith('internal-') and not v['name'].endswith('-'),'name')
    require(len(set(eks.values()))==2 and all(re.fullmatch(r'sg-([0-9a-f]{8}|[0-9a-f]{17})',x) for x in eks.values()),'custom_eks_groups')
    require(plan.get('plan_format_version')=='1.2','plan_format')
    prefix='module.private_ingress.' if scope=='root' else '';rows={}
    for r in plan['resource_changes']:
        if scope=='root' and r['address'].startswith('module.eks_platform.'):continue
        addr=r['address'];require(addr.startswith(prefix),'module_boundary');addr=addr[len(prefix):]
        require(addr not in rows and addr==r['type']+'.'+r['name'] and r.get('module_address','')==prefix.rstrip('.') and r.get('index') is None,'unique_resource_identity')
        require(r['mode']=='managed' and r['provider_name']==PROVIDER and r['change']['actions']==['create'] and r['change']['before'] is None,'resource_owner')
        rows[addr]=r['change']
    names={'aws_lb.this','aws_lb_listener.https_passthrough','aws_lb_target_group.gateway','aws_security_group.nlb','aws_security_group.vpc_link_client',
        'aws_vpc_security_group_egress_rule.client_nlb','aws_vpc_security_group_ingress_rule.nlb_clients','aws_vpc_security_group_egress_rule.nlb_targets','aws_vpc_security_group_ingress_rule.nodes_targets','aws_vpc_security_group_egress_rule.cluster_webhook','aws_vpc_security_group_ingress_rule.nodes_webhook'}
    require(set(rows)==names,'exact_11_owners_no_dynamic_registration')
    def value(a,k):
        c=rows[a];require(k in c['after'] and not unknown(c['after_unknown'].get(k,False)),'critical_value:'+a+':'+k);return c['after'][k]
    def same(a,k,x):require(value(a,k)==x,'contract:'+a+':'+k)
    lb='aws_lb.this';tg='aws_lb_target_group.gateway';li='aws_lb_listener.https_passthrough'
    nlb=value('aws_security_group.nlb','id');client=value('aws_security_group.vpc_link_client','id');require(len({nlb,client,*eks.values()})==4,'distinct_groups')
    for a in ['aws_security_group.nlb','aws_security_group.vpc_link_client']:
        same(a,'vpc_id',n['vpc_id']);same(a,'ingress',[]);same(a,'egress',[])
    for k,x in dict(name=v['name'],internal=True,load_balancer_type='network',ip_address_type='ipv4',security_groups=[nlb],subnets=sorted(private[k] for k in keys),enable_cross_zone_load_balancing=v['cross_zone_enabled'],enable_deletion_protection=v.get('deletion_protection',True),enforce_security_group_inbound_rules_on_private_link_traffic='on',vpc_id=n['vpc_id'],subnet_mapping=[]).items():same(lb,k,x)
    arnbase='arn:aws:elasticloadbalancing:'+s['region']+':'+s['account_id']+':'
    for a,kind in [(lb,'loadbalancer/net/'),(tg,'targetgroup/'),(li,'listener/net/')]:
        require(value(a,'arn').startswith(arnbase+kind),'arn_scope:'+a)
    require(value(lb,'dns_name') and value(lb,'zone_id'),'computed_dns_zone')
    for k,x in dict(name=v['name']+'-gateway',port=port,protocol='TCP',target_type='ip',ip_address_type='ipv4',vpc_id=n['vpc_id'],preserve_client_ip='false',proxy_protocol_v2=False,load_balancing_cross_zone_enabled='use_load_balancer_configuration',connection_termination=True,deregistration_delay='300').items():same(tg,k,x)
    hc=value(tg,'health_check');require(len(hc)==1,'single_health_check')
    for k,x in dict(enabled=True,port='traffic-port',protocol='TCP',interval=30,healthy_threshold=3,unhealthy_threshold=3).items():require(hc[0][k]==x,'health:'+k)
    same(li,'load_balancer_arn',value(lb,'arn'));same(li,'port',443);same(li,'protocol','TCP');same(li,'certificate_arn',None);same(li,'alpn_policy',None);same(li,'mutual_authentication',[])
    actions=value(li,'default_action');require(len(actions)==1 and actions[0]['type']=='forward' and actions[0]['target_group_arn']==value(tg,'arn') and not actions[0]['forward'] and not actions[0]['redirect'] and not actions[0]['fixed_response'],'actual_forward')
    flows=[('egress','client_nlb',client,nlb,443),('ingress','nlb_clients',nlb,client,443),('egress','nlb_targets',nlb,eks['nodes'],port),('ingress','nodes_targets',eks['nodes'],nlb,port),('egress','cluster_webhook',eks['cluster'],eks['nodes'],9443),('ingress','nodes_webhook',eks['nodes'],eks['cluster'],9443)]
    for direction,label,owner,peer,p in flows:
        a='aws_vpc_security_group_'+direction+'_rule.'+label
        for k,x in dict(security_group_id=owner,referenced_security_group_id=peer,ip_protocol='tcp',from_port=p,to_port=p,cidr_ipv4=None,cidr_ipv6=None,prefix_list_id=None).items():same(a,k,x)
    for a in names:require(all(value(a,'tags').get(k)==x for k,x in v.get('tags',{}).items() if k!='Name'),'governance_tags')
    out=dict(interface_version=1,scope=s,nlb_arn=value(lb,'arn'),nlb_dns_name=value(lb,'dns_name'),nlb_zone_id=value(lb,'zone_id'),listener_arn=value(li,'arn'),target_group_arn=value(tg,'arn'),target_group_name=value(tg,'name'),nlb_security_group_id=nlb,vpc_link_client_security_group_id=client,private_subnet_ids={k:private[k] for k in keys},vpc_id=value(tg,'vpc_id'),backend_target_port=value(tg,'port'),cross_zone_enabled=value(lb,'enable_cross_zone_load_balancing'))
    outputs=plan.get('output_changes',{});require(set(outputs)==({'platform','private_ingress'} if scope=='root' else {'private_ingress'}),'output_inventory')
    o=outputs['private_ingress'];require(o['actions']==['create'] and o['before'] is None and o['after']==out and not unknown(o['after_unknown']) and o['after_sensitive'] is False,'actual_ingress_output')
    return len(rows)
def source_contract(sources=None):
    paths=list(MODULE.glob('*.tf'))+[ROOT/'ingress.tf',ROOT/'ingress_variables.tf']
    sources=sources or {str(p.relative_to(REPO)):p.read_text() for p in paths}
    norm=lambda path:re.sub(r'\s+','',re.sub(r'(?m)#.*$','',sources[path]))
    child='infra/modules/private_ingress/';root='infra/services/dev/ca-central-1/platform/'
    main=norm(child+'main.tf');variables=norm(child+'variables.tf');wiring=norm(root+'ingress.tf');rootvars=norm(root+'ingress_variables.tf')
    for expr in ['security_groups=[aws_security_group.nlb.id]','load_balancer_arn=aws_lb.this.arn','target_group_arn=aws_lb_target_group.gateway.arn','port=var.backend_target_port','aws_vpc_security_group_ingress_rule.nodes_targets]']:
        require(expr in main,'actual_source_reference:'+expr)
    for expr in ['cluster=module.eks_platform.security_group_ids.cluster','nodes=module.eks_platform.security_group_ids.nodes','subnet_keys=toset([var.ingress_subnet_key])','backend_target_port=var.gateway_target_port','network_reference=var.network_reference','expected_scope=local.expected_scope','cross_zone_enabled=false','providers={aws=aws}']:
        require(expr in wiring,'root_binding:'+expr)
    require('var.network_reference.subnet_azs.private[var.ingress_subnet_key]==var.active_workload_az' in rootvars,'dev_az_validation')
    require('var.backend_target_port>=1&&var.backend_target_port<=65535&&floor(var.backend_target_port)==var.backend_target_port' in variables,'child_port_validation')
    require('var.network_reference.scope==var.expected_scope' in variables and 'var.network_reference.interface_version==1' in variables,'scope_validation')
    all_child='\n'.join(sources[child+p.name] for p in MODULE.glob('*.tf'))
    require(not re.search(r'(?m)^\s*(provider|data)\s+"|\bbackend\s+"',all_child),'child_no_provider_backend_discovery')
    require('aws_lb_target_group_attachment' not in all_child and 'terraform_remote_state' not in all_child,'no_dynamic_or_state_owner')

def capture(events,scope,exit_code=0):
    require(exit_code==0,'process_exit');pos,neg=definitions(scope);expected=set(pos)|set(neg);file='tests/ingress.tftest.hcl' if scope=='child' else 'tests/platform.tftest.hcl'
    plans={};runs=set();errors=set();versions=[];abstract=[];summaries=[];files=[];diagnostics=set()
    for e in events:
        require(not summaries,'after_summary');kind=e.get('type');require(kind in {'version','test_abstract','test_plan','test_run','diagnostic','test_summary','test_file'},'event_kind');name=e.get('@testrun')
        if kind=='version':versions.append(e.get('terraform'))
        if kind=='test_abstract':abstract.append(e['test_abstract'])
        if kind in {'test_plan','test_run','diagnostic'}:require(e.get('@testfile')==file and name in expected,'case_identity')
        if kind=='test_run' and 'status' in e['test_run']:
            require(name not in runs and e['test_run']['status']=='pass','run_completion');runs.add(name)
        if kind=='test_plan':require(name not in plans,'duplicate_plan');plans[name]=e['test_plan']
        if kind=='diagnostic':
            d=e['diagnostic'];signature=json.dumps([name,d],sort_keys=True);require(signature not in diagnostics,'duplicate_diagnostic');diagnostics.add(signature);require(name in neg and d['severity']=='error' and d['summary']=='Invalid value for variable' and any(x.get('traversal','').startswith(neg[name]) for x in d['snippet']['values']),'specific_input_rejection');errors.add(name)
        if kind=='test_file' and 'status' in e['test_file']:files.append(e['test_file'])
        if kind=='test_summary':summaries.append(e['test_summary'])
    require(versions==['1.17.0'] and len(abstract)==1 and set(abstract[0])=={file} and len(abstract[0][file])==len(expected) and set(abstract[0][file])==expected,'declared_coverage')
    require(set(plans)==runs==expected and errors==set(neg) and len(files)==1 and files[0]['status']=='pass','complete_evidence')
    require(summaries==[dict(status='pass',passed=len(expected),failed=0,errored=0,skipped=0)],'exact_summary')
    counts={k:(verify_plan(plans[k],v,scope) if scope=='child' else verify_root_ingress(plans[k],v)) for k,v in pos.items()}
    partial=parse((HERE/'partial_plans.json').read_text())[scope]
    for name in neg:
        p=plans[name];addresses=[r['address'] for r in p.get('resource_changes',[])];require(len(addresses)==len(set(addresses)) and set(addresses)==set(partial[name]['resources']) and set(p.get('output_changes',{}))==set(partial[name]['outputs']),'negative_partial_shape')
        require(all(r.get('mode')=='managed' and r.get('provider_name')==PROVIDER and r.get('change',{}).get('actions')==['create'] for r in p.get('resource_changes',[])),'negative_partial_identity')
    return dict(status='passed',aws_api_calls=0,native_tests=len(expected),positive_plans=len(pos),negative_cases=len(neg),resource_counts=counts),plans

def reject(call,label):
    try:call()
    except (ValueError,KeyError,TypeError,IndexError):return label
    raise ValueError('unsafe_variant_not_detected:'+label)
def self_test(events,scope,plans):
    pos,_=definitions(scope);p=plans['private_dev'];v=pos['private_dev'];prefix='module.private_ingress.' if scope=='root' else ''
    def verify(p):return verify_root_ingress(p,v) if scope=='root' else verify_plan(p,v,'child')
    def edit(addr,path,x):
        q=copy.deepcopy(p);d=next(r for r in q['resource_changes'] if r['address']==prefix+addr)['change']['after']
        for k in path[:-1]:d=d[k]
        d[path[-1]]=x;return q
    variants=[('aws_lb.this',['internal'],False),('aws_lb.this',['load_balancer_type'],'application'),('aws_lb.this',['security_groups'],[]),('aws_lb.this',['subnets'],['subnet-00000000000000003']),('aws_lb.this',['enforce_security_group_inbound_rules_on_private_link_traffic'],'off'),('aws_lb.this',['enable_cross_zone_load_balancing'],True),('aws_lb_listener.https_passthrough',['protocol'],'TLS'),('aws_lb_listener.https_passthrough',['port'],80),('aws_lb_listener.https_passthrough',['certificate_arn'],'unapproved'),('aws_lb_listener.https_passthrough',['default_action',0,'target_group_arn'],'fabricated'),('aws_lb_target_group.gateway',['target_type'],'instance'),('aws_lb_target_group.gateway',['port'],443),('aws_lb_target_group.gateway',['preserve_client_ip'],'true'),('aws_lb_target_group.gateway',['proxy_protocol_v2'],True),('aws_lb_target_group.gateway',['health_check',0,'port'],'443'),('aws_lb_target_group.gateway',['health_check',0,'protocol'],'HTTPS')]
    for a in ['aws_vpc_security_group_egress_rule.client_nlb','aws_vpc_security_group_ingress_rule.nlb_clients','aws_vpc_security_group_egress_rule.nlb_targets','aws_vpc_security_group_ingress_rule.nodes_targets','aws_vpc_security_group_egress_rule.cluster_webhook','aws_vpc_security_group_ingress_rule.nodes_webhook']:
        variants.extend([(a,['cidr_ipv4'],'0.0.0.0/0'),(a,['ip_protocol'],'-1'),(a,['referenced_security_group_id'],'sg-11111111111111111'),(a,['from_port'],0)])
    detections=[reject(lambda a=a,path=path,x=x:verify(edit(a,path,x)),a+str(path)) for a,path,x in variants]
    for label,fn in [('missing_node_ingress',lambda q:q['resource_changes'].__setitem__(slice(None),[r for r in q['resource_changes'] if r['address']!=prefix+'aws_vpc_security_group_ingress_rule.nodes_targets'])),('duplicate_resource',lambda q:q['resource_changes'].append(copy.deepcopy(q['resource_changes'][-1]))),('dynamic_registration',lambda q:q['resource_changes'].append(dict(address=prefix+'aws_lb_target_group_attachment.forbidden',type='aws_lb_target_group_attachment',name='forbidden',module_address=prefix.rstrip('.'),mode='managed',provider_name=PROVIDER,change={'actions':['create'],'before':None,'after':{},'after_unknown':{}}))),('unknown_nlb_arn',lambda q:next(r for r in q['resource_changes'] if r['address']==prefix+'aws_lb.this')['change']['after_unknown'].update(arn=True)),('output_corruption',lambda q:q['output_changes']['private_ingress']['after'].update(target_group_arn='fabricated'))]:
        q=copy.deepcopy(p);fn(q);detections.append(reject(lambda q=q:verify(q),label))
    faults=[]
    for kind in ['version','test_abstract','test_plan','test_run','diagnostic','test_summary','test_file']:
        index=next(i for i,e in enumerate(events) if e['type']==kind and (kind not in {'test_run','test_file'} or 'status' in e[kind]))
        for operation in ['missing','duplicate']:
            q=copy.deepcopy(events)
            if operation=='missing':q.pop(index)
            else:q.insert(index,copy.deepcopy(q[index]))
            faults.append(reject(lambda q=q:capture(q,scope),operation+':'+kind))
    for status in ['fail','error','skip']:
        q=copy.deepcopy(events);next(e for e in q if e['type']=='test_run' and 'status' in e['test_run'])['test_run']['status']=status
        faults.append(reject(lambda q=q:capture(q,scope),'terminal:'+status))
    faults.append(reject(lambda:capture(events,scope,1),'exit'))
    for text in ['{broken','{"x":1,"x":2}','{"x":NaN}']:
        faults.append(reject(lambda text=text:parse(text),'json:'+text))
    source_detections=[]
    paths=list(MODULE.glob('*.tf'))+[ROOT/'ingress.tf',ROOT/'ingress_variables.tf']
    sources={str(p.relative_to(REPO)):p.read_text() for p in paths}
    child='infra/modules/private_ingress/';root='infra/services/dev/ca-central-1/platform/'
    changes=[(root+'ingress.tf',r'module\.eks_platform\.security_group_ids\.cluster','module.eks_platform.security_group_ids.eks_managed'),
      (root+'ingress.tf',r'module\.eks_platform\.security_group_ids\.nodes','"sg-11111111111111111"'),
      (root+'ingress.tf',r'(cross_zone_enabled\s*=\s*)false',r'\g<1>true'),
      (root+'ingress.tf',r'var.gateway_target_port','443'),
      (root+'ingress.tf',r'toset\(\[var.ingress_subnet_key\]\)','toset([])'),
      (child+'main.tf',r', aws_vpc_security_group_ingress_rule.nodes_targets',''),
      (child+'variables.tf',r'condition\s*=\s*var.backend_target_port >= 1[^\n]*','condition = true'),
      (root+'ingress_variables.tf',r'condition\s*=\s*try\(contains[^\n]*','condition = true')]
    for path,pattern,replacement in changes:
        q=sources.copy();q[path],count=re.subn(pattern,replacement,q[path],count=1);require(count==1,'source_mutation_witness:'+path+pattern)
        source_detections.append(reject(lambda q=q:source_contract(q),path+pattern))
    return dict(semantic_mutations=len(detections),semantic_detections=detections,capture_failure_injections=len(faults),capture_detections=faults,source_dependency_mutations=len(source_detections),source_dependency_detections=source_detections)
def main():
    a=argparse.ArgumentParser();a.add_argument('--scope',choices=['child','root'],required=True);a.add_argument('--events',type=Path,required=True);a.add_argument('--exit-code',type=int,default=0);a.add_argument('--self-test',action='store_true');args=a.parse_args()
    try:
        source_contract();events=list(read_events(args.events.open()));report,plans=capture(events,args.scope,args.exit_code)
        if args.self_test:report.update(self_test(events,args.scope,plans))
        print(json.dumps(report,indent=2))
    except (ValueError,KeyError,TypeError,IndexError,OSError) as e:print('Ingress verification failed: '+str(e),file=sys.stderr);return 1
    return 0
if __name__=='__main__':sys.exit(main())
