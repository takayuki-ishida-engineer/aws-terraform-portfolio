"""Static manual-workflow contract; also used on deliberately unsafe mutations."""
import re
from gates import require
CHECKOUT='actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1'
def workflow_gate(w):
  require(set(w['on'])=={'workflow_dispatch'},'manual-only')
  require(w['permissions']=={'contents':'read'} and w['concurrency']=={'group':'aws-emulator-representative','cancel-in-progress':'false'},'permissions-concurrency')
  require(set(w['jobs'])=={'representative'},'one-standard-job')
  j=w['jobs']['representative'];require(j['runs-on']=='ubuntu-24.04' and j['timeout-minutes']=='25','standard-free-runner')
  require('permissions' not in j and 'container' not in j and 'services' not in j,'no-extra-runtime-privileges')
  dispatch=w['on']['workflow_dispatch']['inputs'];require(set(dispatch)=={'target_sha','owner_billing_confirmed','owner_checked_at'},'dispatch-contract')
  require(dispatch['owner_billing_confirmed']['default']=='false' and all(v['required']=='true' for v in dispatch.values()),'explicit-owner-confirmation')
  require('RUNNER_KIND' not in j.get('env',{}),'runner-context-step-only')
  steps=j['steps'];require(len(steps)==5 and steps[0]['id']=='consent','consent-before-checkout')
  require(steps[2].get('env')=={'RUNNER_KIND':'${{ runner.environment }}'},'runner-environment-step-context')
  actions=[s for s in steps if 'uses' in s];require(len(actions)==1 and actions[0]['uses']==CHECKOUT,'pinned-approved-checkout-only')
  require(actions[0]['with']=={'ref':'${{ inputs.target_sha }}','persist-credentials':'false','submodules':'false','lfs':'false'},'checkout-no-auth-lfs')
  text=str(w)
  require(not any(x in text for x in ['secrets.', 'id-token', 'upload-artifact', 'actions/cache', 'docker/login', 'docker push', '--privileged', '--network host', '/var/run/docker.sock']), 'no-external-writes-or-host-network')
  run=steps[3]['run'];line=next(l for l in run.splitlines() if l.strip().startswith('docker run '))
  for token in ['--network none','--cap-drop ALL','--security-opt no-new-privileges:true','--read-only','--user 1000:1000','--memory 3g','--cpus 2','--tmpfs /work:', '--tmpfs /tmp:']:
    require(token in line,'isolation-flag-'+token)
  require(not re.search(r'(?:^|\s)(?:-p|-v|--publish|--volume|--mount|--env-file)(?:\s|=)',line),'no-port-or-host-mount')
  for token in ["e['ACTOR']==e['OWNER']", "e['TRIGGERING_ACTOR']==e['OWNER']", "e['GITHUB_REF']=='refs/heads/main'", "e['TARGET_SHA']==e['GITHUB_SHA']", "e['GITHUB_RUN_ATTEMPT']=='1'", "<= 1800", "e['OWNER_BILLING_CONFIRMED']=='true'"]:
    require(token in steps[0]['run'],'owner-pre-check-'+token)
