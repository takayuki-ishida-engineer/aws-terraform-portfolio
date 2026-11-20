#!/usr/bin/env python3
"""Actual pinned Helm positives; independent schema/security/negative/evidence tests."""
import argparse,base64,copy,json,sys
from pathlib import Path
from unittest.mock import patch
sys.dont_write_bytecode=True
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from common import ROOT,LOCK,parse,metadata,need,sha
from render import render
from validate import verify,application_network_policy,structural

def capture(objects,evidence,d):
 need(evidence['status']=='rendered' and evidence['complete_v5'] is False and evidence['actual_helm_renders']==4,'fresh complete render evidence')
 need(type(evidence['runtime_contract_version']) is int and evidence['runtime_contract_version']==3,'F11 project-derived object names: contract3; legacy reports are not compatible')
 need(evidence['helm_sha256']==LOCK['helm']['binary_sha256'] and evidence['charts']=={k:v['sha256'] for k,v in LOCK['charts'].items()},'pinned artifacts')
 need(evidence['input_sha256']==sha(json.dumps(d,sort_keys=True,separators=(',',':')).encode()),'input evidence')
 need(evidence['manifest_sha256']==sha(json.dumps(objects,sort_keys=True,separators=(',',':')).encode()) and evidence['resource_count']==len(objects),'manifest evidence')
 need(evidence['stages']=={'namespaces':2,'base':16,'controller':13,'istiod':12,'gateway':5,'mesh_security':5,'admission':4,'binding_writer':3,'ingress':2},'complete ordered stage evidence')
 need(sum(evidence['stages'].values())==len(objects) and set(evidence['raw_chart_counts'])=={'controller','base','istiod','gateway'} and all(type(x) is int and x>0 for x in evidence['raw_chart_counts'].values()),'no partial/failed chart evidence')
 return verify(objects,d,True)
def with_project(q,project):
 # Keep every project-bound input consistent so only the project itself varies.
 c=q['controller_identity'];r=q['runtime'];r['project']=project;c['cluster_name']=project+'-dev-eks';c['role_arn']=c['role_arn'].rsplit('/',1)[0]+'/'+project+'-dev-role-lbc'
 r['gateway_tls_secret']=project+'-gateway-tls';r['gateway_client_ca_secret']=project+'-gateway-client-cacert';return q
# Names fixed by the upstream charts and products (F11 keeps them), written out
# here independently of the renderer. Everything else must be <project>-<purpose>.
def upstream(kind,name,rev):
 if kind=='CustomResourceDefinition':return name.endswith(('.istio.io','.elbv2.k8s.aws'))
 if kind=='Namespace':return name=='istio-system'
 if name.startswith('aws-load-balancer-controller'):return True
 # Istio charts suffix their object names with the revision, itself <project>-v1.
 return name in {'istiod-default-validator','istiod-'+rev,'istiod-clusterrole-'+rev+'-istio-system','istio-'+rev,'istio-sidecar-injector-'+rev,'istio-validator-'+rev+'-istio-system','values-'+rev}
def naming(q,project):
 rev=project+'-v1';project_names=0
 for o in q:
  name=o['metadata']['name'];ns=o['metadata'].get('namespace','')
  need(ns in {'','kube-system','istio-system',project+'-ingress',project+'-app'},'namespace naming:'+ns)
  if name.startswith(project+'-'):project_names+=1
  else:need(upstream(o['kind'],name,rev),'object naming:'+o['kind']+'/'+name)
 return project_names
def main():
 a=argparse.ArgumentParser(description=__doc__);a.add_argument('--helm',required=True);a.add_argument('--report',type=Path);args=a.parse_args()
 d=parse((ROOT/'kubernetes/tests/fixtures/runtime.json').read_text());objects,evidence=render(d,args.helm,True);count=capture(objects,evidence,d)
 alt=with_project(copy.deepcopy(d),'demo');alt['controller_identity']['kubernetes_version']='1.35';alt['private_ingress']['backend_target_port']=9444;alt['runtime']['backend_hostname']='alternate.portfolio.invalid';alt['runtime']['expected_client_spki']=[base64.b64encode(bytes([1])*32).decode()]
 alt['private_ingress']['target_group_arn']=d['private_ingress']['target_group_arn'].replace('/test-ingress-gateway/','/alternate-gateway/')
 alt['controller_identity']['target_group_arn']=alt['private_ingress']['target_group_arn'];need(alt['private_ingress']['target_group_arn']!=d['private_ingress']['target_group_arn'],'distinct synthetic target groups for the two backend ports')
 altobjects,altevidence=render(alt,args.helm,True);capture(altobjects,altevidence,alt)
 # F11: both renders name every project-created object <project>-<purpose>,
 # and neither carries the other project's names.
 project_owned=naming(objects,'test');need(project_owned==naming(altobjects,'demo') and project_owned>=20,'project-derived object names')
 need('demo-' not in json.dumps(objects) and 'test-' not in json.dumps([o['metadata'] for o in altobjects]),'no cross-project names')
 mutations=[]
 def reject(fn,label,collection):
  try:fn()
  except (ValueError,KeyError,TypeError,IndexError):collection.append(label);return
  raise ValueError('unsafe case accepted:'+label)
 def find(q,kind,name=None):return next(x for x in q if x['kind']==kind and (name is None or x['metadata']['name']==name))
 # Assert the actual generated policy, not an expected inventory entry alone.
 for q,inputs in [(objects,d),(altobjects,alt)]:
  P=inputs['runtime']['project'];G=P+'-gateway'
  np=find(q,'NetworkPolicy');need(np['apiVersion']=='networking.k8s.io/v1' and np['metadata']=={'name':P+'-default-deny','namespace':P+'-app'},'rendered NP identity')
  need(np['spec']=={'podSelector':{},'policyTypes':['Ingress','Egress'],'ingress':[],'egress':[]},'rendered NP all Pods/both directions/no rules')
  need(structural([np])==1,'actual NetworkPolicy schema validation')
  need(find(q,'PeerAuthentication')['spec']=={'mtls':{'mode':'STRICT'}} and find(q,'AuthorizationPolicy')['spec']=={'action':'ALLOW','rules':[]},'preserved independent mesh authentication/authorization')
  port=inputs['private_ingress']['backend_target_port'];service=find(q,'Service',G)['spec']['ports'][0];pod=find(q,'Deployment',G)['spec']['template']['spec']['containers'][0]
  need(service['port']==service['targetPort']==find(q,'TargetGroupBinding')['spec']['serviceRef']['port']==find(q,'Gateway')['spec']['servers'][0]['port']['number']==port,'actual Service/targetPort/TGB/Gateway derive from backend input')
  need(next(x['containerPort'] for x in pod['ports'] if x['name']=='https-backend')==port,'actual Pod backend port')
  expression=find(q,'ValidatingAdmissionPolicy',P+'-target-registration')['spec']['validations'][5]['expression']
  need(expression=="object.spec.serviceRef.name == '"+G+"' && object.spec.serviceRef.port == "+str(port),'actual CEL backend port')
  need(pod['readinessProbe']['httpGet']['port']==pod['livenessProbe']['tcpSocket']['port']==15021 and pod['securityContext']['runAsUser']==1337,'Gateway probe/UID unchanged')
 cases=[]
 def change(label,kind,name,path,value):
  def edit(q):
   o=find(q,kind,name)
   for k in path[:-1]:o=o[k]
   o[path[-1]]=value
  cases.append((label,edit))
 for mode in ['SIMPLE','PASSTHROUGH','OPTIONAL_MUTUAL']:change('TLS downgrade:'+mode,'Gateway',None,['spec','servers',0,'tls','mode'],mode)
 for label,path,value in [('old_TLS',['minProtocolVersion'],'TLSV1_0'),('missing_server_Secret',['credentialName'],''),('missing_client_CA',['caCertCredentialName'],''),('missing_client_identity',['verifyCertificateSpki'],[]),('unapproved_client_identity',['verifyCertificateSpki'],['AgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgI='])]:change(label,'Gateway',None,['spec','servers',0,'tls']+path,value)
 change('wildcard_hostname','Gateway',None,['spec','servers',0,'hosts'],['*'])
 change('plaintext_protocol','Gateway',None,['spec','servers',0,'port','protocol'],'HTTP')
 cases.append(('plaintext_fallback',lambda q:find(q,'Gateway')['spec']['servers'].append({'port':{'number':80,'name':'http','protocol':'HTTP'},'hosts':['*']})))
 for mode in ['PERMISSIVE','DISABLE']:change('mesh downgrade:'+mode,'PeerAuthentication',None,['spec','mtls','mode'],mode)
 change('allow_everyone','AuthorizationPolicy',None,['spec','rules'],[{}])
 change('wildcard_principal','AuthorizationPolicy',None,['spec','rules'],[{'from':[{'source':{'principals':['*']}}]}])
 for field,value in [('targetGroupARN','arn:aws:elasticloadbalancing:ca-central-1:000000000000:targetgroup/other/0123456789abcdef'),('targetType','instance'),('vpcID','vpc-11111111'),('networking',{'ingress':[]}),('iamRoleArnToAssume','arn:aws:iam::111111111111:role/other')]:change('wrong_TGB:'+field,'TargetGroupBinding',None,['spec',field],value)
 change('wrong_TGB_Service','TargetGroupBinding',None,['spec','serviceRef'],{'name':'other','port':80})
 change('LoadBalancer_Service','Service','test-gateway',['spec','type'],'LoadBalancer')
 change('wrong_Service_port','Service','test-gateway',['spec','ports',0,'port'],80)
 change('wrong_targetPort','Service','test-gateway',['spec','ports',0,'targetPort'],443)
 change('wrong_Service_selector','Service','test-gateway',['spec','selector'],{'app':'other'})
 change('wrong_Pod_port','Deployment','test-gateway',['spec','template','spec','containers',0,'ports',1,'containerPort'],443)
 change('unapproved_gateway_image','Deployment','test-gateway',['spec','template','spec','containers',0,'image'],'docker.io/istio/proxyv2:latest')
 change('wrong_gateway_SA','Deployment','test-gateway',['spec','template','spec','serviceAccountName'],'default')
 change('wildcard_IRSA_SA','ServiceAccount','aws-load-balancer-controller',['metadata','annotations','eks.amazonaws.com/role-arn'],'arn:aws:iam::111111111111:role/other')
 change('unreviewed_node_AZ','Deployment','test-gateway',['spec','template','spec','nodeSelector'],{'topology.kubernetes.io/zone':'ca-central-1b'})
 change('privileged_container','Deployment','test-gateway',['spec','template','spec','containers',0,'securityContext','privileged'],True)
 change('host_namespace','Deployment','test-gateway',['spec','template','spec','hostPID'],True)
 change('unconfined_seccomp','Deployment','test-gateway',['spec','template','spec','containers',0,'securityContext','seccompProfile'],{'type':'Unconfined'})
 change('added_capability','Deployment','test-gateway',['spec','template','spec','containers',0,'securityContext','capabilities'],{'drop':['ALL'],'add':['NET_ADMIN']})
 change('privileged_gateway','Deployment','test-gateway',['spec','template','spec','containers',0,'securityContext','allowPrivilegeEscalation'],True)
 change('insecure_CA_fallback','Deployment','istiod-test-v1',['spec','template','spec','volumes',2,'secret','optional'],True)
 cases.append(('missing_CA_keys',lambda q:next(v for v in find(q,'Deployment','istiod-test-v1')['spec']['template']['spec']['volumes'] if v['name']=='cacerts')['secret'].pop('items')))
 change('cluster_admin_binding','ClusterRoleBinding','aws-load-balancer-controller-rolebinding',['roleRef','name'],'cluster-admin')
 change('untrusted_cluster_binding','ClusterRoleBinding','aws-load-balancer-controller-rolebinding',['subjects'],[{'kind':'Group','name':'system:authenticated','apiGroup':'rbac.authorization.k8s.io'}])
 change('broad_controller_RBAC','ClusterRole','aws-load-balancer-controller-role',['rules',0,'verbs'],['*'])
 cases.append(('broad_TGB_writer',lambda q:find(q,'Role','test-binding-writer')['rules'].append({'apiGroups':['*'],'resources':['*'],'verbs':['*']})))
 change('untrusted_binding_actor','RoleBinding','test-binding-writer',['subjects'],[{'kind':'Group','name':'system:authenticated','apiGroup':'rbac.authorization.k8s.io'}])
 change('bypassed_namespace_guard','ValidatingAdmissionPolicy','test-no-lb-service',['spec','matchConstraints','namespaceSelector'],{'matchLabels':{'unmatched':'true'}})
 change('Istio_webhook_fail_open','MutatingWebhookConfiguration','istio-sidecar-injector-test-v1',['webhooks',0,'failurePolicy'],'Ignore')
 change('missing_binding_guard','ValidatingAdmissionPolicy','test-target-registration',['spec','validations'],[{'expression':'true'}])
 change('admission_ignore','ValidatingAdmissionPolicy','test-target-registration',['spec','failurePolicy'],'Ignore')
 change('admission_audit_only','ValidatingAdmissionPolicyBinding','test-target-registration',['spec','validationActions'],['Audit'])
 change('controller_gate_disabled','ValidatingAdmissionPolicy','test-no-lb-service',['spec','validations'],[{'expression':'true'}])
 for flag,new in [('--aws-region','us-east-1'),('--aws-vpc-id','vpc-11111111'),('--cluster-name','other'),('--watch-namespace',''),('--enable-backend-security-group','true'),('--enable-manage-backend-security-group-rules','true'),('--feature-gates','EnableServiceController=true')]:
  def mutate(q,flag=flag,new=new):
   co=find(q,'Deployment','aws-load-balancer-controller')['spec']['template']['spec']['containers'][0];co['args']=[flag+'='+new if x.startswith(flag+'=') else x for x in co['args']]
  cases.append(('controller_flag:'+flag,mutate))
 change('legacy_name:ingress_namespace','Namespace','test-ingress',['metadata','name'],'istio-ingress')
 change('legacy_name:Gateway','Gateway',None,['metadata','name'],'portfolio-backend')
 change('legacy_name:TargetGroupBinding','TargetGroupBinding',None,['metadata','name'],'portfolio-gateway')
 change('legacy_name:PeerAuthentication','PeerAuthentication',None,['metadata','name'],'strict')
 change('other_project_name:binding_writer','Role','test-binding-writer',['metadata','name'],'demo-binding-writer')
 change('app_SA_token','ServiceAccount','test-application',['automountServiceAccountToken'],True)
 cases.extend([('missing_object',lambda q:q.pop()),('duplicate_object',lambda q:q.append(copy.deepcopy(q[0]))),('forbidden_Secret',lambda q:q.append({'apiVersion':'v1','kind':'Secret','metadata':{'name':'forbidden'}}))])
 # Exercise NP semantics separately as well as through full-bundle validation:
 # an exact-inventory failure must not be the only additive-policy defense.
 prior_cases=len(cases)
 cases.append(('NP_missing',lambda q:q.remove(find(q,'NetworkPolicy'))))
 change('NP_partial_selector','NetworkPolicy',None,['spec','podSelector'],{'matchLabels':{'app':'subset'}})
 change('NP_expression_selector','NetworkPolicy',None,['spec','podSelector'],{'matchExpressions':[{'key':'app','operator':'Exists'}]})
 for types in [['Ingress'],['Egress'],[]]:change('NP_policy_types:'+str(types),'NetworkPolicy',None,['spec','policyTypes'],types)
 for direction,peer in [('ingress','from'),('egress','to')]:
  change('NP_allow_all:'+direction,'NetworkPolicy',None,['spec',direction],[{}])
  change('NP_public_IPv4:'+direction,'NetworkPolicy',None,['spec',direction],[{peer:[{'ipBlock':{'cidr':'0.0.0.0/0'}}]}])
  change('NP_all_namespaces:'+direction,'NetworkPolicy',None,['spec',direction],[{peer:[{'namespaceSelector':{}}]}])
  cases.append(('NP_missing_field:'+direction,lambda q,direction=direction:find(q,'NetworkPolicy')['spec'].pop(direction)))
 change('NP_wrong_namespace','NetworkPolicy',None,['metadata','namespace'],'test-ingress')
 change('NP_missing_selector','NetworkPolicy',None,['spec','podSelector'],None)
 change('NP_wrong_api','NetworkPolicy',None,['apiVersion'],'networking.k8s.io/v1beta1')
 def additive_allow(q):
  np=copy.deepcopy(find(q,'NetworkPolicy'));np['metadata']['name']='unreviewed-allow-all';np['spec']['ingress']=[{}];np['spec']['egress']=[{}];q.append(np)
 cases.append(('NP_additive_allow_policy',additive_allow))
 def policy_before_namespace(q):
  np=find(q,'NetworkPolicy');q.remove(np);q.insert(0,np)
 cases.append(('NP_before_namespace',policy_before_namespace))
 policy_cases=cases[prior_cases:];policy_mutations=[]
 for label,mutate in policy_cases:
  q=copy.deepcopy(objects);mutate(q);reject(lambda q=q:application_network_policy(q,'test'),label,policy_mutations)
 for label,mutate in cases:
  q=copy.deepcopy(objects);mutate(q);reject(lambda q=q:verify(q,d,True),label,mutations)
 # The naming contract itself rejects legacy, unprefixed and other-project names.
 for label,kind,name,path,value in [('legacy_namespace_name','Namespace','test-ingress',['metadata','name'],'istio-ingress'),('legacy_namespace_field','NetworkPolicy',None,['metadata','namespace'],'portfolio-app'),('unprefixed_object','Role','test-binding-writer',['metadata','name'],'binding-writer'),('other_project','Gateway',None,['metadata','name'],'demo-backend'),('legacy_revision','ConfigMap','values-test-v1',['metadata','name'],'values-portfolio-v1')]:
  q=copy.deepcopy(objects);o=find(q,kind,name)
  for k in path[:-1]:o=o[k]
  o[path[-1]]=value;reject(lambda q=q:naming(q,'test'),'naming:'+label,mutations)
 # Exercise individual and coordinated port changes on both actual renders.
 # None can be accepted merely because every manifest agrees on the wrong port.
 gateway_mutations=[]
 for inputs,actual,other in [(d,objects,alt),(alt,altobjects,d)]:
  label_scope=str(inputs['private_ingress']['backend_target_port']);P=inputs['runtime']['project'];G=P+'-gateway'
  def update(q,kind,path,value,G=G):
   target=find(q,kind,G if kind in ['Service','Deployment','TargetGroupBinding'] else None)
   for key in path[:-1]:target=target[key]
   target[path[-1]]=value
  def all_wrong(q,P=P,G=G):
   for kind,path in [('Service',['spec','ports',0,'port']),('Service',['spec','ports',0,'targetPort']),('Deployment',['spec','template','spec','containers',0,'ports',1,'containerPort']),('TargetGroupBinding',['spec','serviceRef','port']),('Gateway',['spec','servers',0,'port','number'])]:update(q,kind,path,9445)
   find(q,'ValidatingAdmissionPolicy',P+'-target-registration')['spec']['validations'][5]['expression']="object.spec.serviceRef.name == '"+G+"' && object.spec.serviceRef.port == 9445"
  edits=[('Service443',lambda q:update(q,'Service',['spec','ports',0,'port'],443)),('targetPort443',lambda q:update(q,'Service',['spec','ports',0,'targetPort'],443)),('Pod443',lambda q:update(q,'Deployment',['spec','template','spec','containers',0,'ports',1,'containerPort'],443)),('Gateway443',lambda q:update(q,'Gateway',['spec','servers',0,'port','number'],443)),('TGB443',lambda q:update(q,'TargetGroupBinding',['spec','serviceRef','port'],443)),('admission443',lambda q,P=P,G=G:find(q,'ValidatingAdmissionPolicy',P+'-target-registration')['spec']['validations'][5].update(expression="object.spec.serviceRef.name == '"+G+"' && object.spec.serviceRef.port == 443")),('wrong_TG_reference',lambda q:update(q,'TargetGroupBinding',['spec','targetGroupARN'],other['private_ingress']['target_group_arn'])),('coordinated_wrong_port',all_wrong),('probe_changed',lambda q:update(q,'Deployment',['spec','template','spec','containers',0,'livenessProbe','tcpSocket','port'],9445)),('UID_changed',lambda q:update(q,'Deployment',['spec','template','spec','containers',0,'securityContext','runAsUser'],0))]
  for label,edit in edits:
   q=copy.deepcopy(actual);edit(q);name='gateway:'+label_scope+':'+label;reject(lambda q=q,inputs=inputs:verify(q,inputs,True),name,mutations);gateway_mutations.append(name)
 negatives=[]
 for field in ['project','backend_hostname','gateway_tls_secret','gateway_client_ca_secret','expected_client_spki','webhook_ca_bundle','istio_ca_secret','resources','trust_domain']:
  q=copy.deepcopy(d);q['runtime'].pop(field);reject(lambda q=q:metadata(q,True),'missing:'+field,negatives)
 for label,fn in [('CA_not_root_SDS',lambda q:q['runtime'].update(gateway_client_ca_secret='leaf-only')),('unexpected_input',lambda q:q['controller_identity'].update(unreviewed='not-minimal')),('scope_mismatch',lambda q:q['private_ingress']['scope'].update(account_id='111111111111')),('wrong_target',lambda q:q['private_ingress'].update(target_group_arn='arn:aws:elasticloadbalancing:ca-central-1:000000000000:targetgroup/other/0123456789abcdef')),('bad_spki',lambda q:q['runtime'].update(expected_client_spki=['*'])),('wrong_version',lambda q:q['controller_identity'].update(kubernetes_version='1.99')),('unresolved',lambda q:q['runtime'].update(backend_hostname='${HOST}')),('missing_limits',lambda q:q['runtime']['resources']['gateway'].pop('limits')),('credential_in_CA',lambda q:q['runtime'].update(webhook_ca_bundle='LS0tLS1CRUdJTiBQUklWQVRFIEtFWS0tLS0t'))]:
  q=copy.deepcopy(d);fn(q);reject(lambda q=q:metadata(q,True),label,negatives)
 reject(lambda:metadata(d,False),'fixture_cannot_be_live',negatives)
 # F11 project boundary: each invalid project keeps the other project-bound inputs
 # consistent with it; each mismatch changes one project-bound input only.
 for project in ['Test','1test','test-','te_st','abcdefghijk','myaws','amazon1','cognito','']:
  q=with_project(copy.deepcopy(d),project);reject(lambda q=q:metadata(q,True),'invalid_project:'+repr(project),negatives)
 q=copy.deepcopy(d);q['runtime']['project']=7;reject(lambda q=q:metadata(q,True),'invalid_project:int',negatives)
 for label,fn in [('project_cluster_mismatch',lambda q:q['controller_identity'].update(cluster_name='other-dev-eks')),('project_role_mismatch',lambda q:q['controller_identity'].update(role_arn='arn:aws:iam::000000000000:role/other-dev-role-lbc')),('gateway_secret_without_project',lambda q:q['runtime'].update(gateway_tls_secret='other-gateway-tls')),('client_ca_without_project',lambda q:q['runtime'].update(gateway_client_ca_secret='other-gateway-client-cacert')),('legacy_input_interface_1',lambda q:q.update(interface_version=1))]:
  q=copy.deepcopy(d);fn(q);reject(lambda q=q:metadata(q,True),label,negatives)
 accepted_projects=['demo','a','ab','abcdefghij','my-app1']
 for project in accepted_projects:metadata(with_project(copy.deepcopy(d),project),True)
 with patch('render.helm',side_effect=AssertionError('invalid backend input reached Helm')):
  for port in [-1,0,80,443,1023,65536,15000,15010,15011,15012,15014,15017,15020,15021,15053,15090,True,8443.5,'8443']:
   q=copy.deepcopy(d);q['private_ingress']['backend_target_port']=port;reject(lambda q=q:render(q,args.helm,True),'invalid_backend_port:'+repr(port),negatives)
  q=copy.deepcopy(d);q['private_ingress'].pop('backend_target_port');reject(lambda:render(q,args.helm,True),'missing_backend_port',negatives)
 accepted_ports=[1024,14999,15091,65535]
 for port in accepted_ports:
  q=copy.deepcopy(d);q['private_ingress']['backend_target_port']=port;metadata(q,True)
 faults=[]
 for key in ['status','complete_v5','actual_helm_renders','helm_sha256','charts','input_sha256','manifest_sha256','resource_count','stages','raw_chart_counts']:
  q=copy.deepcopy(evidence);q.pop(key);reject(lambda q=q:capture(objects,q,d),'missing:'+key,faults)
 for key,value in [('status','failed'),('actual_helm_renders',3),('helm_sha256','fabricated'),('manifest_sha256','fabricated'),('resource_count',0),('complete_v5',True)]:
  q=copy.deepcopy(evidence);q[key]=value;reject(lambda q=q:capture(objects,q,d),'fabricated:'+key,faults)
 for label,edit in [('old_mesh_stage_count',lambda e:e['stages'].update(mesh_security=4)),('missing_mesh_stage',lambda e:e['stages'].pop('mesh_security'))]:
  q=copy.deepcopy(evidence);edit(q);reject(lambda q=q:capture(objects,q,d),label,faults)
 for text in ['{broken','{"x":1,"x":2}','{"x":NaN}']:
  reject(lambda text=text:parse(text),'malformed:'+text,faults)
 q=copy.deepcopy(evidence);q.pop('runtime_contract_version');reject(lambda:capture(objects,q,d),'missing_runtime_contract_version',faults)
 for key,value in [('runtime_contract_version',1),('input_sha256','fabricated'),('charts',{})]:
  q=copy.deepcopy(evidence);q[key]=value;reject(lambda q=q:capture(objects,q,d),'fabricated:'+key,faults)
 bad=copy.deepcopy(objects);find(bad,'Service','test-gateway')['spec']['ports'][0]['port']=443
 q=copy.deepcopy(evidence);q['manifest_sha256']=sha(json.dumps(bad,sort_keys=True,separators=(',',':')).encode());reject(lambda:capture(bad,q,d),'forged_hash_matching_unsafe_manifest',faults)
 report={'status':'passed','runtime_contract_version':3,'complete_runtime':True,'complete_v5':False,'aws_api_calls':0,'kubernetes_api_calls':0,'actual_helm_renders':8,'positive_configurations':2,'resource_count':count,'inventory':evidence['stages'],'schema_checked_objects':count*2,'semantic_mutations':len(mutations),'detected_mutations':mutations,'network_policy_mutations':len(policy_mutations),'detected_network_policy_mutations':policy_mutations,'gateway_contract_mutations':len(gateway_mutations),'detected_gateway_contract_mutations':gateway_mutations,'accepted_input_boundaries':accepted_ports,'accepted_projects':accepted_projects,'project_named_objects':project_owned,'negative_cases':len(negatives),'rejected_inputs':negatives,'evidence_faults':len(faults),'rejected_evidence':faults,'chart_sha256':evidence['charts']}
 if args.report:args.report.write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps(report,indent=2))
if __name__=='__main__':main()
