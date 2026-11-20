"""Pinned, credential-free rendering primitives. No deployment or cloud clients."""
import base64,hashlib,json,os,re,subprocess,sys,tempfile
from pathlib import Path
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[2]
LOCK=json.loads((ROOT/'kubernetes/dependencies.lock.json').read_text())
for lib in ['pyyaml','fastjsonschema']:
 for name,digest in LOCK[lib]['files'].items():
  if hashlib.sha256((ROOT/'kubernetes/vendor'/lib/name).read_bytes()).hexdigest()!=digest:raise ValueError('dependency integrity:'+name)
 sys.path.insert(0,str(ROOT/'kubernetes/vendor'/lib))
import yaml,fastjsonschema

def need(ok,label):
 if not ok:raise ValueError(label)
def unique(items):
 d={}
 for k,v in items:need(k not in d,'duplicate key:'+str(k));d[k]=v
 return d
def parse(text):return json.loads(text,object_pairs_hook=unique,parse_constant=lambda x:(_ for _ in ()).throw(ValueError('nonfinite JSON')))
class Safe(yaml.SafeLoader):pass
def mapping(loader,node,deep=False):
 loader.flatten_mapping(node);return unique((loader.construct_object(k,deep=deep),loader.construct_object(v,deep=deep)) for k,v in node.value)
Safe.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,mapping)
def docs(text):return [d for d in yaml.load_all(text,Loader=Safe) if d is not None]
def sha(data):return hashlib.sha256(data).hexdigest()
# Same rule as the DEV roots' project variable (finding F11: Kubernetes objects
# the project creates are named <project>-<purpose>; upstream-mandated names stay).
PROJECT=r'[a-z]([a-z0-9-]{0,8}[a-z0-9])?'
def names(project):
 need(isinstance(project,str) and re.fullmatch(PROJECT,project) and not re.search('aws|amazon|cognito',project),'project name')
 return {'revision':project+'-v1','ingress_namespace':project+'-ingress','gateway':project+'-gateway','backend':project+'-backend','target_registration':project+'-target-registration','no_lb_service':project+'-no-lb-service','binding_writer':project+'-binding-writer','app_namespace':project+'-app','app_service_account':project+'-application','peer_authentication':project+'-strict-mtls','authorization_policy':project+'-default-deny','network_policy':project+'-default-deny','ingress_class':project+'-disabled'}
def fill(obj,project):
 # Replace ${project} in reviewed source templates and the expected inventory.
 names(project)
 if isinstance(obj,dict):return {fill(k,project):fill(v,project) for k,v in obj.items()}
 if isinstance(obj,list):return [fill(v,project) for v in obj]
 if isinstance(obj,str):return obj.replace('${project}',project)
 return obj
def metadata(d,fixture=False):
 # Input interface 2 adds runtime.project (finding F11); interface 1 inputs are refused.
 need(set(d)=={'interface_version','fixture','controller_identity','private_ingress','runtime'} and d['interface_version']==2 and d['fixture'] is fixture,'manifest/fixture boundary')
 c=d['controller_identity'];p=d['private_ingress'];s=c['scope'];r=d['runtime']
 need(s==p['scope'] and set(s)=={'environment','partition','region','account_id'} and s['environment']=='dev' and s['partition']=='aws' and s['region']=='ca-central-1' and re.fullmatch('[0-9]{12}',s['account_id']),'scope')
 need(c['interface_version']==p['interface_version']==1 and c['namespace']=='kube-system' and c['service_account']=='aws-load-balancer-controller','identity interface')
 need(c['target_group_arn']==p['target_group_arn'] and re.fullmatch('arn:aws:elasticloadbalancing:ca-central-1:'+s['account_id']+r':targetgroup/[A-Za-z0-9-]+/[0-9a-f]{16}',p['target_group_arn']),'target scope')
 need(re.fullmatch('arn:aws:iam::'+s['account_id']+r':role/[a-z][a-z0-9-]*-lbc',c['role_arn']),'role scope')
 need(re.fullmatch(r'https://oidc[.]eks[.]ca-central-1[.]amazonaws[.]com/id/[A-Za-z0-9]+',c['oidc_issuer']) and c['oidc_provider_arn']=='arn:aws:iam::'+s['account_id']+':oidc-provider/'+c['oidc_issuer'].removeprefix('https://'),'OIDC')
 need(re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,39}',c['cluster_name']) and re.fullmatch(r'ca-central-1[a-z]',c['active_workload_az']),'cluster/AZ')
 need(c['kubernetes_version'] in ['1.33','1.34','1.35','1.36','1.37'],'Istio software matrix; live selection remains external')
 need(re.fullmatch(r'vpc-([0-9a-f]{8}|[0-9a-f]{17})',p['vpc_id']) and type(p['backend_target_port']) is int and 1024<=p['backend_target_port']<=65535 and not 15000<=p['backend_target_port']<=15090,'VPC/backend port: integer1024-65535, reserving Istio control/probe range15000-15090')
 need(set(r)=={'project','backend_hostname','gateway_tls_secret','gateway_client_ca_secret','expected_client_spki','trust_domain','webhook_tls_secret','webhook_ca_bundle','istio_ca_secret','resources'},'runtime fields')
 n=names(r['project'])
 need(c['cluster_name']==r['project']+'-dev-eks' and c['role_arn'].endswith(':role/'+r['project']+'-dev-role-lbc'),'project matches the platform cluster and controller role names')
 for field in ['backend_hostname','trust_domain']:
  need(len(r[field])<=253 and re.fullmatch(r'[a-z0-9]([a-z0-9.-]*[a-z0-9])?',r[field]) and '.' in r[field] and '*' not in r[field] and '..' not in r[field],'exact DNS:'+field)
 for field in ['gateway_tls_secret','gateway_client_ca_secret','istio_ca_secret','webhook_tls_secret']:need(re.fullmatch(r'[a-z0-9]([a-z0-9-]*[a-z0-9])?',r[field]),'Secret reference:'+field)
 need(r['gateway_client_ca_secret'].endswith('-cacert') and not r['gateway_tls_secret'].endswith('-cacert'),'CA-only SDS suffix must not be a leaf credential')
 need(all(r[f].startswith(r['project']+'-') for f in ['gateway_tls_secret','gateway_client_ca_secret']),'project-created gateway Secrets are named <project>-<purpose>')
 need(set(c)=={'interface_version','scope','role_arn','oidc_issuer','oidc_provider_arn','namespace','service_account','target_group_arn','cluster_name','kubernetes_version','active_workload_az'} and set(p)=={'interface_version','scope','target_group_arn','vpc_id','backend_target_port'},'minimal reference fields only')
 need(r['istio_ca_secret']=='cacerts' and r['webhook_tls_secret']=='aws-load-balancer-controller-tls' and r['gateway_tls_secret']!=r['gateway_client_ca_secret'],'external CA/credential separation')
 pins=r['expected_client_spki'];need(isinstance(pins,list) and 1<=len(pins)<=2 and len(set(pins))==len(pins) and all(len(base64.b64decode(x,validate=True))==32 for x in pins),'exact SPKI SHA256 pins')
 ca=base64.b64decode(r['webhook_ca_bundle'],validate=True);need(ca and b'PRIVATE KEY' not in ca,'public CA')
 if not fixture:need(ca.startswith(b'-----BEGIN CERTIFICATE-----') and ca.rstrip().endswith(b'-----END CERTIFICATE-----'),'reviewed external public CA')
 need(set(r['resources'])=={'controller','istiod','gateway'},'resource profiles')
 def cpu(x):need(re.fullmatch(r'[1-9][0-9]*m|[1-9][0-9]*',x),'cpu');return int(x[:-1]) if x.endswith('m') else int(x)*1000
 def mem(x):need(re.fullmatch(r'[1-9][0-9]*(Mi|Gi)',x),'memory');return int(x[:-2])*(1024 if x.endswith('Gi') else 1)
 for v in r['resources'].values():
  need(set(v)=={'requests','limits'} and all(set(x)=={'cpu','memory'} for x in v.values()),'resource keys')
  need(cpu(v['requests']['cpu'])<=cpu(v['limits']['cpu']) and mem(v['requests']['memory'])<=mem(v['limits']['memory']),'request <= limit')
 need('${' not in json.dumps(d) and 'PRIVATE KEY' not in json.dumps(d),'no unresolved references/secret material')
 return d

def helm(helm,key,values,ns,version):
 tool=LOCK['helm'];need(sha(Path(helm).read_bytes())==tool['binary_sha256'],'Helm binary integrity')
 v=subprocess.run([helm,'version','--template','{{.Version}}'],capture_output=True,text=True,check=True);need(v.stdout=='v'+tool['version'],'Helm version')
 chart=LOCK['charts'][key];path=ROOT/chart['path'];need(sha(path.read_bytes())==chart['sha256'],'chart integrity:'+key)
 env={k:v for k,v in os.environ.items() if not k.startswith(('AWS_','KUBE','HELM_'))};env.update(KUBECONFIG='/dev/null',HELM_PLUGINS='/nonexistent',HELM_CACHE_HOME='/tmp/portfolio-helm-cache')
 with tempfile.TemporaryDirectory(prefix='portfolio-render-') as tmp:
  vf=Path(tmp)/'values.json';vf.write_text(json.dumps(values))
  p=subprocess.run([helm,'template',key,str(path),'--namespace',ns,'--kube-version',version+'.0','--include-crds','-f',str(vf)],env=env,capture_output=True,text=True,check=True)
 return docs(p.stdout)
