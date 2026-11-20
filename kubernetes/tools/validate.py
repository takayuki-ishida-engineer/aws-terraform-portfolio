"""Offline OpenAPI structural validation plus independent cross-resource security contracts."""
import copy,hashlib,io,json,re,tarfile
from common import ROOT,LOCK,docs,fill,need,names,parse,sha,fastjsonschema,metadata
_CACHE={}
def identity(o):return (o['apiVersion'],o['kind'],o['metadata'].get('namespace',''),o['metadata']['name'])
def normalize(schema):
 if isinstance(schema,list):return [normalize(x) for x in schema]
 if not isinstance(schema,dict):return schema
 out={k:normalize(v) for k,v in schema.items()}
 # Kubernetes OpenAPI IntOrString is an extension, not a plain JSON string.
 if out.get('format')=='int-or-string' or out.get('x-kubernetes-int-or-string'):
  out.pop('type',None);out.pop('format',None);out['anyOf']=[{'type':'integer','minimum':-2147483648,'maximum':2147483647},{'type':'string'}]
 return out

def structural(objects):
 src=LOCK['schema'];raw=(ROOT/src['path']).read_bytes();need(sha(raw)==src['sha256'],'Kubernetes schema integrity');db=json.loads(raw)
 crds={}
 for o in objects:
  if o['kind']=='CustomResourceDefinition':
   for v in o['spec']['versions']:
    if v['served']:crds[o['spec']['group']+'/'+v['name']+'/'+o['spec']['names']['kind']]=v['schema']['openAPIV3Schema']
 def local_refs(x):
  if isinstance(x,dict):
   for k,v in x.items():
    if k=='$ref':need(v.startswith('#/definitions/'),'no external schema fetch')
    else:local_refs(v)
  elif isinstance(x,list):
   for v in x:local_refs(v)
 for obj in objects:
  key=obj['apiVersion']+'/'+obj['kind']
  if obj['kind']=='CustomResourceDefinition':
   pins=json.loads((ROOT/'kubernetes/tests/expected-crds.json').read_text());need(sha(json.dumps(obj,sort_keys=True,separators=(',',':')).encode())==pins[obj['metadata']['name']],'exact pinned CRD definition')
   need(obj['apiVersion']=='apiextensions.k8s.io/v1' and obj['spec']['scope'] in ['Cluster','Namespaced'] and obj['spec']['versions'],'CRD envelope')
   continue
  if key in db['kinds']:
   schema={'$schema':'http://json-schema.org/draft-04/schema#','$ref':'#/definitions/'+db['kinds'][key],'definitions':db['definitions']}
  else:need(key in crds,'unsupported API/kind:'+key);schema=crds[key]
  # Published OpenAPI schemas have custom Kubernetes annotations; CEL, admission
  # execution and live API discovery remain external, not simulated by this validator.
  schema=normalize(schema);local_refs(schema);digest=sha(json.dumps(schema,sort_keys=True).encode())
  if digest not in _CACHE:_CACHE[digest]=fastjsonschema.compile(schema,use_default=False,use_formats=False)
  _CACHE[digest](copy.deepcopy(obj))
 return len(objects)

# Finding F18, written independently of the renderer: the image lock is re-proved from
# the raw upstream manifests, and every image reference in the bundle must be one of
# the three private ECR references pinned by digest. This is offline bundle validation,
# not Kubernetes admission: nothing here stops a different Pod on a real cluster.
LOCKED_IMAGES={'istio-pilot':('docker.io/istio/pilot','istiod'),'istio-proxy':('docker.io/istio/proxyv2','istiod'),'lbc':('public.ecr.aws/eks/aws-load-balancer-controller','controller')}
PUBLIC_REFERENCE=re.compile(r'(?<![A-Za-z0-9.-])(docker\.io|index\.docker\.io|registry-1\.docker\.io|quay\.io|gcr\.io|k8s\.gcr\.io|ghcr\.io|registry\.k8s\.io|public\.ecr\.aws|registry\.istio\.io|mcr\.microsoft\.com|registry\.gitlab\.com|cgr\.dev)(?![A-Za-z0-9-])|busybox')
def verify_image_lock(lock=None,read=None):
 lock=json.loads((ROOT/'kubernetes/images.lock.json').read_text()) if lock is None else lock
 read=read or (lambda path:(ROOT/path).read_bytes())
 need(isinstance(lock,dict) and sorted(lock)==['description','images','lock_version','registry','required_platform'] and lock['lock_version']==1,'image lock version')
 need(lock['required_platform']=='linux/amd64' and lock['registry']=={'region':'ca-central-1','host':'${account_id}.dkr.ecr.ca-central-1.amazonaws.com','repository':'${project}-dev-ecr-${purpose}','reference':'digest'},'image lock registry contract')
 need(isinstance(lock['images'],list) and sorted(i.get('purpose') for i in lock['images'] if isinstance(i,dict))==sorted(LOCKED_IMAGES),'exactly the reviewed images, each once')
 digests={}
 for item in lock['images']:
  source,chart=LOCKED_IMAGES[item['purpose']]
  need(sorted(item)==['digest','kind','manifest_file','media_type','observed','platforms','purpose','source','tag'],'image lock fields')
  need(item['source']==source and item['tag']==LOCK['charts'][chart]['app_version'],'upstream source and tag equal the pinned chart')
  need(item['manifest_file']=='kubernetes/image-manifests/'+item['purpose']+'.index.json','raw manifest path')
  raw=read(item['manifest_file']);need(re.fullmatch(r'sha256:[0-9a-f]{64}',item['digest']) and 'sha256:'+hashlib.sha256(raw).hexdigest()==item['digest'],'raw manifest bytes prove the pinned digest')
  index=parse(raw.decode())
  need(item['kind']=='index' and index.get('schemaVersion')==2 and index.get('mediaType')==item['media_type'] in ('application/vnd.docker.distribution.manifest.list.v2+json','application/vnd.oci.image.index.v1+json'),'multi-platform index; single-platform or unknown manifests are refused')
  need(sorted(index)==['manifests','mediaType','schemaVersion'] and isinstance(index['manifests'],list) and index['manifests'],'index structure')
  found={}
  for child in index['manifests']:
   need(child.get('mediaType') in ('application/vnd.docker.distribution.manifest.v2+json','application/vnd.oci.image.manifest.v1+json') and re.fullmatch(r'sha256:[0-9a-f]{64}',str(child.get('digest'))),'supported child manifest')
   platform=child.get('platform',{});key='/'.join([platform.get('os',''),platform.get('architecture','')]+([platform['variant']] if platform.get('variant') else []))
   need(key not in found,'duplicate platform');found[key]={'digest':child['digest'],'media_type':child['mediaType']}
  need(item['platforms']==found and 'linux/amd64' in found,'recorded platforms and linux/amd64 child digest equal the raw manifest')
  need(sorted(item['observed'])==['at','endpoint','method'] and item['observed']['endpoint']==source.split('/')[0].replace('docker.io','registry-1.docker.io'),'observation provenance')
  digests[item['purpose']]=item['digest']
 return digests
def chart_file(chart,name):
 path=ROOT/LOCK['charts'][chart]['path'];data=path.read_bytes();need(sha(data)==LOCK['charts'][chart]['sha256'],'chart integrity:'+chart)
 with tarfile.open(fileobj=io.BytesIO(data)) as archive:return archive.extractfile(name).read().decode()
def images(objects,d,lock=None,read=None):
 digests=verify_image_lock(lock,read);project=d['runtime']['project'];REV=names(project)['revision'];GW=names(project)['gateway']
 host=d['controller_identity']['scope']['account_id']+'.dkr.ecr.ca-central-1.amazonaws.com'
 refs={k:host+'/'+project+'-dev-ecr-'+k+'@'+v for k,v in digests.items()}
 found=[]
 def walk(x,owner):
  if isinstance(x,dict):
   for k,v in x.items():
    if k=='image':need(isinstance(v,str),'image reference type');found.append((owner,v))
    else:walk(v,owner)
  elif isinstance(x,list):
   for v in x:walk(v,owner)
 # CRD schemas define an 'image' property; they are definitions, not references.
 for o in objects:
  if o['kind']!='CustomResourceDefinition':walk(o,(o['kind'],o['metadata']['name']))
 expected=[(('Deployment','aws-load-balancer-controller'),refs['lbc']),(('Deployment','istiod-'+REV),refs['istio-pilot']),(('Deployment',GW),refs['istio-proxy'])]
 need(sorted(found)==sorted(expected),'every image is the approved private ECR reference pinned by digest, on its own workload; no other image')
 injector=next(o for o in objects if o['kind']=='ConfigMap' and o['metadata']['name']=='istio-sidecar-injector-'+REV)['data']
 need(sorted(injector)==['config','values'],'injector ConfigMap keys')
 g=json.loads(injector['values'])['global']
 need(g['hub']==host and g['tag']==LOCK['charts']['istiod']['app_version'] and g['variant']=='' and g['proxy']['image']==refs['istio-proxy'] and g['proxy_init']['image']==refs['istio-proxy'],'injected proxy and init images are the pinned private reference')
 config=docs(injector['config'])[0]
 need(sorted(config)==['alwaysInjectSelector','defaultTemplates','injectedAnnotations','neverInjectSelector','policy','template','templates'] and config['defaultTemplates']==['sidecar'] and config['policy']=='enabled','default injection contract')
 need(sorted(config['templates'])==['gateway','sidecar'],'only the default sidecar and gateway injection templates')
 for key,name in [('sidecar','istiod/files/injection-template.yaml'),('gateway','istiod/files/gateway-injection-template.yaml')]:
  need(config['templates'][key]==chart_file('istiod',name).strip()+'\n','unchanged pinned chart injection template:'+key)
 for key in ['original-values','merged-values']:
  values=json.loads(next(o for o in objects if o['kind']=='ConfigMap' and o['metadata']['name']=='values-'+REV)['data'][key])
  need(values['image']==refs['istio-pilot'] and values['global']['hub']==host and values['global']['proxy']['image']==refs['istio-proxy'] and values['global']['proxy_init']['image']==refs['istio-proxy'],'recorded Istio values use the pinned private references:'+key)
 need(not PUBLIC_REFERENCE.search(json.dumps(objects)),'no public registry reference anywhere in the bundle')
 return refs

def application_network_policy(objects,project):
 # Policies are additive: validating only the named deny policy would overlook
 # a second policy that grants traffic. No other policy is approved in NP-1.
 N=names(project);policies=[o for o in objects if o['kind']=='NetworkPolicy']
 need(len(policies)==1,'NP-1 permits exactly one NetworkPolicy; no additive allow policy')
 policy=policies[0]
 need(identity(policy)==('networking.k8s.io/v1','NetworkPolicy',N['app_namespace'],N['network_policy']),'application NetworkPolicy identity')
 need(policy['spec']=={'podSelector':{},'policyTypes':['Ingress','Egress'],'ingress':[],'egress':[]},'all application Pods: explicit ingress/egress default deny, no exceptions')
 namespace=next(o for o in objects if o['kind']=='Namespace' and o['metadata']['name']==N['app_namespace'])
 need(objects.index(namespace)<objects.index(policy),'application namespace before NetworkPolicy')

def verify(objects,d,fixture=False):
 metadata(d,fixture);need(isinstance(objects,list),'resource list');rows={}
 for o in objects:
  need(isinstance(o,dict) and all(k in o for k in ['apiVersion','kind','metadata']),'resource envelope');i=identity(o);need(i not in rows,'duplicate object');rows[i]=o
 project=d['runtime']['project'];N=names(project);REV=N['revision'];ING=N['ingress_namespace'];GW=N['gateway'];APP=N['app_namespace']
 application_network_policy(objects,project)
 # The inventory holds ${project} tokens for the names the project creates (F11).
 expected=fill(json.loads((ROOT/'kubernetes/tests/expected-inventory.json').read_text()),project);need(set(rows)=={tuple(x) for x in expected},'complete exact ownership inventory')
 structural(objects)
 refs=images(objects,d)
 def obj(kind,name,ns=''):return next(o for o in objects if o['kind']==kind and o['metadata']['name']==name and o['metadata'].get('namespace','')==ns)
 c=d['controller_identity'];p=d['private_ingress'];r=d['runtime']
 for o in objects:
  need(o['kind'] not in ['Secret','Certificate','Issuer','Ingress','VirtualService','HorizontalPodAutoscaler'],'no Secret/new ingress/app/implicit autoscaling')
  if o['kind'] in ['MutatingWebhookConfiguration','ValidatingWebhookConfiguration']:
   need(all(w['failurePolicy']=='Fail' for w in o['webhooks']),'all runtime webhooks fail closed; startup/readiness barrier required')
  if o['kind']=='Service':need(o['spec'].get('type','ClusterIP')=='ClusterIP' and not o['spec'].get('externalIPs'),'private ClusterIP only')
  if o['kind']=='Deployment':
   spec=o['spec'];pod=spec['template']['spec'];labels=spec['template']['metadata']['labels'];need(spec['replicas']==1 and all(labels.get(k)==v for k,v in spec['selector']['matchLabels'].items()),'reviewed DEV replicas/selectors')
   need(pod['nodeSelector']=={'topology.kubernetes.io/zone':c['active_workload_az']} and not any(pod.get(k) for k in ['hostNetwork','hostPID','hostIPC','initContainers']) and len(pod['containers'])==1,'one active AZ/private pod network')
   for co in pod['containers']:
    need(co['securityContext'].get('runAsNonRoot') is True and co['securityContext'].get('allowPrivilegeEscalation') is False and co['securityContext'].get('readOnlyRootFilesystem') is True,'non-root pod security')
    sc=co['securityContext'];need(not sc.get('privileged') and sc.get('capabilities')=={'drop':['ALL']} and sc.get('seccompProfile',pod.get('securityContext',{}).get('seccompProfile'))=={'type':'RuntimeDefault'},'restricted capabilities/seccomp')
    need('readinessProbe' in co and 'livenessProbe' in co,'explicit probes')
 controller=obj('Deployment','aws-load-balancer-controller','kube-system');cs=controller['spec']['template']['spec'];co=cs['containers'][0]
 need(cs['serviceAccountName']=='aws-load-balancer-controller' and co['image']==refs['lbc'] and co['resources']==r['resources']['controller'],'controller identity/image/resources')
 sa=obj('ServiceAccount','aws-load-balancer-controller','kube-system');need(sa['metadata']['annotations']=={'eks.amazonaws.com/role-arn':c['role_arn']},'IRSA role')
 flags={}
 for arg in co['args']:
  k,sep,v=arg.partition('=');need(sep and k not in flags,'unique explicit controller flag');flags[k]=v
 for k,v in {'--cluster-name':c['cluster_name'],'--aws-region':'ca-central-1','--aws-vpc-id':p['vpc_id'],'--watch-namespace':ING,'--ingress-class':N['ingress_class'],'--disable-ingress-class-annotation':'true','--enable-backend-security-group':'false','--enable-manage-backend-security-group-rules':'false','--enable-pod-readiness-gate-inject':'false','--enable-shield':'false','--enable-waf':'false','--enable-wafv2':'false'}.items():need(flags[k]==v,'controller scope/ownership:'+k)
 gates=dict(x.split('=') for x in flags['--feature-gates'].split(','));need(set(gates)=={'ALBGatewayAPI','ALBTargetControlAgent','EnableCertificateManagement','EnableRGTAPI','EnableServiceController','EndpointsFailOpen','GatewayListenerSet','GlobalAcceleratorController','NLBGatewayAPI'} and set(gates.values())=={'false'},'non-TGB controller features disabled')
 need(cs['volumes']==[{'name':'cert','secret':{'defaultMode':420,'secretName':r['webhook_tls_secret']}}],'external webhook Secret')
 for kind in ['MutatingWebhookConfiguration','ValidatingWebhookConfiguration']:
  for w in obj(kind,'aws-load-balancer-controller-webhook')['webhooks']:
   need(w['failurePolicy']=='Fail' and w['clientConfig']['caBundle']==r['webhook_ca_bundle'] and w['clientConfig']['service']['namespace']=='kube-system','webhook trust/failure')
   need(w['namespaceSelector']=={'matchLabels':{'portfolio.runtime/ingress':'true'}} and all(x['resources']==['targetgroupbindings'] for x in w['rules']),'only scoped TGB webhooks')
 # Binding identity is as important as the role's contents: a changed roleRef
 # must not silently select cluster-admin or a pre-existing unrestricted role.
 bindings=[('ClusterRoleBinding','aws-load-balancer-controller-rolebinding','','ClusterRole','aws-load-balancer-controller-role','kube-system','aws-load-balancer-controller'),('RoleBinding','aws-load-balancer-controller-leader-election-rolebinding','kube-system','Role','aws-load-balancer-controller-leader-election-role','kube-system','aws-load-balancer-controller'),('ClusterRoleBinding','istiod-clusterrole-'+REV+'-istio-system','','ClusterRole','istiod-clusterrole-'+REV+'-istio-system','istio-system','istiod-'+REV),('RoleBinding','istiod-'+REV,'istio-system','Role','istiod-'+REV,'istio-system','istiod-'+REV),('RoleBinding',GW,ING,'Role',GW,ING,GW)]
 for kind,name,ns,rkind,rname,sns,sname in bindings:
  b=obj(kind,name,ns);need(b['roleRef']=={'apiGroup':'rbac.authorization.k8s.io','kind':rkind,'name':rname} and len(b['subjects'])==1,'exact pinned runtime role binding')
  subject=b['subjects'][0];need(subject['kind']=='ServiceAccount' and subject['name']==sname and subject.get('namespace',ns)==sns,'exact runtime binding subject')
 for o in objects:
  if o['kind'] in ['Role','ClusterRole']:
   for rule in o['rules']:
    if 'elbv2.k8s.aws' in rule['apiGroups'] or '*' in rule['apiGroups']:
     need('*' not in rule['resources'] and ('targetgroupbindings' not in rule['resources'] or o['kind']=='Role' and o['metadata']['namespace']==ING and o['metadata']['name'] in [N['binding_writer'],N['target_registration']]),'single scoped TGB writer boundary')
 for rule in obj('ClusterRole','aws-load-balancer-controller-role')['rules']:need(set(rule['verbs'])<={'get','list','watch'} and not {'secrets','targetgroupbindings'}&set(rule['resources']),'cluster-wide metadata read only')
 role=obj('Role',N['target_registration'],ING)
 for rule in role['rules']:
  need('*' not in rule['verbs'] and '*' not in rule['resources'],'no wildcard controller RBAC')
  if set(rule['verbs'])&{'create','delete','patch','update'}:
   if any(x.startswith('targetgroupbindings') for x in rule['resources']):need(set(rule['verbs'])<={'patch','update'} and rule.get('resourceNames')==[GW],'exact TGB update rights')
   else:need(set(rule['resources'])<={'events','pods/status'},'no service/ingress/LB writer')
 writer=obj('Role',N['binding_writer'],ING);need(writer['rules']==[{'apiGroups':['elbv2.k8s.aws'],'resources':['targetgroupbindings'],'verbs':['create']},{'apiGroups':['elbv2.k8s.aws'],'resources':['targetgroupbindings'],'resourceNames':[GW],'verbs':['get','update','patch','delete']}],'binding writer bounds')
 for name,ns,sa_ns,sa_name,role_name in [(N['binding_writer'],ING,ING,N['binding_writer'],N['binding_writer']),(N['target_registration'],ING,'kube-system','aws-load-balancer-controller',N['target_registration'])]:
  b=obj('RoleBinding',name,ns);need(b['subjects']==[{'kind':'ServiceAccount','name':sa_name,'namespace':sa_ns}] and b['roleRef']=={'apiGroup':'rbac.authorization.k8s.io','kind':'Role','name':role_name},'binding actor')
 policy=obj('ValidatingAdmissionPolicy',N['target_registration'])['spec'];need(policy['failurePolicy']=='Fail' and policy['matchConstraints']=={'resourceRules':[{'apiGroups':['elbv2.k8s.aws'],'apiVersions':['v1beta1'],'operations':['CREATE','UPDATE'],'resources':['targetgroupbindings']}]},'all TGB admissions guarded')
 expr=[x['expression'] for x in policy['validations']]
 required=["request.userInfo.username in ['system:serviceaccount:"+ING+":"+N['binding_writer']+"','system:serviceaccount:kube-system:aws-load-balancer-controller']","object.metadata.namespace == '"+ING+"' && object.metadata.name == '"+GW+"'",'object.spec.targetGroupARN == '+json.dumps(p['target_group_arn']),"object.spec.targetType == 'ip'",'object.spec.vpcID == '+json.dumps(p['vpc_id']),"object.spec.serviceRef.name == '"+GW+"' && object.spec.serviceRef.port == "+str(p['backend_target_port']),"!has(object.spec.networking) && !has(object.spec.iamRoleArnToAssume) && !has(object.spec.nodeSelector)","!has(object.spec.multiClusterTargetGroup) || object.spec.multiClusterTargetGroup == false"]
 need(expr==required,'exact reviewed CEL binding boundary')
 for name in [N['target_registration'],N['no_lb_service']]:
  binding=obj('ValidatingAdmissionPolicyBinding',name)['spec'];need(binding=={'policyName':name,'validationActions':['Deny']},'admission enforcement binding')
 noing=obj('ValidatingAdmissionPolicy',N['no_lb_service'])['spec'];need(noing['matchConstraints']=={'namespaceSelector':{'matchLabels':{'portfolio.runtime/ingress':'true'}},'resourceRules':[{'apiGroups':['networking.k8s.io'],'apiVersions':['v1'],'operations':['CREATE','UPDATE'],'resources':['ingresses']},{'apiGroups':[''],'apiVersions':['v1'],'operations':['CREATE','UPDATE'],'resources':['services']}]},'namespace LB guard cannot be bypassed by changed match constraints');need(noing['failurePolicy']=='Fail' and noing['validations']==[{'expression':"request.kind.kind == 'Service' && object.spec.type == 'ClusterIP'",'message':'This namespace permits ClusterIP Services, not Ingress or external LB ownership.'}],'deny duplicate LB paths')
 tgb=obj('TargetGroupBinding',GW,ING);need(tgb['apiVersion']=='elbv2.k8s.aws/v1beta1' and tgb['spec']=={'targetGroupARN':p['target_group_arn'],'targetType':'ip','vpcID':p['vpc_id'],'serviceRef':{'name':GW,'port':p['backend_target_port']},'multiClusterTargetGroup':False},'actual owned TGB no SG networking/assumeRole')
 dep=obj('Deployment',GW,ING);pod=dep['spec']['template'];pc=pod['spec']['containers'][0];svc=obj('Service',GW,ING)['spec']
 need(pod['spec']['serviceAccountName']==GW and pc['image']==refs['istio-proxy'],'gateway identity/image')
 need(pod['metadata']['labels']['istio.io/rev']==REV and pod['metadata']['labels']['sidecar.istio.io/inject']=='true' and pod['metadata']['annotations']['inject.istio.io/templates']=='gateway','pinned gateway injection template')
 need(svc['type']=='ClusterIP' and all(pod['metadata']['labels'].get(k)==v for k,v in svc['selector'].items()) and svc['ports']==[{'name':'https-backend','port':p['backend_target_port'],'protocol':'TCP','targetPort':p['backend_target_port']}],'Service selector/backend port/Pod target port')
 need(pc['ports']==[{'containerPort':15090,'protocol':'TCP','name':'http-envoy-prom'},{'name':'https-backend','containerPort':p['backend_target_port'],'protocol':'TCP'},{'name':'status','containerPort':15021,'protocol':'TCP'}] and pc['resources']==r['resources']['gateway'],'exact Pod ports/resources; no duplicate backend or probe binding')
 need(pc['securityContext']['runAsUser']==1337,'Gateway non-root UID1337')
 need(pc['readinessProbe']=={'httpGet':{'path':'/healthz/ready','port':15021},'periodSeconds':5} and pc['livenessProbe']=={'tcpSocket':{'port':15021},'initialDelaySeconds':30,'periodSeconds':10,'failureThreshold':6},'unchanged Gateway probe port15021')
 gw=obj('Gateway',N['backend'],ING)['spec'];need(gw['selector']=={'istio':GW} and len(gw['servers'])==1,'Gateway owner/one TLS listener')
 server=gw['servers'][0];need(server['port']=={'number':p['backend_target_port'],'name':'https-backend','protocol':'HTTPS'} and server['hosts']==[r['backend_hostname']],'exact backend hostname/TLS listener')
 need(server['tls']=={'mode':'MUTUAL','credentialName':r['gateway_tls_secret'],'minProtocolVersion':'TLSV1_2','verifyCertificateSpki':r['expected_client_spki'],'caCertCredentialName':r['gateway_client_ca_secret']},'MUTUAL explicit server credential/client CA/identity; no fallback')
 istio=obj('Deployment','istiod-'+REV,'istio-system')['spec']['template']['spec'];ic=istio['containers'][0]
 need(ic['image']==refs['istio-pilot'] and ic['resources']==r['resources']['istiod'] and istio['serviceAccountName']=='istiod-'+REV,'pinned Istiod/SA/resources')
 ca=next(v['secret'] for v in istio['volumes'] if v['name']=='cacerts');need(ca=={'secretName':r['istio_ca_secret'],'optional':False,'items':[{'key':k,'path':k} for k in ['ca-cert.pem','ca-key.pem','root-cert.pem','cert-chain.pem']]},'no unreviewed CA bootstrap fallback')
 env={v['name']:v.get('value') for v in ic['env']};need(env['PILOT_ENABLE_GATEWAY_API']=='false' and env['PILOT_ENABLE_GATEWAY_API_DEPLOYMENT_CONTROLLER']=='false','no extra gateway deployment controller')
 mesh=obj('ConfigMap','istio-'+REV,'istio-system')['data']['mesh']
 need(docs(mesh)[0]['trustDomain']==r['trust_domain'],'explicit mesh trust domain')
 app=obj('Namespace',APP)['metadata']['labels'];need(app['istio.io/rev']==REV and app['pod-security.kubernetes.io/enforce']=='restricted','sidecar injection/PSS')
 need(obj('PeerAuthentication',N['peer_authentication'],APP)['spec']=={'mtls':{'mode':'STRICT'}},'STRICT mesh')
 need(obj('AuthorizationPolicy',N['authorization_policy'],APP)['spec']=={'action':'ALLOW','rules':[]},'namespace deny-by-default; no broad allow')
 need(obj('Namespace',ING)['metadata']['labels']['portfolio.runtime/ingress']=='true','guarded ingress namespace')
 need(obj('ServiceAccount',N['app_service_account'],APP)['automountServiceAccountToken'] is False,'application ServiceAccount without token')
 return len(objects)
