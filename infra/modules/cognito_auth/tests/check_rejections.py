#!/usr/bin/env python3
"""Unsafe source re-plans and missing Root inputs using mocked providers only."""
import argparse,json,os,re,shutil,subprocess,tempfile,sys
from pathlib import Path
sys.dont_write_bytecode=True
from verify import parse,verify,source_guard,need,HERE
REPO=HERE.parents[3];ROOT=REPO/'infra/services/dev/ca-central-1/api';MODULE=HERE.parent

def run(tf,path,env):
 p=subprocess.Popen([tf,'-chdir='+str(path),'test','-json','-verbose','-no-color'],env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True);events=[]
 for l in p.stdout:
  e=parse(l)
  if e['type']=='test_plan':e['test_plan'].pop('provider_schemas',None)
  events.append(e)
 err=p.stderr.read();code=p.wait();need(not err.strip(),'unexpected stderr');return code,events

def main():
 a=argparse.ArgumentParser();a.add_argument('--terraform',default='terraform');args=a.parse_args()
 env={k:v for k,v in os.environ.items() if not k.startswith(('AWS_','TF_VAR_','TF_CLI_ARGS'))};env.update(AWS_EC2_METADATA_DISABLED='true',AWS_SHARED_CREDENTIALS_FILE='/dev/null',AWS_CONFIG_FILE='/dev/null')
 header=(MODULE/'tests/auth.tftest.hcl').read_text().split('run "')[0];v=parse((HERE/'cases.json').read_text())['positive']['standard']
 def test(values):return header+'run "probe" {\n command=plan\n variables {\n'+'\n'.join(k+'='+json.dumps(x) for k,x in values.items())+'\n}\n}\n'
 # Whitespace-independent witnesses, each must produce a complete mocked plan.
 changes=[('implicit',r'(allowed_oauth_flows\s*=\s*)\["code"\]',r'\1["implicit"]'),('secret',r'(generate_secret\s*=\s*)false',r'\1true'),('password',r'(explicit_auth_flows\s*=\s*)\["ALLOW_REFRESH_TOKEN_AUTH"\]',r'\1["ALLOW_USER_PASSWORD_AUTH"]'),('revocation',r'(enable_token_revocation\s*=\s*)true',r'\1false'),('deletion',r'(deletion_protection\s*=\s*)"ACTIVE"',r'\1"INACTIVE"'),('branding_dependency',r'depends_on\s*=\s*\[aws_cognito_user_pool_domain.this\]',''),('scope_reference',r'\$\{aws_cognito_resource_server.this.identifier\}','invented'),('branding_owner',r'client_id\s*=\s*aws_cognito_user_pool_client.this.id','client_id = "invented"'),('signup',r'(allow_admin_create_user_only\s*=\s*)true',r'\1false'),('totp',r'(software_token_mfa_configuration\s*\{\s*enabled\s*=\s*)true',r'\1false')]
 results=[]
 with tempfile.TemporaryDirectory(prefix='cognito-security-',dir=os.environ.get('RUNNER_TEMP','/tmp')) as td:
  td=Path(td)
  for name,pattern,replacement in changes:
   d=td/name;d.mkdir();(d/'tests').mkdir()
   for f in MODULE.glob('*.tf'):shutil.copy2(f,d/f.name)
   shutil.copy2(ROOT/'.terraform.lock.hcl',d/'.terraform.lock.hcl');p=d/'main.tf';text,n=re.subn(pattern,replacement,p.read_text(),count=1);need(n==1,'mutation witness '+name);p.write_text(text);(d/'tests/probe.tftest.hcl').write_text(test(v))
   scopeenv=dict(env,TF_DATA_DIR=str(MODULE/'.terraform'));code,events=run(args.terraform,d,scopeenv);plans=[e['test_plan'] for e in events if e['type']=='test_plan'];need(code==0 and len(plans)==1,'complete actual mutant plan '+name)
   try:verify(plans[0],v);source_guard(text)
   except (ValueError,KeyError,TypeError):results.append(name)
   else:raise ValueError('unsafe source accepted '+name)
  d=td/'root';d.mkdir();(d/'tests').mkdir()
  for f in ROOT.glob('*.tf'):shutil.copy2(f,d/f.name)
  shutil.copy2(ROOT/'.terraform.lock.hcl',d/'.terraform.lock.hcl');p=d/'main.tf';p.write_text(p.read_text().replace('../../../../modules/cognito_auth',str(MODULE)))
  init=subprocess.run([args.terraform,'-chdir='+str(d),'init','-backend=false','-input=false','-lockfile=readonly','-no-color'],env=env,capture_output=True,text=True);need(init.returncode==0,'root rejection init')
  vals=dict(v);vals['aws_account_id']=vals.pop('expected_scope')['account_id'];rootheader=(ROOT/'tests/auth.tftest.hcl').read_text().split('run "')[0];rejections=[]
  for key in vals:
   q=dict(vals);q.pop(key);(d/'tests/probe.tftest.hcl').write_text(rootheader+test(q)[len(header):]);code,events=run(args.terraform,d,env)
   need(code!=0 and any(e['type']=='diagnostic' and e['diagnostic']['summary']=='No value for required variable' and key in e['diagnostic']['detail'] for e in events),'missing input rejection '+key)
   need(not any(e['type']=='test_run' and e['test_run'].get('status')=='pass' for e in events),'no successful incomplete test');rejections.append(key)
 print(json.dumps(dict(status='passed',source_mutations=len(results),detected=results,required_root_inputs=len(rejections),rejected_inputs=rejections)))
if __name__=='__main__':main()
