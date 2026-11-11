#!/usr/bin/env python3
"""Independent complete EKS mock-plan, IAM, SG, access and ownership verification.

No AWS calls. Public computed fixtures do not establish live identity, service
compatibility, capacity, network reachability or effective authorization.
"""
import argparse
import copy
import ipaddress
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
MODULE = HERE.parent
REPO = HERE.parents[3]
ROOT = REPO / 'infra/services/dev/ca-central-1/platform'
PROVIDER = 'registry.terraform.io/hashicorp/aws'


def require(condition, code):
    if not condition:
        raise ValueError(code)


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, 'duplicate_json_key')
        result[key] = value
    return result


def invalid_constant(value):
    raise ValueError('nonfinite_json:' + value)


def parse(text):
    return json.loads(text, object_pairs_hook=unique_object, parse_constant=invalid_constant)


def unknown(value):
    if isinstance(value, dict):
        return any(unknown(v) for v in value.values())
    if isinstance(value, list):
        return any(unknown(v) for v in value)
    require(type(value) is bool, 'unknown_marker_type')
    return value


def one(value):
    require(isinstance(value, list) and len(value) == 1 and isinstance(value[0], dict), 'single_block')
    return value[0]


def indexed(base, key):
    return base + '[' + json.dumps(key) + ']'


def validate_inputs(v, scope):
    expected = v['expected_scope']; network = v['network_reference']
    require(expected['partition'] == 'aws' and expected['region'] == 'ca-central-1'
        and expected['environment'] in {'dev','stg','prod'} and re.fullmatch(r'[0-9]{12}', expected['account_id']), 'expected_scope')
    require(type(network['interface_version']) is int and network['interface_version'] == 1
        and network['scope'] == expected and network['routing_mode'] == 'per_az', 'network_scope_version')
    for kind, identity in [('vpc', network['vpc_id']), ('rtb', network['public_route_table_id'])]:
        require(re.fullmatch(kind + r'-([0-9a-f]{8}|[0-9a-f]{17})', identity), 'network_id')
    private, public = network['private_subnet_ids'], network['public_subnet_ids']
    azs, tables = network['subnet_azs']['private'], network['private_route_table_ids_by_subnet']
    require(len(private) >= 2 and set(private) == set(azs) == set(tables), 'network_complete_maps')
    subnet_ids = list(private.values()) + list(public.values())
    require(len(set(subnet_ids)) == len(subnet_ids) and all(re.fullmatch(r'subnet-([0-9a-f]{8}|[0-9a-f]{17})', s) for s in subnet_ids), 'private_public_unique_ids')
    require(all(re.fullmatch(expected['region'] + '[a-z]', az) for az in azs.values()), 'private_az_region')
    require(all(re.fullmatch(r'rtb-([0-9a-f]{8}|[0-9a-f]{17})', t) and t != network['public_route_table_id'] for t in tables.values()), 'private_table_scope')
    require(all((azs[k] == azs[j]) == (tables[k] == tables[j]) for k in private for j in private), 'az_table_identity')
    cluster_keys, node = set(v['cluster_subnet_keys']), v['node_group']
    require(cluster_keys <= set(private) and len({azs[k] for k in cluster_keys}) >= 2, 'multi_az_private_cluster')
    require(node['subnet_keys'] and set(node['subnet_keys']) <= cluster_keys, 'private_cluster_node_membership')
    if scope == 'root':
        require(expected == dict(environment='dev',partition='aws',region='ca-central-1',account_id=v['aws_account_id'])
            and public and all(azs[k] == v['active_workload_az'] for k in node['subnet_keys'])
            and set(network['nat_gateway_ids_by_az']) == {v['active_workload_az']}, 'dev_single_az_nat')
    require(node['ami_type'] in {'AL2023_x86_64_STANDARD','AL2023_ARM_64_STANDARD'}
        and re.fullmatch(r'[a-z][a-z0-9-]*\.[a-z0-9]+', node['instance_type'])
        and node['release_version'].startswith(v['kubernetes_version'] + '.'), 'explicit_node_strategy')
    require(all(type(node[k]) is int for k in ['min_size','desired_size','max_size','disk_size_gib'])
        and 1 <= node['min_size'] <= node['desired_size'] <= node['max_size'] and node['disk_size_gib'] >= 20, 'node_capacity')
    vpc, service = ipaddress.ip_network(network['vpc_cidr']), ipaddress.ip_network(v['service_ipv4_cidr'])
    require(vpc.version == service.version == 4 and 12 <= service.prefixlen <= 24 and not vpc.overlaps(service), 'service_cidr')
    require(any(service.subnet_of(ipaddress.ip_network(c)) for c in ['10.0.0.0/8','172.16.0.0/12','192.168.0.0/16']), 'private_service_cidr')
    require(re.fullmatch(r'1\.[0-9]{2}', v['kubernetes_version']) and int(v['kubernetes_version'].split('.')[1]) >= 30, 'explicit_cluster_version')
    require(set(v['addon_versions']) == {'vpc_cni','coredns','kube_proxy'} and all(re.fullmatch(r'v[0-9]+\.[0-9]+\.[0-9]+-eksbuild\.[0-9]+', value) for value in v['addon_versions'].values()), 'pinned_addon_versions')
    if v.get('cluster_kms_key_arn'):
        require(re.fullmatch(r'arn:aws:kms:' + expected['region'] + ':' + expected['account_id'] + r':key/[0-9a-f-]{36}', v['cluster_kms_key_arn']), 'approved_kms_scope')
    role_pattern = r'arn:aws:iam::' + expected['account_id'] + r':role/([A-Za-z0-9_+=,.@-]+/)*[A-Za-z0-9_+=,.@-]{1,64}'
    machine = {f"arn:aws:iam::{expected['account_id']}:role/{v['cluster_name']}-{suffix}" for suffix in ['cluster','nodes','cni']}
    principals = [v['bootstrap_admin_role_arn']]
    for access in v.get('namespace_access', {}).values():
        principals.append(access['principal_arn'])
        require(access['policy'] in {'view','edit'} and access['namespaces'] and all(re.fullmatch(r'[a-z0-9]([a-z0-9-]*[a-z0-9])?', n)
            and len(n) <= 63 and not n.startswith('kube-') and n != 'default' for n in access['namespaces']), 'namespace_access_scope')
    require(len(principals) == len(set(principals)) and all(re.fullmatch(role_pattern, p)
        and ':role/aws-service-role/' not in p and p not in machine for p in principals), 'approved_access_roles')
    for c in v['api_client_cidrs']:
        cidr = ipaddress.ip_network(c)
        require(any(cidr.subnet_of(ipaddress.ip_network(p)) for p in ['10.0.0.0/8','172.16.0.0/12','192.168.0.0/16']), 'private_api_clients')
    require(v['api_client_cidrs'] and v['node_https_egress_cidrs'] and all(8 <= ipaddress.ip_network(c).prefixlen <= 32 and ipaddress.ip_network(c).version == 4 for c in v['node_https_egress_cidrs']), 'bounded_https_egress')


def expected_rules(v, control, nodes):
    result = {}
    def rule(address, owner, protocol, port, *, source_group=None, cidr=None):
        result[address] = dict(security_group_id=owner,ip_protocol=protocol,from_port=port,to_port=port,
            referenced_security_group_id=source_group,cidr_ipv4=cidr)
    rule('aws_vpc_security_group_ingress_rule.cluster_nodes',control,'tcp',443,source_group=nodes)
    for cidr in v['api_client_cidrs']:
        rule(indexed('aws_vpc_security_group_ingress_rule.cluster_clients',cidr),control,'tcp',443,cidr=cidr)
    for key,protocol,port in [('https','tcp',443),('kubelet','tcp',10250),('dns_tcp','tcp',53),('dns_udp','udp',53)]:
        rule(indexed('aws_vpc_security_group_egress_rule.cluster_nodes',key),control,protocol,port,source_group=nodes)
    for key,protocol,port in [('https','tcp',443),('kubelet','tcp',10250),('dns_tcp','tcp',53),('dns_udp','udp',53)]:
        rule(indexed('aws_vpc_security_group_ingress_rule.nodes_cluster',key),nodes,protocol,port,source_group=control)
    resolver = str(ipaddress.ip_network(v['network_reference']['vpc_cidr']).network_address + 2) + '/32'
    for protocol in ['tcp','udp']:
        rule(indexed('aws_vpc_security_group_ingress_rule.nodes_dns',protocol),nodes,protocol,53,source_group=nodes)
        rule(indexed('aws_vpc_security_group_egress_rule.nodes_peer_dns',protocol),nodes,protocol,53,source_group=nodes)
        rule(indexed('aws_vpc_security_group_egress_rule.nodes_dns',protocol),nodes,protocol,53,cidr=resolver)
    rule('aws_vpc_security_group_egress_rule.nodes_cluster',nodes,'tcp',443,source_group=control)
    for cidr in v['node_https_egress_cidrs']:
        rule(indexed('aws_vpc_security_group_egress_rule.nodes_https',cidr),nodes,'tcp',443,cidr=cidr)
    return result


def resources_of(plan, scope):
    require(isinstance(plan,dict) and plan.get('plan_format_version') == '1.2' and isinstance(plan.get('resource_changes'), list), 'complete_plan_shape')
    result = {};prefix = 'module.eks_platform.' if scope == 'root' else ''
    for row in plan['resource_changes']:
        full = row.get('address','');require(full.startswith(prefix), 'resource_root_boundary')
        addr=full[len(prefix):];match=re.fullmatch(r'(aws_[a-z0-9_]+)\.([a-z0-9_]+)(?:\[("[^"\\]+")\])?',addr)
        require(match and row.get('type') == match[1] and row.get('name') == match[2] and addr not in result, 'resource_identity')
        require(row.get('module_address','') == prefix.rstrip('.') and row.get('index') == (json.loads(match[3]) if match[3] else None), 'resource_module_index')
        require(row.get('mode') == 'managed' and row.get('provider_name') == PROVIDER, 'managed_aws_owner')
        change=row.get('change',{})
        require(change.get('actions') == ['create'] and 'before' in change and change['before'] is None
            and isinstance(change.get('after'),dict) and isinstance(change.get('after_unknown'),dict), 'resource_create_metadata')
        unknown(change['after_unknown']);result[addr]=change
    return result


def verify_plan(plan, v, scope):
    ingress_count=0
    if scope=='root':
        # Independent ingress verification runs before projecting the unchanged EKS
        # ownership/output contract. No additional resource is silently ignored.
        import importlib.util
        spec=importlib.util.spec_from_file_location('private_ingress_check',REPO/'infra/modules/private_ingress/tests/check_ingress.py')
        sys.dont_write_bytecode=True
        checker=importlib.util.module_from_spec(spec);spec.loader.exec_module(checker)
        ingress_count=checker.verify_root_ingress(plan,v)
        plan=dict(plan,resource_changes=[r for r in plan['resource_changes'] if not r['address'].startswith('module.private_ingress.')],
            output_changes={k:x for k,x in plan['output_changes'].items() if k not in {'private_ingress','controller_identity'}})
    validate_inputs(v,scope);resources=resources_of(plan,scope)
    def read(addr,key):
        change=resources[addr]
        require(key in change['after'] and not unknown(change['after_unknown'].get(key,False)), 'unknown_or_missing:'+addr+':'+key)
        return change['after'][key]
    def same(addr,key,value):require(read(addr,key)==value,'contract:'+addr+':'+key)
    cluster='aws_eks_cluster.this';sg_control=read('aws_security_group.cluster','id');sg_nodes=read('aws_security_group.nodes','id')
    sg_managed=one(read(cluster,'vpc_config'))['cluster_security_group_id']
    require(len({sg_control,sg_nodes,sg_managed}) == 3,'distinct_security_groups')
    rules=expected_rules(v,sg_control,sg_nodes)
    expected={'aws_eks_cluster.this','aws_cloudwatch_log_group.cluster','aws_iam_role.cluster','aws_iam_role.nodes','aws_iam_role.cni',
        'aws_iam_role_policy.cluster','aws_iam_role_policy_attachment.cni','aws_iam_openid_connect_provider.cluster',
        'aws_security_group.cluster','aws_security_group.nodes','aws_launch_template.nodes','aws_eks_node_group.this',
        'aws_eks_access_entry.bootstrap','aws_eks_access_policy_association.bootstrap',
        'aws_eks_addon.vpc_cni','aws_eks_addon.kube_proxy','aws_eks_addon.coredns'}
    expected |= {indexed('aws_iam_role_policy_attachment.nodes',p) for p in ['AmazonEKSWorkerNodePolicy','AmazonEC2ContainerRegistryPullOnly']}
    expected |= set(rules)
    for k in v.get('namespace_access',{}):expected |= {indexed('aws_eks_access_entry.namespace',k),indexed('aws_eks_access_policy_association.namespace',k)}
    require(set(resources)==expected,'exact_resource_inventory')
    name=v['cluster_name'];net=v['network_reference'];account=v['expected_scope']['account_id'];region=v['expected_scope']['region']
    same(cluster,'name',name);same(cluster,'version',v['kubernetes_version']);same(cluster,'arn',f'arn:aws:eks:{region}:{account}:cluster/{name}')
    same(cluster,'bootstrap_self_managed_addons',False);same(cluster,'force_update_version',False);same(cluster,'deletion_protection',v.get('deletion_protection',True))
    require(set(read(cluster,'enabled_cluster_log_types'))=={'api','audit','authenticator','controllerManager','scheduler'},'all_control_logs')
    require(one(read(cluster,'access_config'))==dict(authentication_mode='API',bootstrap_cluster_creator_admin_permissions=False),'api_access_no_creator')
    for block,sub in [('compute_config',None),('storage_config','block_storage')]:
        config=one(read(cluster,block));config=one(config[sub]) if sub else config
        require(config.get('enabled') is False,'no_auto_mode')
    kube=one(read(cluster,'kubernetes_network_config'))
    require(kube['ip_family']=='ipv4' and kube['service_ipv4_cidr']==v['service_ipv4_cidr']
        and one(kube['elastic_load_balancing'])['enabled'] is False,'ipv4_no_auto_ingress')
    require(one(read(cluster,'upgrade_policy'))=={'support_type':'STANDARD'},'no_unreviewed_extended_support')
    config=one(read(cluster,'vpc_config'))
    require(config['endpoint_private_access'] is True and config['endpoint_public_access'] is False
        and config['control_plane_egress_mode']=='AWS_MANAGED' and set(config['security_group_ids'])=={sg_control}
        and set(config['subnet_ids'])=={net['private_subnet_ids'][k] for k in v['cluster_subnet_keys']} and config['vpc_id']==net['vpc_id'],'private_cluster_vpc_contract')
    encryption=read(cluster,'encryption_config')
    key=v.get('cluster_kms_key_arn')
    require((not encryption and key is None) or (key and len(encryption)==1 and encryption[0]['resources']==['secrets'] and one(encryption[0]['provider'])['key_arn']==key),'encryption_reference')
    for group in ['cluster','nodes']:
        addr='aws_security_group.'+group;same(addr,'vpc_id',net['vpc_id']);same(addr,'ingress',[]);same(addr,'egress',[])
    for addr,fields in rules.items():
        for field,value in fields.items():same(addr,field,value)
        require(not read(addr,'cidr_ipv6') and not read(addr,'prefix_list_id'),'no_alternate_sg_destination')
    role_arns={}
    for role,principal in [('cluster','eks.amazonaws.com'),('nodes','ec2.amazonaws.com')]:
        addr='aws_iam_role.'+role;same(addr,'name',name+'-'+role);same(addr,'arn',f'arn:aws:iam::{account}:role/{name}-{role}');role_arns[role]=read(addr,'arn')
        require(parse(read(addr,'assume_role_policy'))=={'Version':'2012-10-17','Statement':[{'Effect':'Allow','Action':'sts:AssumeRole','Principal':{'Service':principal}}]},'service_role_trust')
        require(not read(addr,'inline_policy') and not read(addr,'managed_policy_arns'),'no_competing_iam_owner')
    same(cluster,'role_arn',role_arns['cluster'])
    oidc='aws_iam_openid_connect_provider.cluster';issuer=one(one(read(cluster,'identity'))['oidc'])['issuer']
    require(re.fullmatch(r'https://oidc\.eks\.'+region+r'\.amazonaws\.com/id/[A-Za-z0-9]+',issuer),'regional_eks_oidc_issuer')
    same(oidc,'url',issuer);same(oidc,'client_id_list',['sts.amazonaws.com'])
    same(oidc,'arn',f'arn:aws:iam::{account}:oidc-provider/{issuer.removeprefix("https://")}')
    cni='aws_iam_role.cni';same(cni,'name',name+'-cni');same(cni,'arn',f'arn:aws:iam::{account}:role/{name}-cni');role_arns['cni']=read(cni,'arn')
    require(parse(read(cni,'assume_role_policy'))=={'Version':'2012-10-17','Statement':[{'Effect':'Allow','Action':'sts:AssumeRoleWithWebIdentity','Principal':{'Federated':read(oidc,'arn')},'Condition':{'StringEquals':{issuer.removeprefix('https://')+':aud':'sts.amazonaws.com',issuer.removeprefix('https://')+':sub':'system:serviceaccount:kube-system:aws-node'}}}]},'cni_scoped_irsa_trust')
    require(not read(cni,'inline_policy') and not read(cni,'managed_policy_arns'),'no_competing_cni_iam_owner')
    statements=[{'Sid':'RegionalEC2Discovery','Effect':'Allow','Action':['ec2:DescribeInstances','ec2:DescribeNetworkInterfaces','ec2:DescribeVpcs','ec2:DescribeDhcpOptions','ec2:DescribeAvailabilityZones','ec2:DescribeInstanceTopology'],'Resource':'*','Condition':{'StringEquals':{'aws:RequestedRegion':region}}},
        {'Sid':'OwnClusterInstanceTag','Effect':'Allow','Action':['ec2:CreateTags'],'Resource':f'arn:aws:ec2:{region}:{account}:instance/*','Condition':{'ForAllValues:StringEquals':{'aws:TagKeys':[f'kubernetes.io/cluster/{name}']},'Null':{'aws:TagKeys':'false'}}}]
    if key:statements.append({'Sid':'ExplicitClusterKeyMetadata','Effect':'Allow','Action':['kms:DescribeKey'],'Resource':key})
    same('aws_iam_role_policy.cluster','role',read('aws_iam_role.cluster','name'))
    require(parse(read('aws_iam_role_policy.cluster','policy'))=={'Version':'2012-10-17','Statement':statements},'minimum_control_plane_permissions')
    for policy in ['AmazonEKSWorkerNodePolicy','AmazonEC2ContainerRegistryPullOnly']:
        addr=indexed('aws_iam_role_policy_attachment.nodes',policy);same(addr,'role',read('aws_iam_role.nodes','name'));same(addr,'policy_arn','arn:aws:iam::aws:policy/'+policy)
    same('aws_iam_role_policy_attachment.cni','role',read(cni,'name'));same('aws_iam_role_policy_attachment.cni','policy_arn','arn:aws:iam::aws:policy/AmazonEKS_CNI_Policy')
    lt='aws_launch_template.nodes';ng='aws_eks_node_group.this';node=v['node_group']
    interfaces=one(read(lt,'network_interfaces'))
    require(interfaces['associate_public_ip_address']=='false' and interfaces['delete_on_termination']=='true' and interfaces['device_index']==0
        and interfaces['security_groups']==[sg_nodes] and not interfaces['subnet_id'] and not interfaces['network_interface_id'],'private_node_interface')
    metadata=one(read(lt,'metadata_options'))
    require(metadata=={'http_endpoint':'enabled','http_protocol_ipv6':'disabled','http_tokens':'required','http_put_response_hop_limit':1,'instance_metadata_tags':'disabled'},'imds_hardening')
    disk=one(read(lt,'block_device_mappings'));ebs=one(disk['ebs'])
    require(disk['device_name']=='/dev/xvda' and ebs['encrypted']=='true' and ebs['delete_on_termination']=='true'
        and ebs['volume_type']=='gp3' and ebs['volume_size']==node['disk_size_gib'] and not ebs['snapshot_id'],'encrypted_ephemeral_nodes')
    for field in ['image_id','instance_type','iam_instance_profile','key_name','user_data','vpc_security_group_ids','security_group_names','instance_market_options','secondary_interfaces']:
        require(not read(lt,field),'no_unreviewed_launch_template_override:'+field)
    for field,value in {'cluster_name':read(cluster,'name'),'node_group_name':node['name'],'node_role_arn':role_arns['nodes'],'ami_type':node['ami_type'],'release_version':node['release_version'],'version':v['kubernetes_version'],'instance_types':[node['instance_type']],'capacity_type':'ON_DEMAND','force_update_version':False}.items():same(ng,field,value)
    require(set(read(ng,'subnet_ids'))=={net['private_subnet_ids'][k] for k in node['subnet_keys']},'node_private_subnets')
    launch=one(read(ng,'launch_template'));require(launch['id']==read(lt,'id') and launch['version']==str(read(lt,'latest_version')),'actual_numeric_launch_template')
    require(one(read(ng,'scaling_config'))=={k:node[k] for k in ['min_size','desired_size','max_size']},'explicit_node_scaling')
    require(not read(ng,'remote_access') and not read(ng,'warm_pool_config') and one(read(ng,'node_repair_config'))['enabled'] is False,'no_remote_or_unreviewed_node_mode')
    require(one(read(ng,'update_config'))['max_unavailable']==1,'bounded_node_updates')
    for addon,service in [('vpc_cni','vpc-cni'),('kube_proxy','kube-proxy'),('coredns','coredns')]:
        addr='aws_eks_addon.'+addon
        for field,value in {'cluster_name':read(cluster,'name'),'addon_name':service,'addon_version':v['addon_versions'][addon],'service_account_role_arn':role_arns['cni'] if addon=='vpc_cni' else None,'preserve':False,'resolve_conflicts_on_create':'NONE','resolve_conflicts_on_update':'NONE','configuration_values':'{}'}.items():same(addr,field,value)
        require(not read(addr,'pod_identity_association') and not read(addr,'namespace_config'),'single_addon_identity_owner')
    log='aws_cloudwatch_log_group.cluster'
    for field,value in {'name':f'/aws/eks/{name}/cluster','retention_in_days':30,'log_group_class':'STANDARD','deletion_protection_enabled':v.get('deletion_protection',True),'skip_destroy':False,'kms_key_id':None}.items():same(log,field,value)
    admin='aws_eks_access_entry.bootstrap';assoc='aws_eks_access_policy_association.bootstrap'
    entries={'bootstrap':read(admin,'access_entry_arn'),'namespaced':{}}
    for addr,principal in [(admin,v['bootstrap_admin_role_arn'])]+[(indexed('aws_eks_access_entry.namespace',k),value['principal_arn']) for k,value in v.get('namespace_access',{}).items()]:
        same(addr,'cluster_name',read(cluster,'name'));same(addr,'principal_arn',principal);same(addr,'type','STANDARD');require(not read(addr,'kubernetes_groups'),'no_unreviewed_kubernetes_groups')
    for addr,principal,policy,namespaces in [(assoc,read(admin,'principal_arn'),'AmazonEKSClusterAdminPolicy',None)]+[(indexed('aws_eks_access_policy_association.namespace',k),read(indexed('aws_eks_access_entry.namespace',k),'principal_arn'),'AmazonEKSViewPolicy' if value['policy']=='view' else 'AmazonEKSEditPolicy',value['namespaces']) for k,value in v.get('namespace_access',{}).items()]:
        same(addr,'cluster_name',read(cluster,'name'));same(addr,'principal_arn',principal);same(addr,'policy_arn','arn:aws:eks::aws:cluster-access-policy/'+policy)
        access=one(read(addr,'access_scope'));require(access['type']==('cluster' if namespaces is None else 'namespace') and set(access.get('namespaces') or [])==set(namespaces or []),'explicit_access_scope')
    for k in v.get('namespace_access',{}):entries['namespaced'][k]=read(indexed('aws_eks_access_entry.namespace',k),'access_entry_arn')
    tags=dict(v.get('tags',{}));tags.pop('Name',None)
    if scope=='root':tags.update(Environment='dev',Service='platform',Project='aws-terraform-portfolio',ManagedBy='Terraform')
    for addr,change in resources.items():
        if 'tags' in change['after']:
            actual=read(addr,'tags');require(isinstance(actual,dict) and actual.get('Name')!='caller-must-not-win' and all(actual.get(k)==val for k,val in tags.items()),'required_tags')
    outputs={'cluster_name':read(cluster,'name'),'cluster_arn':read(cluster,'arn'),'endpoint':read(cluster,'endpoint'),'certificate_authority_data':one(read(cluster,'certificate_authority'))['data'],'oidc_issuer':issuer,'oidc_provider_arn':read(oidc,'arn'),'node_group_arn':read(ng,'arn'),'security_group_ids':dict(cluster=sg_control,nodes=sg_nodes,eks_managed=sg_managed),'role_arns':role_arns,'access_entry_arns':entries,'addon_arns':{key:read('aws_eks_addon.'+key,'arn') for key in ['vpc_cni','kube_proxy','coredns']},'log_group_arn':read(log,'arn')}
    if scope=='root':outputs={'platform':dict(outputs,scope=v['expected_scope'])}
    changes=plan.get('output_changes');require(isinstance(changes,dict) and set(changes)==set(outputs),'output_inventory')
    for key,value in outputs.items():
        output=changes[key];require(output.get('actions')==['create'] and 'before' in output and output['before'] is None and output.get('after')==value
            and 'after_unknown' in output and not unknown(output['after_unknown']) and output.get('after_sensitive') is False,'actual_nonsecret_output:'+key)
    return len(resources)+ingress_count


def source_contract(sources=None):
    sources = sources or {str(p.relative_to(REPO)):p.read_text() for folder in [MODULE,ROOT] for p in folder.glob('*.tf')}
    def norm(path):return re.sub(r'\s+','',re.sub(r'(?m)#.*$','',sources[path]))
    child='infra/modules/eks_platform/';root='infra/services/dev/ca-central-1/platform/'
    cluster=norm(child+'cluster.tf');compute=norm(child+'compute.tf');addons=norm(child+'addons.tf');iam=norm(child+'iam.tf')
    for expr in ['endpoint_private_access=true','endpoint_public_access=false','authentication_mode="API"','bootstrap_cluster_creator_admin_permissions=false','bootstrap_self_managed_addons=false','role_arn=aws_iam_role.cluster.arn','security_group_ids=[aws_security_group.cluster.id]']:
        require(expr in cluster,'source_private_cluster:'+expr)
    require('depends_on=[aws_iam_role_policy.cluster,aws_cloudwatch_log_group.cluster,aws_vpc_security_group_ingress_rule.cluster_nodes,aws_vpc_security_group_ingress_rule.cluster_clients,aws_vpc_security_group_egress_rule.cluster_nodes]' in cluster,'cluster_iam_log_sg_dependency')
    for expr in ['node_role_arn=aws_iam_role.nodes.arn','id=aws_launch_template.nodes.id','version=tostring(aws_launch_template.nodes.latest_version)','associate_public_ip_address=false','security_groups=[aws_security_group.nodes.id]']:
        require(expr in compute,'source_node_binding:'+expr)
    for dep in ['aws_iam_role_policy_attachment.nodes','aws_eks_addon.vpc_cni','aws_eks_addon.kube_proxy','aws_eks_access_policy_association.bootstrap','aws_vpc_security_group_ingress_rule.nodes_cluster','aws_vpc_security_group_ingress_rule.nodes_dns','aws_vpc_security_group_egress_rule.nodes_cluster','aws_vpc_security_group_egress_rule.nodes_dns','aws_vpc_security_group_egress_rule.nodes_peer_dns','aws_vpc_security_group_egress_rule.nodes_https']:
        depends=re.search(r'depends_on=\[([^]]+)\]',compute);require(depends and dep in depends[1].split(','),'node_readiness_dependency:'+dep)
    require('depends_on=[aws_eks_node_group.this]' in addons and 'depends_on=[aws_iam_role_policy_attachment.cni]' in addons,'addon_ordering')
    require('url=aws_eks_cluster.this.identity[0].oidc[0].issuer' in iam and 'Federated=aws_iam_openid_connect_provider.cluster.arn' in iam,'actual_oidc_identity')
    require('service_account_role_arn=aws_iam_role.cni.arn' in addons and addons.count('configuration_values=jsonencode({})')==3,'addon_identity_config')
    for filename in MODULE.glob('*.tf'):
        source=sources[child+filename.name]
        require(not re.search(r'(?m)^\s*(provider|data)\s+"',source),'no_child_provider_or_discovery')
        require(not re.search(r'\bbackend\s+"',source),'no_child_backend')
    all_source='\n'.join(sources.values())
    for term in ['terraform_remote_state','kubernetes_manifest','helm_release','skip_credentials_validation','skip_requesting_account_id','AdministratorAccess','iam:PassRole','aws_eks_fargate_profile']:
        require(term not in all_source,'forbidden_ownership_or_privilege:'+term)
    require('region=local.regionallowed_account_ids=[var.aws_account_id]' in norm(root+'providers.tf'),'root_account_guard')
    require('region="ca-central-1"' in norm(root+'main.tf') and 'environment="dev"' in norm(root+'main.tf'),'root_scope')
    require('source="../../../../modules/eks_platform"' in norm(root+'main.tf') and 'providers={aws=aws}' in norm(root+'main.tf'),'root_child_provider_binding')
    require('backend"local"{}' in norm(root+'backend.tf') and 'required_version="~>1.17.0"' in norm(root+'versions.tf') and 'version="~>6.72.0"' in norm(root+'versions.tf'),'root_backend_versions')
    require((ROOT/'.terraform.lock.hcl').read_bytes()==(REPO/'infra/services/dev/ca-central-1/network/.terraform.lock.hcl').read_bytes(),'root_lock_identity')
    # Default AWS add-on parameters are server-versioned, not arbitrary unreviewed
    # JSON. Inline SG rules must never compete with the standalone rule owners.
    security=norm(child+'security.tf');require('ingress{' not in security and 'egress{' not in security,'no_inline_sg_rule_owner')


def definitions(scope):
    data=parse((HERE/'cases.json').read_text())
    positives=copy.deepcopy(data[scope+'_positive']);negatives=data[scope+'_negative']
    if scope=='root':
        for v in positives.values():v['expected_scope']=dict(environment='dev',region='ca-central-1',partition='aws',account_id=v['aws_account_id'])
    return positives,negatives


def verify_capture(events,scope,exit_code=0):
    require(exit_code==0,'terraform_nonzero_exit')
    positives,negatives=definitions(scope);expected=set(positives)|set(negatives)
    partial=parse((HERE/'partial_plans.json').read_text())[scope]
    file='tests/platform.tftest.hcl';versions=[];abstracts=[];plans={};runs={};errors={};summary=[];terminals=[]
    for event in events:
        require(isinstance(event,dict) and not summary,'event_shape_or_after_summary')
        kind=event.get('type');require(kind in {'version','test_abstract','test_file','test_run','test_plan','diagnostic','test_summary'},'event_type')
        name=event.get('@testrun')
        if kind=='version':versions.append(event.get('terraform'))
        if kind=='test_abstract':abstracts.append(event.get('test_abstract'))
        if kind in {'test_run','test_plan','diagnostic'}:require(event.get('@testfile')==file and name in expected,'test_case_identity')
        if kind=='test_run' and 'status' in event.get('test_run',{}):
            require(name not in runs and event['test_run'].get('run')==name and event['test_run']['status']=='pass','terminal_skip_fail_duplicate')
            runs[name]=True
        if kind=='test_plan':require(name not in plans,'duplicate_plan');plans[name]=event.get('test_plan')
        if kind=='diagnostic':
            d=event.get('diagnostic',{});require(name in negatives and d.get('severity')=='error' and d.get('summary')=='Invalid value for variable','unexpected_diagnostic')
            require(any(value.get('traversal','').startswith(negatives[name]) for value in d.get('snippet',{}).get('values',[])),'specific_rejection_diagnostic')
            errors.setdefault(name,[]).append(d)
        if kind=='test_file' and 'status' in event.get('test_file',{}):terminals.append(event['test_file'])
        if kind=='test_summary':summary.append(event.get('test_summary'))
    require(versions==['1.17.0'],'version_coverage')
    require(len(abstracts)==1 and set(abstracts[0])=={file} and set(abstracts[0][file])==expected and len(abstracts[0][file])==len(expected),'declared_case_coverage')
    require(set(runs)==set(plans)==expected and set(errors)==set(negatives),'complete_run_plan_negative_coverage')
    require(len(terminals)==1 and terminals[0].get('path')==file and terminals[0].get('status')=='pass','file_completion')
    require(summary==[dict(status='pass',passed=len(expected),failed=0,errored=0,skipped=0)],'summary_coverage')
    inventory={name:verify_plan(plans[name],values,scope) for name,values in positives.items()}
    prefix='module.eks_platform.' if scope=='root' else ''
    for name in negatives:
        plan=plans[name];rows=plan.get('resource_changes',[]);outputs=plan.get('output_changes',{})
        require(isinstance(rows,list) and isinstance(outputs,dict),'partial_plan_shape')
        addresses=[row.get('address','') for row in rows]
        require(len(addresses)==len(set(addresses)) and set(addresses)==set(partial[name]['resources']) and set(outputs)==set(partial[name]['outputs']),'reviewed_negative_partial_shape:'+name)
        for row in rows:
            require(row.get('mode')=='managed' and row.get('provider_name')==PROVIDER and row.get('address','').startswith((prefix,'module.private_ingress.') if scope=='root' else prefix)
                and row.get('change',{}).get('actions')==['create'],'partial_resource_identity')
    return dict(status='passed',aws_api_calls=0,evidence_type='actual_mock_plan_verification',native_tests=len(expected),positive_plans=len(positives),negative_cases=len(negatives),resource_counts=inventory),plans


def read_events(stream):
    for line in stream:
        require(line.strip(),'empty_event')
        event=parse(line);require(isinstance(event,dict),'event_object')
        if event.get('type')=='test_plan':event.get('test_plan',{}).pop('provider_schemas',None)
        yield event


def rejected(call,name):
    try:call()
    except (ValueError,TypeError,KeyError,IndexError):return name
    raise ValueError('unsafe_variant_not_detected:'+name)


def self_test(events,scope,plans):
    positives,_=definitions(scope);name='private_dev';plan=plans[name];v=positives[name]
    prefix='module.eks_platform.' if scope=='root' else ''
    def edit(addr,path,value,base=plan):
        changed=copy.deepcopy(base);row=next(r for r in changed['resource_changes'] if r['address']==prefix+addr)
        d=row['change']['after']
        for key in path[:-1]:d=d[key]
        d[path[-1]]=value
        return changed
    mutations=[
        ('wrong_peer_dns_target',indexed('aws_vpc_security_group_egress_rule.nodes_peer_dns','udp'),['referenced_security_group_id'],'sg-11111111111111111'),
        ('wrong_peer_dns_port',indexed('aws_vpc_security_group_egress_rule.nodes_peer_dns','tcp'),['to_port'],54),
        ('wrong_control_dns_source',indexed('aws_vpc_security_group_ingress_rule.nodes_cluster','dns_udp'),['referenced_security_group_id'],'sg-11111111111111111'),
        ('wrong_control_dns_protocol',indexed('aws_vpc_security_group_ingress_rule.nodes_cluster','dns_tcp'),['ip_protocol'],'udp'),
        ('public_api','aws_eks_cluster.this',['vpc_config',0,'endpoint_public_access'],True),
        ('no_private_api','aws_eks_cluster.this',['vpc_config',0,'endpoint_private_access'],False),
        ('legacy_auth','aws_eks_cluster.this',['access_config',0,'authentication_mode'],'CONFIG_MAP'),
        ('mixed_auth','aws_eks_cluster.this',['access_config',0,'authentication_mode'],'API_AND_CONFIG_MAP'),
        ('creator_admin','aws_eks_cluster.this',['access_config',0,'bootstrap_cluster_creator_admin_permissions'],True),
        ('auto_mode','aws_eks_cluster.this',['compute_config',0,'enabled'],True),
        ('auto_storage','aws_eks_cluster.this',['storage_config',0,'block_storage',0,'enabled'],True),
        ('auto_ingress','aws_eks_cluster.this',['kubernetes_network_config',0,'elastic_load_balancing',0,'enabled'],True),
        ('duplicate_addons','aws_eks_cluster.this',['bootstrap_self_managed_addons'],True),
        ('unattached_cluster_sg','aws_eks_cluster.this',['vpc_config',0,'security_group_ids'],['sg-00000000000000003']),
        ('public_cluster_subnet','aws_eks_cluster.this',['vpc_config',0,'subnet_ids'],[v['network_reference']['public_subnet_ids']['public-a']]),
        ('foreign_vpc','aws_eks_cluster.this',['vpc_config',0,'vpc_id'],'vpc-11111111111111111'),
        ('foreign_cluster','aws_eks_cluster.this',['arn'],'arn:aws:eks:ca-central-1:111111111111:cluster/test-eks'),
        ('missing_audit_logs','aws_eks_cluster.this',['enabled_cluster_log_types'],['api']),
        ('extended_support','aws_eks_cluster.this',['upgrade_policy',0,'support_type'],'EXTENDED'),
        ('public_node','aws_launch_template.nodes',['network_interfaces',0,'associate_public_ip_address'],'true'),
        ('managed_sg_on_node','aws_launch_template.nodes',['network_interfaces',0,'security_groups'],['sg-00000000000000003']),
        ('imds_v1','aws_launch_template.nodes',['metadata_options',0,'http_tokens'],'optional'),
        ('pod_imds_access','aws_launch_template.nodes',['metadata_options',0,'http_put_response_hop_limit'],2),
        ('unencrypted_disk','aws_launch_template.nodes',['block_device_mappings',0,'ebs',0,'encrypted'],'false'),
        ('retained_disk','aws_launch_template.nodes',['block_device_mappings',0,'ebs',0,'delete_on_termination'],'false'),
        ('ssh_key','aws_launch_template.nodes',['key_name'],'unapproved-key'),
        ('public_node_subnet','aws_eks_node_group.this',['subnet_ids'],[v['network_reference']['public_subnet_ids']['public-a']]),
        ('wrong_node_role','aws_eks_node_group.this',['node_role_arn'],v['bootstrap_admin_role_arn']),
        ('spot_nodes','aws_eks_node_group.this',['capacity_type'],'SPOT'),
        ('force_drain','aws_eks_node_group.this',['force_update_version'],True),
        ('wrong_instance','aws_eks_node_group.this',['instance_types'],['unreviewed.large']),
        ('wrong_scaling','aws_eks_node_group.this',['scaling_config',0,'desired_size'],99),
        ('wrong_lt','aws_eks_node_group.this',['launch_template',0,'id'],'lt-11111111111111111'),
        ('floating_lt','aws_eks_node_group.this',['launch_template',0,'version'],'$Latest'),
        ('wrong_sg_owner','aws_vpc_security_group_ingress_rule.cluster_nodes',['security_group_id'],'sg-00000000000000002'),
        ('all_protocols','aws_vpc_security_group_ingress_rule.cluster_nodes',['ip_protocol'],'-1'),
        ('world_sg_source','aws_vpc_security_group_ingress_rule.cluster_nodes',['cidr_ipv4'],'0.0.0.0/0'),
        ('wrong_sg_reference','aws_vpc_security_group_ingress_rule.cluster_nodes',['referenced_security_group_id'],'sg-00000000000000003'),
        ('wrong_bootstrap','aws_eks_access_entry.bootstrap',['principal_arn'],'arn:aws:iam::111111111111:role/test-bootstrap'),
        ('system_masters','aws_eks_access_entry.bootstrap',['kubernetes_groups'],['system:masters']),
        ('wrong_access_policy','aws_eks_access_policy_association.bootstrap',['policy_arn'],'arn:aws:iam::aws:policy/AdministratorAccess'),
        ('wrong_access_principal','aws_eks_access_policy_association.bootstrap',['principal_arn'],'arn:aws:iam::000000000000:role/test-eks-nodes'),
        ('wrong_cni_role','aws_eks_addon.vpc_cni',['service_account_role_arn'],'arn:aws:iam::000000000000:role/test-eks-nodes'),
        ('unpinned_addon','aws_eks_addon.vpc_cni',['addon_version'],'latest'),
        ('addon_adoption','aws_eks_addon.vpc_cni',['resolve_conflicts_on_create'],'OVERWRITE'),
        ('addon_retention','aws_eks_addon.vpc_cni',['preserve'],True),
        ('extra_addon_identity','aws_eks_addon.vpc_cni',['pod_identity_association'],[{'role_arn':'arn:aws:iam::000000000000:role/unapproved','service_account':'aws-node'}]),
        ('wrong_oidc_url','aws_iam_openid_connect_provider.cluster',['url'],'https://unapproved.example.test'),
        ('wrong_oidc_client','aws_iam_openid_connect_provider.cluster',['client_id_list'],['unapproved']),
        ('weak_log_retention','aws_cloudwatch_log_group.cluster',['retention_in_days'],1),
        ('retained_logs','aws_cloudwatch_log_group.cluster',['skip_destroy'],True),
        ('node_admin_policy',indexed('aws_iam_role_policy_attachment.nodes','AmazonEKSWorkerNodePolicy'),['policy_arn'],'arn:aws:iam::aws:policy/AdministratorAccess'),
        ('cni_policy_on_node','aws_iam_role_policy_attachment.cni',['role'],'test-eks-nodes'),
    ]
    detected=[rejected(lambda addr=addr,path=path,value=value:verify_plan(edit(addr,path,value),v,scope),name) for name,addr,path,value in mutations]
    # Policy mutations alter actual generated JSON; no source substring is used
    # as proof of IAM/Trust permission semantics.
    for addr,field,fn,label in [
        ('aws_iam_role.nodes','assume_role_policy',lambda p:p['Statement'][0]['Principal'].update(Service='lambda.amazonaws.com'),'wrong_ec2_trust'),
        ('aws_iam_role.cluster','assume_role_policy',lambda p:p['Statement'][0].update(Principal={'AWS':'*'}),'broad_cluster_trust'),
        ('aws_iam_role.cni','assume_role_policy',lambda p:p['Statement'][0].update(Principal={'Federated':'*'}),'broad_federation'),
        ('aws_iam_role.cni','assume_role_policy',lambda p:p['Statement'][0]['Condition'].update(StringLike={'sub':'*'}),'weak_irsa_condition'),
        ('aws_iam_role.cni','assume_role_policy',lambda p:p['Statement'][0]['Condition']['StringEquals'].update({'oidc.eks.ca-central-1.amazonaws.com/id/TESTISSUER:aud':'other'}),'wrong_irsa_audience'),
        ('aws_iam_role_policy.cluster','policy',lambda p:p['Statement'][0]['Action'].append('iam:PassRole'),'unrestricted_passrole'),
        ('aws_iam_role_policy.cluster','policy',lambda p:p['Statement'][0]['Action'].append('elasticloadbalancing:CreateLoadBalancer'),'future_lb_write'),
        ('aws_iam_role_policy.cluster','policy',lambda p:p['Statement'][1].update(Resource='*'),'unrestricted_tag_resource'),
        ('aws_iam_role_policy.cluster','policy',lambda p:p['Statement'][1]['Condition'].pop('Null'),'missing_tag_presence'),
    ]:
        row=next(r for r in plan['resource_changes'] if r['address']==prefix+addr);policy=parse(row['change']['after'][field]);fn(policy)
        detected.append(rejected(lambda addr=addr,field=field,policy=policy:verify_plan(edit(addr,[field],json.dumps(policy)),v,scope),label))
    access_plan=plans['namespace_access'];access_input=positives['namespace_access']
    for field,value in [('policy_arn','arn:aws:eks::aws:cluster-access-policy/AmazonEKSClusterAdminPolicy'),('access_scope',[{'type':'cluster','namespaces':None}])]:
        changed=edit(indexed('aws_eks_access_policy_association.namespace','reader'),[field],value,access_plan)
        detected.append(rejected(lambda changed=changed:verify_plan(changed,access_input,scope),'namespace_escalation:'+field))
    for label,fn in [
        ('missing_resource',lambda p:p['resource_changes'].pop()),
        ('duplicate_resource',lambda p:p['resource_changes'].append(copy.deepcopy(p['resource_changes'][0]))),
        ('wrong_provider',lambda p:p['resource_changes'][0].update(provider_name='registry.terraform.io/unapproved/aws')),
        ('data_owner',lambda p:p['resource_changes'][0].update(mode='data')),
        ('replacement',lambda p:p['resource_changes'][0]['change'].update(actions=['delete','create'])),
        ('unknown_id',lambda p:next(r for r in p['resource_changes'] if r['type']=='aws_security_group')['change']['after_unknown'].update(id=True)),
        ('unknown_oidc',lambda p:next(r for r in p['resource_changes'] if r['type']=='aws_eks_cluster')['change']['after_unknown'].update(identity=True)),
        ('missing_output',lambda p:p['output_changes'].pop(next(iter(p['output_changes'])))),
    ]:
        changed=copy.deepcopy(plan);fn(changed);detected.append(rejected(lambda changed=changed:verify_plan(changed,v,scope),label))
    changed=copy.deepcopy(plan);output=next(iter(changed['output_changes'].values()));output['after']='unapproved'
    detected.append(rejected(lambda:verify_plan(changed,v,scope),'wrong_actual_output'))
    faults=[]
    for kind in ['version','test_abstract','test_plan','test_run','diagnostic','test_summary','test_file']:
        changed=copy.deepcopy(events);index=next(i for i,e in enumerate(changed) if e['type']==kind and (kind not in {'test_run','test_file'} or 'status' in e[kind]));changed.pop(index)
        faults.append(rejected(lambda changed=changed:verify_capture(changed,scope),'missing_'+kind))
    for kind in ['version','test_abstract','test_plan','test_run','test_summary','test_file']:
        changed=copy.deepcopy(events);index=next(i for i,e in enumerate(changed) if e['type']==kind and (kind not in {'test_run','test_file'} or 'status' in e[kind]));changed.insert(index,copy.deepcopy(changed[index]))
        faults.append(rejected(lambda changed=changed:verify_capture(changed,scope),'duplicate_'+kind))
    for status in ['fail','error','skip']:
        changed=copy.deepcopy(events);next(e for e in changed if e['type']=='test_run' and 'status' in e['test_run'])['test_run']['status']=status
        faults.append(rejected(lambda changed=changed:verify_capture(changed,scope),'bad_terminal:'+status))
    faults.append(rejected(lambda:verify_capture(events,scope,1),'nonzero_process'))
    for text in ['{broken','{"type":"test_plan","type":"test_summary"}','{"value":NaN}','{"value":Infinity}']:
        faults.append(rejected(lambda text=text:parse(text),'malformed_json:'+text))
    sources={str(p.relative_to(REPO)):p.read_text() for folder in [MODULE,ROOT] for p in folder.glob('*.tf')}
    source_mutations=[]
    variants=[('infra/modules/eks_platform/cluster.tf','endpoint_public_access    = false','endpoint_public_access = true'),
        ('infra/modules/eks_platform/cluster.tf','aws_iam_role_policy.cluster,',''),
        ('infra/modules/eks_platform/compute.tf','aws_eks_addon.vpc_cni,',''),
        ('infra/modules/eks_platform/compute.tf','aws_iam_role_policy_attachment.nodes,',''),
        ('infra/modules/eks_platform/compute.tf','aws_eks_access_policy_association.bootstrap,',''),
        ('infra/modules/eks_platform/compute.tf','security_groups             = [aws_security_group.nodes.id]','security_groups = []'),
        ('infra/modules/eks_platform/addons.tf','depends_on                  = [aws_eks_node_group.this]','depends_on = []'),
        ('infra/modules/eks_platform/iam.tf','url            = aws_eks_cluster.this.identity[0].oidc[0].issuer','url = "https://unapproved.example.test"'),
        ('infra/services/dev/ca-central-1/platform/providers.tf','allowed_account_ids = [var.aws_account_id]','allowed_account_ids = []'),
        ('infra/services/dev/ca-central-1/platform/backend.tf','"local"','"s3"')]
    for path,old,new in variants:
        require(old in sources[path],'source_mutation_witness:'+old);changed=sources.copy();changed[path]=changed[path].replace(old,new,1)
        source_mutations.append(rejected(lambda changed=changed:source_contract(changed),path+old))
    categories={
        'generated_resource_contracts':len(mutations),
        'iam_trust_and_policy_json':9,
        'namespace_privilege_escalation':2,
        'ownership_computed_values_and_outputs':9,
    }
    require(sum(categories.values())==len(detected),'mutation_category_reconciliation')
    require(len(detected)==len(set(detected)) and len(faults)==21 and len(source_mutations)==10,'unique_complete_security_cases')
    return dict(semantic_mutations=len(detected),semantic_mutation_categories=categories,
        semantic_mutation_detections=detected,capture_failure_injections=len(faults),
        capture_failure_detections=faults,source_dependency_mutations=len(source_mutations),
        source_dependency_detections=source_mutations)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compact',action='store_true')
    parser.add_argument('--scope',choices=['child','root'])
    parser.add_argument('--test-events',type=Path)
    parser.add_argument('--terraform-exit-code',type=int,default=0)
    parser.add_argument('--self-test',action='store_true')
    args=parser.parse_args()
    try:
        if args.compact:
            for event in read_events(sys.stdin):print(json.dumps(event,separators=(',',':')))
            return 0
        require(args.scope and args.test_events,'scope_and_capture_required');source_contract()
        with args.test_events.open() as stream:events=list(read_events(stream))
        report,plans=verify_capture(events,args.scope,args.terraform_exit_code)
        if args.self_test:report.update(self_test(events,args.scope,plans))
        print(json.dumps(report,indent=2))
    except (ValueError,KeyError,TypeError,IndexError,OSError) as error:
        print('Platform verification failed: '+str(error),file=sys.stderr);return 1
    return 0


if __name__=='__main__':sys.exit(main())
