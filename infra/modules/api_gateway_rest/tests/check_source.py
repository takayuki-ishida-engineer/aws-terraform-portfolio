"""Actual mutated mock plans and missing required input rejection witnesses."""
import os,sys,subprocess,tempfile,shutil,json,re
from pathlib import Path
sys.dont_write_bytecode=True
from check_rest_core import HERE,REPO,parse,verify_plan,need
TF=sys.argv[1] if len(sys.argv)>1 else 'terraform'
env={k:v for k,v in os.environ.items() if not k.startswith(('AWS_','TF_VAR_','TF_CLI_ARGS'))};env.update(AWS_CONFIG_FILE='/dev/null',AWS_SHARED_CREDENTIALS_FILE='/dev/null',AWS_EC2_METADATA_DISABLED='true')
probe=(HERE/'core.tftest.hcl').read_text().split('run "reject_',1)[0]
changes=[('edge','"REGIONAL"','"EDGE"'),('enabled','disable_execute_api_endpoint = true','disable_execute_api_endpoint = false'),('type','"COGNITO_USER_POOLS"','"REQUEST"'),('api_ref','aws_api_gateway_rest_api.this.id','"invented"'),('arn_ref','[var.authentication.user_pool_arn]','["arn:aws:cognito-idp:ca-central-1:000000000000:userpool/ca-central-1_TestPool"]')]
mutations=[];missing=[]
with tempfile.TemporaryDirectory(prefix='rest-source-',dir=os.environ.get('RUNNER_TEMP','/tmp')) as td:
 for label,old,new in changes:
  d=Path(td)/label;d.mkdir();(d/'tests').mkdir()
  for f in HERE.parent.glob('*.tf'):shutil.copy2(f,d/f.name)
  shutil.copy2(REPO/'infra/services/dev/ca-central-1/api/.terraform.lock.hcl',d/'.terraform.lock.hcl')
  main=d/'main.tf';text=main.read_text();need(old in text,'source witness exists '+label);main.write_text(text.replace(old,new));(d/'tests/probe.tftest.hcl').write_text(probe)
  run=subprocess.run([TF,'-chdir='+str(d),'test','-json','-verbose','-no-color'],env=dict(env,TF_DATA_DIR=str(HERE.parent/'.terraform')),capture_output=True,text=True)
  need(run.returncode==0 and not run.stderr.strip(),'actual mutant plan '+label)
  plans=[parse(l)['test_plan'] for l in run.stdout.splitlines() if parse(l)['type']=='test_plan'];need(len(plans)==1,'one complete witness')
  try:
   verify_plan(plans[0])
   # Identical synthetic ARN still requires actual source provenance.
   need(re.search(r'provider_arns\s*=\s*\[var.authentication.user_pool_arn\]',main.read_text()),'ARN source binding')
  except (ValueError,KeyError,TypeError):mutations.append(label)
  else:raise ValueError('undetected source mutation '+label)
 # Remove validation entirely: native rejection expectations must fail.
 d=Path(td)/'validation';shutil.copytree(HERE.parent,d,ignore=shutil.ignore_patterns('.terraform','.terraform.lock.hcl','__pycache__'))
 shutil.copy2(REPO/'infra/services/dev/ca-central-1/api/.terraform.lock.hcl',d/'.terraform.lock.hcl')
 p=d/'variables.tf';s=p.read_text();start=s.index('  validation {',s.index('variable "authentication"'));end=s.index('\n}\nvariable "tags"',start);p.write_text(s[:start]+s[end:])
 run=subprocess.run([TF,'-chdir='+str(d),'test','-json','-no-color'],env=dict(env,TF_DATA_DIR=str(HERE.parent/'.terraform')),capture_output=True,text=True)
 need(run.returncode!=0 and 'Missing expected failure' in run.stdout,'validation removal rejected');mutations.append('validation_removed')
 for key in ['expected_scope','name_prefix','authentication']:
  d=Path(td)/('missing-'+key);d.mkdir();(d/'tests').mkdir()
  for f in HERE.parent.glob('*.tf'):shutil.copy2(f,d/f.name)
  shutil.copy2(REPO/'infra/services/dev/ca-central-1/api/.terraform.lock.hcl',d/'.terraform.lock.hcl')
  s=re.sub(r'^\s*'+key+r'\s*=\s*.*\n','',probe,flags=re.M);(d/'tests/probe.tftest.hcl').write_text(s)
  run=subprocess.run([TF,'-chdir='+str(d),'test','-json','-verbose','-no-color'],env=dict(env,TF_DATA_DIR=str(HERE.parent/'.terraform')),capture_output=True,text=True)
  events=[parse(l) for l in run.stdout.splitlines()];need(run.returncode==1 and not run.stderr.strip() and any(e.get('diagnostic',{}).get('summary')=='No value for required variable' for e in events) and not any(e['type']=='test_plan' for e in events),'missing input '+key);missing.append(key)
print(json.dumps(dict(status='passed',source_mutations=len(mutations),mutations=mutations,missing_required_inputs=len(missing))))
