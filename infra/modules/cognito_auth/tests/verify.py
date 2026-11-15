#!/usr/bin/env python3
"""Independent full mock-plan security/evidence verifier; no cloud clients."""
import argparse,copy,json,re,sys
from pathlib import Path
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
TYPES=['user_pool','user_pool_domain','resource_server','user_pool_client','managed_login_branding']
def need(x,label):
 if not x:raise ValueError(label)
def pairs(xs):
 d={}
 for k,v in xs:need(k not in d,'duplicate JSON');d[k]=v
 return d
def parse(t):return json.loads(t,object_pairs_hook=pairs,parse_constant=lambda x:(_ for _ in ()).throw(ValueError('nonfinite')))
def verify(p,v,root=False):
 if root:
  sys.path.insert(0,str(HERE.parents[1]/'api_gateway_rest/tests'))
  from check_rest_core import verify_plan
  verify_plan(p,True)
  p=copy.deepcopy(p)
  p['resource_changes']=[r for r in p['resource_changes'] if r['address'].startswith('module.cognito_auth.')]
  p['output_changes']={k:v for k,v in p['output_changes'].items() if k=='authentication'}
 prefix='module.cognito_auth.' if root else '';rows={}
 for r in p['resource_changes']:
  need(r['address'] not in rows,'duplicate owner');rows[r['address']]=r
 need(set(rows)=={prefix+'aws_cognito_'+t+'.this' for t in TYPES},'exact five owners')
 def get(t):return rows[prefix+'aws_cognito_'+t+'.this']['change']['after']
 def eq(t,k,x):
  row=rows[prefix+'aws_cognito_'+t+'.this'];need(row['change']['after_unknown'].get(k,False) in [False,{},[]],'unknown critical '+k);need(get(t)[k]==x,t+':'+k)
 for t in TYPES:
  row=rows[prefix+'aws_cognito_'+t+'.this'];need(row['type']=='aws_cognito_'+t and row['name']=='this' and row.get('module_address','')==prefix.rstrip('.') and 'index' not in row,'exact resource identity');need(row['mode']=='managed' and row['provider_name']=='registry.terraform.io/hashicorp/aws' and row['change']['actions']==['create'] and row['change']['before'] is None,'owner/provider/actions');eq(t,'region',v['expected_scope']['region'])
 pool=get('user_pool');client=get('user_pool_client');server=get('resource_server');domain=get('user_pool_domain');brand=get('managed_login_branding');scope=v['expected_scope']
 need(scope==dict(environment='dev',partition='aws',region='ca-central-1',account_id='000000000000'),'fixture scope')
 for k,x in dict(name=v['pool_name'],user_pool_tier=v['feature_plan'],deletion_protection='ACTIVE',username_attributes=['email'],auto_verified_attributes=[],mfa_configuration=v['mfa_configuration'],username_configuration=[{'case_sensitive':False}],software_token_mfa_configuration=[{'enabled':True}],sms_configuration=[],email_configuration=[],email_mfa_configuration=[],lambda_config=[],user_pool_add_ons=[]).items():eq('user_pool',k,x)
 need(pool['admin_create_user_config'][0]['allow_admin_create_user_only'] is True,'no self signup')
 need(pool['account_recovery_setting']==[{'recovery_mechanism':[{'name':'admin_only','priority':1}]}],'admin recovery')
 pw=pool['password_policy'][0];need(pw['minimum_length']==v['password_minimum_length'] and pw['temporary_password_validity_days']==1 and all(pw[k] is True for k in ['require_lowercase','require_uppercase','require_symbols','require_numbers']),'password protections')
 need(len(pool['schema'])==1 and all(pool['schema'][0][k]==x for k,x in dict(name='email',attribute_data_type='String',required=True,mutable=True).items()),'email identity schema')
 need(pool['arn']=='arn:aws:cognito-idp:ca-central-1:000000000000:userpool/'+pool['id'] and pool['endpoint']=='cognito-idp.ca-central-1.amazonaws.com/'+pool['id'],'pool identity')
 for t in TYPES[1:]:eq(t,'user_pool_id',pool['id'])
 eq('user_pool_domain','domain',v['domain_prefix']);eq('user_pool_domain','managed_login_version',2);eq('user_pool_domain','certificate_arn',None)
 eq('resource_server','identifier',v['resource_server_identifier']);need({x['scope_name']:x['scope_description'] for x in server['scope']}==v['scopes'],'actual scopes')
 for t,k in [('user_pool','id'),('user_pool','arn'),('user_pool','endpoint'),('user_pool_client','id'),('managed_login_branding','managed_login_branding_id')]:
  need(isinstance(get(t)[k],str) and get(t)[k],'nonempty identity');eq(t,k,get(t)[k])
 custom=sorted(server['identifier']+'/'+x for x in v['approved_scope_names'])
 for k,x in dict(name=v['pool_name']+'-browser',generate_secret=False,allowed_oauth_flows_user_pool_client=True,allowed_oauth_flows=['code'],allowed_oauth_scopes=sorted(['email','openid']+custom),explicit_auth_flows=['ALLOW_REFRESH_TOKEN_AUTH'],supported_identity_providers=['COGNITO'],enable_token_revocation=True,prevent_user_existence_errors='ENABLED',callback_urls=sorted(v['callback_urls']),logout_urls=sorted(v['logout_urls']),default_redirect_uri=v['default_redirect_uri'],access_token_validity=v['access_token_minutes'],id_token_validity=v['id_token_minutes'],refresh_token_validity=v['refresh_token_hours'],token_validity_units=[dict(access_token='minutes',id_token='minutes',refresh_token='hours')],read_attributes=['email','email_verified'],write_attributes=['name']).items():eq('user_pool_client',k,x)
 eq('managed_login_branding','client_id',client['id']);eq('managed_login_branding','use_cognito_provided_values',True);eq('managed_login_branding','asset',[]);eq('managed_login_branding','settings',None)
 out=dict(interface_version=1,scope=scope,user_pool_id=pool['id'],user_pool_arn=pool['arn'],app_client_id=client['id'],resource_server_identifier=server['identifier'],approved_custom_scopes=custom,domain_prefix=domain['domain'],issuer_url='https://'+pool['endpoint'],managed_login_branding_id=brand['managed_login_branding_id'])
 need(set(p['output_changes'])=={'authentication'},'output inventory');o=p['output_changes']['authentication'];need(o['after']==out and o['after_unknown'] is False and o['after_sensitive'] is False,'resource derived nonsecret outputs')
 return 5
def capture(events,root=False):
 cases=parse((HERE/'cases.json').read_text());positive=cases['positive'];negative=cases['negative'];expected=set(positive)|{'reject_'+k for k,c in negative.items() if not root or c['failure']!='expected_scope' or k=='scope_account_id'}
 need([e.get('terraform') for e in events if e['type']=='version']==['1.17.0'],'version evidence')
 abstracts=[e['test_abstract'] for e in events if e['type']=='test_abstract'];need(len(abstracts)==1 and len(abstracts[0])==1 and set(next(iter(abstracts[0].values())))==expected,'exact native manifest')
 files=[e['test_file'] for e in events if e['type']=='test_file' and e['test_file'].get('progress')=='complete'];need(len(files)==1 and files[0]['status']=='pass','file completion')
 summaries=[e['test_summary'] for e in events if e['type']=='test_summary'];need(summaries==[dict(status='pass',passed=len(expected),failed=0,errored=0,skipped=0)],'complete success summary')
 runs=[e for e in events if e['type']=='test_run' and e['test_run'].get('progress')=='complete'];need(len(runs)==len(expected) and {e['test_run']['run'] for e in runs}==expected and all(e['test_run'].get('status')=='pass' for e in runs),'complete passed runs')
 need(not any(e['type']=='diagnostic' and e.get('diagnostic',{}).get('severity')=='error' and e.get('@testrun') in positive for e in events),'no positive errors')
 plans=[e for e in events if e['type']=='test_plan'];seen=set();positive_plans=[]
 for e in plans:
  name=e.get('@testrun');need(name in expected and name not in seen,'unique expected plan');seen.add(name)
  if name in positive:verify(e['test_plan'],positive[name],root);positive_plans.append(e['test_plan'])
 need(set(positive)<=seen and len(positive_plans)==5,'complete positive captures')
 return dict(status='passed',native_tests=len(expected),positive_plans=5,negative_tests=len(expected)-5),positive_plans

def source_guard(text=None):
 if text is None:text='\n'.join(p.read_text() for p in HERE.parent.glob('*.tf'))
 need('aws_cognito_identity_provider' not in text and 'client_secret' not in text,'no federation secret writer')
 for pattern in [r'client_id\s*=\s*aws_cognito_user_pool_client.this.id',r'user_pool_id\s*=\s*aws_cognito_user_pool.this.id',r'depends_on\s*=\s*\[aws_cognito_user_pool_domain.this\]',r'depends_on\s*=\s*\[aws_cognito_resource_server.this\]',r'\$\{aws_cognito_resource_server.this.identifier\}']:
  need(re.search(pattern,text), 'actual reference/dependency '+pattern)
def main():
 a=argparse.ArgumentParser();a.add_argument('--events',type=Path,required=True);a.add_argument('--root',action='store_true');a.add_argument('--self-test',action='store_true');args=a.parse_args()
 events=[]
 for l in args.events.open():
  e=parse(l)
  if e['type']=='test_plan':e['test_plan'].pop('provider_schemas',None)
  events.append(e)
 source_guard();report,plans=capture(events,args.root)
 if args.self_test:
  rejected=[]
  def reject(fn,label):
   try:fn()
   except (ValueError,KeyError,TypeError,IndexError):rejected.append(label);return
   raise ValueError('unsafe mutation accepted '+label)
  v=parse((HERE/'cases.json').read_text())['positive']['standard'];base=plans[0];prefix='module.cognito_auth.' if args.root else ''
  mutations=[('user_pool_client','allowed_oauth_flows',['implicit']),('user_pool_client','allowed_oauth_flows',['client_credentials']),('user_pool_client','generate_secret',True),('user_pool_client','explicit_auth_flows',['ALLOW_USER_PASSWORD_AUTH']),('user_pool_client','explicit_auth_flows',['ALLOW_ADMIN_USER_PASSWORD_AUTH']),('user_pool_client','callback_urls',[]),('user_pool_client','callback_urls',['https://*.example.invalid']),('user_pool_client','allowed_oauth_scopes',['openid','admin']),('user_pool_client','enable_token_revocation',False),('user_pool_client','user_pool_id','other'),('user_pool_client','access_token_validity',1000),('user_pool_client','supported_identity_providers',['Google']),('managed_login_branding','client_id','other'),('managed_login_branding','use_cognito_provided_values',False),('resource_server','identifier','invented'),('user_pool_domain','managed_login_version',1),('user_pool','deletion_protection','INACTIVE'),('user_pool','mfa_configuration','OFF'),('user_pool','username_attributes',['phone_number']),('user_pool','region','us-east-1'),('user_pool','arn','arn:aws:cognito-idp:ca-central-1:111111111111:userpool/other'),('user_pool','admin_create_user_config',[{'allow_admin_create_user_only':False}]),('user_pool','password_policy',[{}])]
  for t,k,x in mutations:
   p=copy.deepcopy(base);next(r for r in p['resource_changes'] if r['address']==prefix+'aws_cognito_'+t+'.this')['change']['after'][k]=x;reject(lambda p=p:verify(p,v,args.root),t+':'+k)
  for label,fn in [('missing_branding',lambda p:p['resource_changes'].pop(0)),('duplicate_owner',lambda p:p['resource_changes'].append(copy.deepcopy(p['resource_changes'][0]))),('secret_output',lambda p:p['output_changes'].update(client_secret={})),('wrong_output',lambda p:p['output_changes']['authentication']['after'].update(app_client_id='invented')),('unknown_output',lambda p:p['output_changes']['authentication'].update(after_unknown=True)),('unknown_pool_id',lambda p:next(r for r in p['resource_changes'] if r['type']=='aws_cognito_user_pool')['change']['after_unknown'].update(id=True)),('false_resource_type',lambda p:p['resource_changes'][0].update(type='aws_cognito_identity_provider')),('sensitive_output',lambda p:p['output_changes']['authentication'].update(after_sensitive=True)),('unexpected_IdP',lambda p:p['resource_changes'].append(dict(p['resource_changes'][0],address='aws_cognito_identity_provider.forbidden')))]:
   p=copy.deepcopy(base);fn(p);reject(lambda p=p:verify(p,v,args.root),label)
  report['security_mutations']=len(rejected);rejected=[]
  for kind in ['version','test_summary','test_plan','test_run','test_file','test_abstract']:
   q=[e for e in events if e['type']!=kind];reject(lambda q=q:capture(q,args.root),'missing '+kind)
  e=next(e for e in events if e['type']=='test_plan');reject(lambda:capture(events+[e],args.root),'duplicate plan')
  q=copy.deepcopy(events);next(e for e in q if e['type']=='test_summary')['test_summary']['skipped']=1;reject(lambda:capture(q,args.root),'skipped evidence')
  reject(lambda:capture(events+[next(e for e in events if e['type']=='test_summary')],args.root),'duplicate summary')
  q=copy.deepcopy(events);next(e for e in q if e['type']=='version')['terraform']='wrong';reject(lambda:capture(q,args.root),'wrong version')
  for text in ['{broken','{"x":1,"x":2}','{"x":NaN}']:reject(lambda text=text:parse(text),'malformed JSON')
  report['evidence_faults']=len(rejected)
 print(json.dumps(report))
if __name__=='__main__':main()
