"""Fail-closed independent actual mock-plan, source and evidence checks."""
import argparse,copy,json,re,sys
from pathlib import Path
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
REPO=HERE.parents[3]
def need(ok,label):
    if not ok: raise ValueError(label)
def pairs(rows):
    result={}
    for k,v in rows:
        need(k not in result,'duplicate JSON key');result[k]=v
    return result
def parse(s):
    return json.loads(s,object_pairs_hook=pairs,parse_constant=lambda x:(_ for _ in ()).throw(ValueError('nonfinite JSON')))
def verify_plan(p,root=False):
    prefix='module.api_gateway_rest.' if root else ''
    expected={prefix+'aws_api_gateway_rest_api.this',prefix+'aws_api_gateway_authorizer.this'}
    if root:
        expected|={'module.cognito_auth.aws_cognito_'+t+'.this' for t in ['user_pool','user_pool_domain','resource_server','user_pool_client','managed_login_branding']}
    rows=p['resource_changes'];need(len(rows)==len(expected) and {r['address'] for r in rows}==expected,'exact resource inventory')
    by={r['address']:r for r in rows}
    a=by[prefix+'aws_api_gateway_rest_api.this'];z=by[prefix+'aws_api_gateway_authorizer.this']
    def unknown(x):
        return any(unknown(v) for v in x.values()) if isinstance(x,dict) else any(unknown(v) for v in x) if isinstance(x,list) else x is True
    for row,typ in [(a,'aws_api_gateway_rest_api'),(z,'aws_api_gateway_authorizer')]:
        need(row['type']==typ and row['name']=='this' and row['mode']=='managed' and row['provider_name']=='registry.terraform.io/hashicorp/aws' and row.get('module_address','')==prefix.rstrip('.') and 'index' not in row,'resource identity')
        need(row['change']['actions']==['create'] and row['change']['before'] is None,'non-destructive creation inventory')
        need(not any(unknown(row['change']['after_unknown'].get(k,False)) for k in ['id','rest_api_id','provider_arns','type','disable_execute_api_endpoint']),'known critical evidence')
    api=a['change']['after'];auth=z['change']['after']
    need(api['disable_execute_api_endpoint'] is True and api['endpoint_configuration'][0]['types']==['REGIONAL'],'regional disabled endpoint')
    need(auth['type']=='COGNITO_USER_POOLS' and auth['rest_api_id']==api['id'] and auth['identity_source']=='method.request.header.Authorization','authorizer binding')
    out=p['output_changes'];need(set(out)==({'authentication','rest_core'} if root else {'rest_core'}),'output inventory')
    o=out['rest_core'];need(o['after_unknown'] is False and o['after_sensitive'] is False,'known public output')
    value=o['after'];scope=value['scope'];need(value['interface_version']==1 and scope==dict(environment='dev',partition='aws',region='ca-central-1',account_id='000000000000'),'output scope')
    arn='arn:aws:cognito-idp:ca-central-1:000000000000:userpool/ca-central-1_TestPool'
    if root:
        pool=by['module.cognito_auth.aws_cognito_user_pool.this']['change']['after'];arn=pool['arn']
        need(out['authentication']['after']['user_pool_arn']==arn,'Cognito output provenance')
        need(value['approved_custom_scopes']==out['authentication']['after']['approved_custom_scopes'],'scope provenance')
    need(auth['provider_arns']==[arn] and value['user_pool_arn']==arn,'exact ARN provenance')
    need(value==dict(interface_version=1,scope=scope,rest_api_id=api['id'],authorizer_id=auth['id'],user_pool_arn=arn,approved_custom_scopes=value['approved_custom_scopes']),'resource-derived outputs')
    # Names and module-owned Name/service tags (docs/deployment-configuration.md sections 4 and 5);
    # project, env and managed come from the root provider default_tags, not resource tags.
    prefix_name=by['module.cognito_auth.aws_cognito_user_pool.this']['change']['after']['name'].removesuffix('-cognito') if root else 'test-dev'
    need(api['name']==prefix_name+'-apigw-rest' and auth['name']==api['name']+'-cognito','derived names')
    need(api['tags']=={'Name':api['name'],'service':'apigw'},'exact name and service tags')
    return a,z

def source_guard():
    main=(HERE.parent/'main.tf').read_text();out=(HERE.parent/'outputs.tf').read_text();root=(REPO/'infra/services/dev/ca-central-1/api/main.tf').read_text();variables=(HERE.parent/'variables.tf').read_text()
    for text,pattern in [(main,r'rest_api_id\s*=\s*aws_api_gateway_rest_api.this.id'),(main,r'provider_arns\s*=\s*\[var.authentication.user_pool_arn\]'),(root,r'authentication\s*=\s*module.cognito_auth.authentication'),(out,r'rest_api_id\s*=\s*aws_api_gateway_rest_api.this.id'),(out,r'authorizer_id\s*=\s*aws_api_gateway_authorizer.this.id')]:need(re.search(pattern,text),'source reference '+pattern)
    for token in ['interface_version == 1','scope == var.expected_scope','length(var.authentication.approved_custom_scopes) > 0','var.authentication.user_pool_arn ==']:
        need(token in variables,'required contract validation '+token)
    need(set(re.findall(r'resource "([^"]+)"',main))=={'aws_api_gateway_rest_api','aws_api_gateway_authorizer'},'source resource types')

def capture(events,root=False):
    expected=set(re.findall(r'run "([^"]+)"',((REPO/'infra/services/dev/ca-central-1/api/tests/auth.tftest.hcl') if root else HERE/'core.tftest.hcl').read_text()))
    need([e.get('terraform') for e in events if e['type']=='version']==['1.17.0'],'version')
    abstract=[e['test_abstract'] for e in events if e['type']=='test_abstract'];need(len(abstract)==1 and len(abstract[0])==1 and set(next(iter(abstract[0].values())))==expected,'manifest')
    summaries=[e['test_summary'] for e in events if e['type']=='test_summary'];need(summaries==[dict(status='pass',passed=len(expected),failed=0,errored=0,skipped=0)],'terminal summary')
    runs=[e['test_run'] for e in events if e['type']=='test_run' and e['test_run'].get('progress')=='complete'];need(len(runs)==len(expected) and {r['run'] for r in runs}==expected and all(r['status']=='pass' for r in runs),'complete runs')
    files=[e['test_file'] for e in events if e['type']=='test_file' and e['test_file'].get('progress')=='complete'];need(len(files)==1 and files[0]['status']=='pass','file')
    plans=[e for e in events if e['type']=='test_plan'];seen=set();positive=[]
    for e in plans:
        name=e['@testrun'];need(name in expected and name not in seen,'unique plan');seen.add(name)
        if not name.startswith('reject_'):verify_plan(e['test_plan'],root);positive.append(e['test_plan'])
    count=6 if root else 1
    need(len(positive)==count,'positive plans')
    return dict(native_tests=len(expected),positive_plans=count,negative_tests=len(expected)-count),positive

def main():
    p=argparse.ArgumentParser();p.add_argument('--events',type=Path,required=True);p.add_argument('--root',action='store_true');a=p.parse_args()
    events=[parse(l) for l in a.events.open()];source_guard();report,plans=capture(events,a.root)
    failures=[]
    def reject(fn,label):
        try:fn()
        except (ValueError,KeyError,TypeError,IndexError):failures.append(label);return
        raise ValueError('unsafe witness accepted '+label)
    base=plans[0];prefix='module.api_gateway_rest.' if a.root else ''
    mutations=[('aws_api_gateway_rest_api','disable_execute_api_endpoint',False),('aws_api_gateway_rest_api','endpoint_configuration',[{'types':['EDGE']}]),('aws_api_gateway_rest_api','endpoint_configuration',[{'types':['PRIVATE']}]),('aws_api_gateway_authorizer','type','REQUEST'),('aws_api_gateway_authorizer','rest_api_id','invented'),('aws_api_gateway_authorizer','provider_arns',['arn:aws:cognito-idp:ca-central-1:111111111111:userpool/ca-central-1_TestPool']),('aws_api_gateway_authorizer','identity_source','method.request.header.Other')]
    for typ,k,v in mutations:
        q=copy.deepcopy(base);next(r for r in q['resource_changes'] if r['address']==prefix+typ+'.this')['change']['after'][k]=v;reject(lambda:verify_plan(q,a.root),typ+k)
    for mode in ['missing','extra','duplicate','output','unknown','tags']:
        q=copy.deepcopy(base)
        if mode=='missing':q['resource_changes'].pop()
        if mode in ['extra','duplicate']:q['resource_changes'].append(copy.deepcopy(q['resource_changes'][0]))
        if mode=='output':q['output_changes']['rest_core']['after']['authorizer_id']='invented'
        if mode=='unknown':q['output_changes']['rest_core']['after_unknown']=True
        if mode=='tags':next(r for r in q['resource_changes'] if r['address']==prefix+'aws_api_gateway_rest_api.this')['change']['after']['tags']['service']='other'
        reject(lambda:verify_plan(q,a.root),mode)
    report['security_mutations']=len(failures);failures=[]
    for typ in ['version','test_summary','test_run','test_plan','test_file','test_abstract']:reject(lambda typ=typ:capture([e for e in events if e['type']!=typ],a.root),typ)
    reject(lambda:capture(events+[next(e for e in events if e['type']=='test_plan')],a.root),'duplicate plan')
    for s in ['{"a":1,"a":2}','{"a":NaN}']:reject(lambda s=s:parse(s),'invalid JSON')
    report['evidence_faults']=len(failures);report['status']='passed';print(json.dumps(report))
if __name__=='__main__':main()
