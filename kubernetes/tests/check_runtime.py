#!/usr/bin/env python3
"""Actual pinned Helm positives; independent schema/security/negative/evidence tests."""
import argparse,base64,copy,json,sys
from pathlib import Path
sys.dont_write_bytecode=True
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from common import ROOT,LOCK,parse,metadata,need,sha
from render import render
from validate import verify

def capture(objects,evidence,d):
 need(evidence['status']=='rendered' and evidence['complete_v5'] is False and evidence['actual_helm_renders']==4,'fresh complete render evidence')
 need(evidence['helm_sha256']==LOCK['helm']['binary_sha256'] and evidence['charts']=={k:v['sha256'] for k,v in LOCK['charts'].items()},'pinned artifacts')
 need(evidence['input_sha256']==sha(json.dumps(d,sort_keys=True,separators=(',',':')).encode()),'input evidence')
 need(evidence['manifest_sha256']==sha(json.dumps(objects,sort_keys=True,separators=(',',':')).encode()) and evidence['resource_count']==len(objects),'manifest evidence')
 need(evidence['stages']=={'namespaces':2,'base':16,'controller':13,'istiod':12,'gateway':5,'mesh_security':4,'admission':4,'binding_writer':3,'ingress':2},'complete ordered stage evidence')
 need(sum(evidence['stages'].values())==len(objects) and set(evidence['raw_chart_counts'])=={'controller','base','istiod','gateway'} and all(type(x) is int and x>0 for x in evidence['raw_chart_counts'].values()),'no partial/failed chart evidence')
 return verify(objects,d,True)
def main():
 a=argparse.ArgumentParser(description=__doc__);a.add_argument('--helm',required=True);a.add_argument('--report',type=Path);args=a.parse_args()
 d=parse((ROOT/'kubernetes/tests/fixtures/runtime.json').read_text());objects,evidence=render(d,args.helm,True);count=capture(objects,evidence,d)
 alt=copy.deepcopy(d);alt['controller_identity']['kubernetes_version']='1.35';alt['private_ingress']['backend_target_port']=9444;alt['runtime']['backend_hostname']='alternate.portfolio.invalid';alt['runtime']['expected_client_spki']=[base64.b64encode(bytes([1])*32).decode()];altobjects,altevidence=render(alt,args.helm,True);capture(altobjects,altevidence,alt)
 mutations=[]
 def reject(fn,label,collection):
  try:fn()
  except (ValueError,KeyError,TypeError,IndexError):collection.append(label);return
  raise ValueError('unsafe case accepted:'+label)
 def find(q,kind,name=None):return next(x for x in q if x['kind']==kind and (name is None or x['metadata']['name']==name))
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
 change('LoadBalancer_Service','Service','portfolio-gateway',['spec','type'],'LoadBalancer')
 change('wrong_Service_port','Service','portfolio-gateway',['spec','ports',0,'port'],80)
 change('wrong_targetPort','Service','portfolio-gateway',['spec','ports',0,'targetPort'],443)
 change('wrong_Service_selector','Service','portfolio-gateway',['spec','selector'],{'app':'other'})
 change('wrong_Pod_port','Deployment','portfolio-gateway',['spec','template','spec','containers',0,'ports',1,'containerPort'],443)
 change('unapproved_gateway_image','Deployment','portfolio-gateway',['spec','template','spec','containers',0,'image'],'docker.io/istio/proxyv2:latest')
 change('wrong_gateway_SA','Deployment','portfolio-gateway',['spec','template','spec','serviceAccountName'],'default')
 change('wildcard_IRSA_SA','ServiceAccount','aws-load-balancer-controller',['metadata','annotations','eks.amazonaws.com/role-arn'],'arn:aws:iam::111111111111:role/other')
 change('unreviewed_node_AZ','Deployment','portfolio-gateway',['spec','template','spec','nodeSelector'],{'topology.kubernetes.io/zone':'ca-central-1b'})
 change('privileged_container','Deployment','portfolio-gateway',['spec','template','spec','containers',0,'securityContext','privileged'],True)
 change('host_namespace','Deployment','portfolio-gateway',['spec','template','spec','hostPID'],True)
 change('unconfined_seccomp','Deployment','portfolio-gateway',['spec','template','spec','containers',0,'securityContext','seccompProfile'],{'type':'Unconfined'})
 change('added_capability','Deployment','portfolio-gateway',['spec','template','spec','containers',0,'securityContext','capabilities'],{'drop':['ALL'],'add':['NET_ADMIN']})
 change('privileged_gateway','Deployment','portfolio-gateway',['spec','template','spec','containers',0,'securityContext','allowPrivilegeEscalation'],True)
 change('insecure_CA_fallback','Deployment','istiod-portfolio-v1',['spec','template','spec','volumes',2,'secret','optional'],True)
 cases.append(('missing_CA_keys',lambda q:next(v for v in find(q,'Deployment','istiod-portfolio-v1')['spec']['template']['spec']['volumes'] if v['name']=='cacerts')['secret'].pop('items')))
 change('cluster_admin_binding','ClusterRoleBinding','aws-load-balancer-controller-rolebinding',['roleRef','name'],'cluster-admin')
 change('untrusted_cluster_binding','ClusterRoleBinding','aws-load-balancer-controller-rolebinding',['subjects'],[{'kind':'Group','name':'system:authenticated','apiGroup':'rbac.authorization.k8s.io'}])
 change('broad_controller_RBAC','ClusterRole','aws-load-balancer-controller-role',['rules',0,'verbs'],['*'])
 cases.append(('broad_TGB_writer',lambda q:find(q,'Role','portfolio-binding-writer')['rules'].append({'apiGroups':['*'],'resources':['*'],'verbs':['*']})))
 change('untrusted_binding_actor','RoleBinding','portfolio-binding-writer',['subjects'],[{'kind':'Group','name':'system:authenticated','apiGroup':'rbac.authorization.k8s.io'}])
 change('bypassed_namespace_guard','ValidatingAdmissionPolicy','portfolio-no-lb-service',['spec','matchConstraints','namespaceSelector'],{'matchLabels':{'unmatched':'true'}})
 change('Istio_webhook_fail_open','MutatingWebhookConfiguration','istio-sidecar-injector-portfolio-v1',['webhooks',0,'failurePolicy'],'Ignore')
 change('missing_binding_guard','ValidatingAdmissionPolicy','portfolio-target-registration',['spec','validations'],[{'expression':'true'}])
 change('admission_ignore','ValidatingAdmissionPolicy','portfolio-target-registration',['spec','failurePolicy'],'Ignore')
 change('admission_audit_only','ValidatingAdmissionPolicyBinding','portfolio-target-registration',['spec','validationActions'],['Audit'])
 change('controller_gate_disabled','ValidatingAdmissionPolicy','portfolio-no-lb-service',['spec','validations'],[{'expression':'true'}])
 for flag,new in [('--aws-region','us-east-1'),('--aws-vpc-id','vpc-11111111'),('--cluster-name','other'),('--watch-namespace',''),('--enable-backend-security-group','true'),('--enable-manage-backend-security-group-rules','true'),('--feature-gates','EnableServiceController=true')]:
  def mutate(q,flag=flag,new=new):
   co=find(q,'Deployment','aws-load-balancer-controller')['spec']['template']['spec']['containers'][0];co['args']=[flag+'='+new if x.startswith(flag+'=') else x for x in co['args']]
  cases.append(('controller_flag:'+flag,mutate))
 cases.extend([('missing_object',lambda q:q.pop()),('duplicate_object',lambda q:q.append(copy.deepcopy(q[0]))),('forbidden_Secret',lambda q:q.append({'apiVersion':'v1','kind':'Secret','metadata':{'name':'forbidden'}}))])
 for label,mutate in cases:
  q=copy.deepcopy(objects);mutate(q);reject(lambda q=q:verify(q,d,True),label,mutations)
 negatives=[]
 for field in ['backend_hostname','gateway_tls_secret','gateway_client_ca_secret','expected_client_spki','webhook_ca_bundle','istio_ca_secret','resources','trust_domain']:
  q=copy.deepcopy(d);q['runtime'].pop(field);reject(lambda q=q:metadata(q,True),'missing:'+field,negatives)
 for label,fn in [('CA_not_root_SDS',lambda q:q['runtime'].update(gateway_client_ca_secret='leaf-only')),('unexpected_input',lambda q:q['controller_identity'].update(unreviewed='not-minimal')),('scope_mismatch',lambda q:q['private_ingress']['scope'].update(account_id='111111111111')),('wrong_target',lambda q:q['private_ingress'].update(target_group_arn='arn:aws:elasticloadbalancing:ca-central-1:000000000000:targetgroup/other/0123456789abcdef')),('bad_spki',lambda q:q['runtime'].update(expected_client_spki=['*'])),('wrong_version',lambda q:q['controller_identity'].update(kubernetes_version='1.99')),('unresolved',lambda q:q['runtime'].update(backend_hostname='${HOST}')),('missing_limits',lambda q:q['runtime']['resources']['gateway'].pop('limits')),('credential_in_CA',lambda q:q['runtime'].update(webhook_ca_bundle='LS0tLS1CRUdJTiBQUklWQVRFIEtFWS0tLS0t'))]:
  q=copy.deepcopy(d);fn(q);reject(lambda q=q:metadata(q,True),label,negatives)
 reject(lambda:metadata(d,False),'fixture_cannot_be_live',negatives)
 faults=[]
 for key in ['status','complete_v5','actual_helm_renders','helm_sha256','charts','input_sha256','manifest_sha256','resource_count','stages','raw_chart_counts']:
  q=copy.deepcopy(evidence);q.pop(key);reject(lambda q=q:capture(objects,q,d),'missing:'+key,faults)
 for key,value in [('status','failed'),('actual_helm_renders',3),('helm_sha256','fabricated'),('manifest_sha256','fabricated'),('resource_count',0),('complete_v5',True)]:
  q=copy.deepcopy(evidence);q[key]=value;reject(lambda q=q:capture(objects,q,d),'fabricated:'+key,faults)
 for text in ['{broken','{"x":1,"x":2}','{"x":NaN}']:
  reject(lambda text=text:parse(text),'malformed:'+text,faults)
 report={'status':'passed','complete_runtime':True,'complete_v5':False,'aws_api_calls':0,'kubernetes_api_calls':0,'actual_helm_renders':8,'positive_configurations':2,'resource_count':count,'inventory':evidence['stages'],'schema_checked_objects':count*2,'semantic_mutations':len(mutations),'detected_mutations':mutations,'negative_cases':len(negatives),'rejected_inputs':negatives,'evidence_faults':len(faults),'rejected_evidence':faults,'chart_sha256':evidence['charts']}
 if args.report:args.report.write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps(report,indent=2))
if __name__=='__main__':main()
