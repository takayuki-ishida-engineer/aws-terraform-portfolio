#!/usr/bin/env python3
"""Credential-free pinned Helm rendering, reviewed overlays and ordered runtime bundle."""
import argparse,base64,copy,json,sys
from pathlib import Path
from common import ROOT,LOCK,docs,fill,helm,metadata,names,parse,need,sha
SENTINELS={'caCert':'EXTERNAL_CA_REFERENCE_ONLY','cert':'EXTERNAL_CERT_REFERENCE_ONLY','key':'EXTERNAL_KEY_REFERENCE_ONLY'}
READ_CLUSTER=[{'apiGroups':[''],'resources':['nodes','namespaces'],'verbs':['get','list','watch']},{'apiGroups':['networking.k8s.io'],'resources':['ingressclasses'],'verbs':['get','list','watch']},{'apiGroups':['elbv2.k8s.aws'],'resources':['ingressclassparams'],'verbs':['get','list','watch']}]
def read_namespace(gateway):return [{'apiGroups':[''],'resources':['pods','services','endpoints'],'verbs':['get','list','watch']},{'apiGroups':[''],'resources':['events'],'verbs':['create','patch']},{'apiGroups':[''],'resources':['pods/status'],'verbs':['patch','update']},{'apiGroups':['discovery.k8s.io'],'resources':['endpointslices'],'verbs':['get','list','watch']},{'apiGroups':['networking.k8s.io'],'resources':['ingresses'],'verbs':['get','list','watch']},{'apiGroups':['elbv2.k8s.aws'],'resources':['targetgroupbindings'],'verbs':['get','list','watch']},{'apiGroups':['elbv2.k8s.aws'],'resources':['targetgroupbindings','targetgroupbindings/status'],'resourceNames':[gateway],'verbs':['patch','update']}]
def resource(kind,name,ns='',api='v1',**body):return dict(apiVersion=api,kind=kind,metadata=dict(name=name,**({'namespace':ns} if ns else {})),**body)
def render(d,tool,fixture=False):
 metadata(d,fixture);c=d['controller_identity'];p=d['private_ingress'];r=d['runtime'];version=c['kubernetes_version'];stages={};raw_counts={}
 project=r['project'];N=names(project);REV=N['revision'];ING=N['ingress_namespace']
 namespaces=[]
 for name in ['istio-system',ING]:
  n=resource('Namespace',name);n['metadata']['labels']={'istio.io/dataplane-mode':'none','pod-security.kubernetes.io/enforce':'restricted','pod-security.kubernetes.io/enforce-version':'v'+version}
  if name==ING:n['metadata']['labels'].update({'istio.io/rev':REV,'portfolio.runtime/ingress':'true'})
  namespaces.append(n)
 stages['namespaces']=namespaces
 v=docs((ROOT/'kubernetes/platform/aws-load-balancer-controller/values.yaml').read_text())[0]
 need('ingressClass' not in v and 'watchNamespace' not in v,'project-derived controller scope is set by the renderer')
 v.update(clusterName=c['cluster_name'],vpcId=p['vpc_id'],fullnameOverride='aws-load-balancer-controller',nameOverride='aws-load-balancer-controller',resources=r['resources']['controller'],nodeSelector={'topology.kubernetes.io/zone':c['active_workload_az']},webhookTLS=SENTINELS,ingressClass=N['ingress_class'],watchNamespace=ING)
 raw=helm(tool,'controller',v,'kube-system',version);raw_counts['controller']=len(raw);controller=[]
 for obj in raw:
  obj=copy.deepcopy(obj);kind=obj['kind'];name=obj['metadata']['name']
  if kind=='CustomResourceDefinition' and name not in ['targetgroupbindings.elbv2.k8s.aws','ingressclassparams.elbv2.k8s.aws']:continue
  if kind=='Secret':
   need(name==r['webhook_tls_secret'] and obj['data']=={k:base64.b64encode(x.encode()).decode() for k,x in [('ca.crt',SENTINELS['caCert']),('tls.crt',SENTINELS['cert']),('tls.key',SENTINELS['key'])]},'no generated/supplied private material')
   continue
  need(kind not in ['Certificate','Issuer'],'no implicit cert-manager')
  if kind=='ClusterRole':obj['rules']=copy.deepcopy(READ_CLUSTER)
  if kind in ['MutatingWebhookConfiguration','ValidatingWebhookConfiguration']:
   obj['webhooks']=[w for w in obj['webhooks'] if any('targetgroupbindings' in rule['resources'] for rule in w['rules'])];need(obj['webhooks'],'TGB admission required')
   for w in obj['webhooks']:
    w['clientConfig']['caBundle']=r['webhook_ca_bundle'];w['failurePolicy']='Fail';w['namespaceSelector']={'matchLabels':{'portfolio.runtime/ingress':'true'}}
  controller.append(obj)
 sa=resource('ServiceAccount','aws-load-balancer-controller','kube-system',automountServiceAccountToken=True);sa['metadata']['annotations']={'eks.amazonaws.com/role-arn':c['role_arn']}
 controller.extend([sa,resource('Role',N['target_registration'],ING,api='rbac.authorization.k8s.io/v1',rules=read_namespace(N['gateway'])),resource('RoleBinding',N['target_registration'],ING,api='rbac.authorization.k8s.io/v1',subjects=[{'kind':'ServiceAccount','name':'aws-load-balancer-controller','namespace':'kube-system'}],roleRef={'apiGroup':'rbac.authorization.k8s.io','kind':'Role','name':N['target_registration']})])
 stages['controller']=controller
 global_values={'hub':'docker.io/istio','tag':'1.32.0','istioNamespace':'istio-system','enableReaderRBAC':False}
 base=helm(tool,'base',{'global':global_values,'defaultRevision':REV},'istio-system',version);raw_counts['base']=len(base)
 for obj in base:
  if obj['kind']=='ValidatingWebhookConfiguration':
   for webhook in obj['webhooks']:webhook['failurePolicy']='Fail'
 stages['base']=base
 values={'global':global_values,'revision':REV,'autoscaleEnabled':False,'replicaCount':1,'resources':r['resources']['istiod'],'nodeSelector':{'topology.kubernetes.io/zone':c['active_workload_az']},'meshConfig':{'trustDomain':r['trust_domain'],'accessLogFile':'','defaultConfig':{'holdApplicationUntilProxyStarts':True}},'seccompProfile':{'type':'RuntimeDefault'},'env':{'PILOT_ENABLE_GATEWAY_API':'false','PILOT_ENABLE_GATEWAY_API_DEPLOYMENT_CONTROLLER':'false'}}
 istiod=helm(tool,'istiod',values,'istio-system',version);raw_counts['istiod']=len(istiod)
 istiod=[o for o in istiod if '-gateway-controller-' not in o['metadata']['name']]
 for obj in istiod:
  if obj['kind'] in ['MutatingWebhookConfiguration','ValidatingWebhookConfiguration']:
   for webhook in obj['webhooks']:webhook['failurePolicy']='Fail'
  if obj['kind']=='Deployment':
   pod=obj['spec']['template']['spec'];vol=next(v for v in pod['volumes'] if v['name']=='cacerts');vol['secret']={'secretName':r['istio_ca_secret'],'optional':False,'items':[{'key':k,'path':k} for k in ['ca-cert.pem','ca-key.pem','root-cert.pem','cert-chain.pem']]}
   container=pod['containers'][0];container['livenessProbe']={'tcpSocket':{'port':15014},'initialDelaySeconds':30,'periodSeconds':10,'failureThreshold':6}
 stages['istiod']=istiod
 gv={'name':N['gateway'],'revision':REV,'global':global_values,'replicaCount':1,'autoscaling':{'enabled':False},'serviceAccount':{'create':False,'name':N['gateway']},'labels':{'istio':N['gateway'],'app':N['gateway'],'istio.io/dataplane-mode':'none'},'service':{'type':'ClusterIP','ports':[{'name':'https-backend','port':p['backend_target_port'],'protocol':'TCP','targetPort':p['backend_target_port']}]},'resources':r['resources']['gateway'],'nodeSelector':{'topology.kubernetes.io/zone':c['active_workload_az']},'readinessProbe':{'httpGet':{'path':'/healthz/ready','port':15021},'periodSeconds':5},'containerSecurityContext':{'runAsNonRoot':True,'runAsUser':1337,'allowPrivilegeEscalation':False,'readOnlyRootFilesystem':True,'capabilities':{'drop':['ALL']},'seccompProfile':{'type':'RuntimeDefault'}}}
 gateway=helm(tool,'gateway',gv,ING,version);raw_counts['gateway']=len(gateway)
 for obj in gateway:
  if obj['kind']=='Deployment':
   pod=obj['spec']['template']['spec'];container=pod['containers'][0];need(container['image']=='auto','reviewed gateway injection model');container['image']='docker.io/istio/proxyv2:1.32.0';container['ports'].extend([{'name':'https-backend','containerPort':p['backend_target_port'],'protocol':'TCP'},{'name':'status','containerPort':15021,'protocol':'TCP'}]);container['livenessProbe']={'tcpSocket':{'port':15021},'initialDelaySeconds':30,'periodSeconds':10,'failureThreshold':6}
 gateway.insert(0,resource('ServiceAccount',N['gateway'],ING,automountServiceAccountToken=False));stages['gateway']=gateway
 # Workload security source is preserved; bind its namespace PSS policy to requested Kube minor.
 security=fill(docs((ROOT/'kubernetes/platform/istio/application-security.yaml').read_text()),project)
 for obj in security:
  if obj['kind']=='Namespace':obj['metadata']['labels']['pod-security.kubernetes.io/enforce-version']='v'+version
 stages['mesh_security']=security
 def substitute(obj):
  values={'backend_hostname':r['backend_hostname'],'gateway_tls_secret':r['gateway_tls_secret'],'gateway_client_ca_secret':r['gateway_client_ca_secret'],'expected_client_spki':r['expected_client_spki'],'backend_target_port':p['backend_target_port'],'target_group_arn':p['target_group_arn'],'vpc_id':p['vpc_id']}
  if isinstance(obj,dict):return {k:substitute(x) for k,x in obj.items()}
  if isinstance(obj,list):return [substitute(x) for x in obj]
  if isinstance(obj,str) and obj.startswith('${'):need(obj.endswith('}') and obj[2:-1] in values,'unresolved template');return values[obj[2:-1]]
  return obj
 binding=substitute(fill(parse((ROOT/'kubernetes/platform/ingress/target-group-binding.template.json').read_text()),project));tls=substitute(fill(parse((ROOT/'kubernetes/platform/ingress/gateway.template.json').read_text()),project));tls['spec']['servers'][0]['tls']['caCertCredentialName']=r['gateway_client_ca_secret']
 # Exact-object admission guards apply before binding writer/TGB. Cluster admins can
 # change admission; effective isolation must still be verified on the actual cluster.
 policyname=N['target_registration']
 actor="request.userInfo.username in ['system:serviceaccount:"+ING+":"+N['binding_writer']+"','system:serviceaccount:kube-system:aws-load-balancer-controller']"
 checks=[actor,"object.metadata.namespace == '"+ING+"' && object.metadata.name == '"+N['gateway']+"'",'object.spec.targetGroupARN == '+json.dumps(p['target_group_arn']),"object.spec.targetType == 'ip'",'object.spec.vpcID == '+json.dumps(p['vpc_id']),"object.spec.serviceRef.name == '"+N['gateway']+"' && object.spec.serviceRef.port == "+str(p['backend_target_port']),"!has(object.spec.networking) && !has(object.spec.iamRoleArnToAssume) && !has(object.spec.nodeSelector)","!has(object.spec.multiClusterTargetGroup) || object.spec.multiClusterTargetGroup == false"]
 policy=resource('ValidatingAdmissionPolicy',policyname,api='admissionregistration.k8s.io/v1',spec={'failurePolicy':'Fail','matchConstraints':{'resourceRules':[{'apiGroups':['elbv2.k8s.aws'],'apiVersions':['v1beta1'],'operations':['CREATE','UPDATE'],'resources':['targetgroupbindings']}]},'validations':[{'expression':x,'message':'Only the reviewed Platform binding/identity is permitted.'} for x in checks]})
 pb=resource('ValidatingAdmissionPolicyBinding',policyname,api='admissionregistration.k8s.io/v1',spec={'policyName':policyname,'validationActions':['Deny']})
 noing=resource('ValidatingAdmissionPolicy',N['no_lb_service'],api='admissionregistration.k8s.io/v1',spec={'failurePolicy':'Fail','matchConstraints':{'namespaceSelector':{'matchLabels':{'portfolio.runtime/ingress':'true'}},'resourceRules':[{'apiGroups':['networking.k8s.io'],'apiVersions':['v1'],'operations':['CREATE','UPDATE'],'resources':['ingresses']},{'apiGroups':[''],'apiVersions':['v1'],'operations':['CREATE','UPDATE'],'resources':['services']}]},'validations':[{'expression':"request.kind.kind == 'Service' && object.spec.type == 'ClusterIP'",'message':'This namespace permits ClusterIP Services, not Ingress or external LB ownership.'}]})
 nb=resource('ValidatingAdmissionPolicyBinding',N['no_lb_service'],api='admissionregistration.k8s.io/v1',spec={'policyName':N['no_lb_service'],'validationActions':['Deny']})
 stages['admission']=[policy,pb,noing,nb]
 stages['binding_writer']=fill(docs((ROOT/'kubernetes/platform/ingress/binding-writer.yaml').read_text()),project)
 stages['ingress']=[tls,binding]
 # Namespace -> CRDs -> controller -> Istiod -> Gateway -> admission -> binding.
 order=['namespaces','base','controller','istiod','gateway','mesh_security','admission','binding_writer','ingress']
 result=[]
 for stage in order:result.extend(stages[stage])
 # Helm may emit unquoted numeric quantities; canonical JSON strings retain the
 # exact quantity and match the published Kubernetes OpenAPI representation.
 for obj in result:
  if obj['kind']=='Deployment':
   for container in obj['spec']['template']['spec']['containers']:
    for profile in container.get('resources',{}).values():
     if isinstance(profile,dict):
      for key,value in list(profile.items()):
       if type(value) in [int,float]:profile[key]=str(value)
 def omit_null(x):
  if isinstance(x,dict):return {k:omit_null(v) for k,v in x.items() if v is not None}
  if isinstance(x,list):return [omit_null(v) for v in x]
  return x
 result=omit_null(result)
 return result,{'status':'rendered','runtime_contract_version':3,'complete_v5':False,'actual_helm_renders':4,'helm_sha256':LOCK['helm']['binary_sha256'],'charts':{k:v['sha256'] for k,v in LOCK['charts'].items()},'input_sha256':sha(json.dumps(d,sort_keys=True,separators=(',',':')).encode()),'raw_chart_counts':raw_counts,'stages':{s:len(stages[s]) for s in order},'manifest_sha256':sha(json.dumps(result,sort_keys=True,separators=(',',':')).encode()),'resource_count':len(result)}
def main():
 a=argparse.ArgumentParser(description=__doc__);a.add_argument('--input',type=Path,required=True);a.add_argument('--helm',required=True);a.add_argument('--fixture',action='store_true');a.add_argument('--output',type=Path,required=True);args=a.parse_args()
 d=parse(args.input.read_text());result,evidence=render(d,args.helm,args.fixture)
 from validate import verify
 verify(result,d,args.fixture)
 args.output.write_text(json.dumps({'apiVersion':'v1','kind':'List','items':result},indent=2)+'\n');print(json.dumps(evidence,indent=2))
if __name__=='__main__':main()
