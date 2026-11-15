"""Validate sanitized container/host receipts. Missing evidence fails the Job."""
import os,re
from pathlib import Path
from gates import CONTROLS,OPERATIONS,require
from runtime_contracts import strict_json,DIAGNOSTICS
STATUSES={'PASS','FAIL','BLOCKED','NOT_TESTED','PARTIAL-SKIP'}
STAGES=set(OPERATIONS)|{'preflight','startup','generated-material','health','auth-signed-sts','auth-invalid-signature','auth-invalid-credential','auth-unsigned-sts','provider-init','baseline','api_absence'}
REQUIRED={'control-'+key for key in CONTROLS}|set(OPERATIONS)|{'resource-cleanup','process-cleanup','lifecycle-evidence-complete','host-cleanup'}

KNOWN=REQUIRED|{'execution-identity','execution','complete-evidence-and-cleanup','startup-ready','authentication-enforced','auth-invalid-signature','auth-invalid-credential','partial-create-api-cleanup','material-cleanup'}|{'recovery-'+name for name in [*CONTROLS,*OPERATIONS]}|{stage+'-'+tool for stage in STAGES for tool in ['ip','aws','terraform','aws-emulator']}

def rows_from_text(text):
  rows=[]
  for line in text.splitlines():
    row=strict_json(line)
    require(set(row)<={'gate','status','diagnostic','exit_code','resource_id','api','sha','run_id'},'summary-fields')
    require(isinstance(row.get('gate'),str) and row['gate'] in KNOWN and row.get('status') in STATUSES,'summary-row')
    require(row.get('diagnostic') is None or row['diagnostic'] in DIAGNOSTICS,'summary-diagnostic')
    rows.append(row)
  return rows

def complete(rows,sha,run_id,execution_status):
  require(execution_status=='success' and re.fullmatch('[0-9a-f]{40}',sha) and re.fullmatch('[0-9]+-[0-9]+',run_id),'summary-execution')
  identities=[row for row in rows if row['gate']=='execution-identity']
  require(len(identities)==1 and identities[0].get('sha')==sha and identities[0].get('run_id')==run_id and identities[0]['status']=='PASS','summary-identity')
  require(all(row['status']=='PASS' for row in rows),'summary-failure')
  for gate in REQUIRED:
    receipts=[row for row in rows if row['gate']==gate]
    require(len(receipts)==1 and receipts[0]['status']=='PASS','summary-missing-duplicate')
  require(rows[-1]['gate']=='host-cleanup','summary-host-cleanup-order')

def main():
  result=1
  with open(os.environ['GITHUB_STEP_SUMMARY'],'a') as output:
    output.write('## Representative Emulator run\n\n')
    sha=os.environ.get('TARGET_SHA','');run_id=os.environ.get('GITHUB_RUN_ID','')+'-'+os.environ.get('GITHUB_RUN_ATTEMPT','')
    output.write('Target SHA: '+(sha if re.fullmatch('[0-9a-f]{40}',sha) else 'INVALID')+'\n\n')
    output.write('Billing: '+('owner-attested; not API-audited' if os.environ.get('OWNER_ATTESTATION_ACCEPTED')=='true' else 'NOT VERIFIED / BLOCKED')+'\n\n')
    try:
      require(os.environ.get('OWNER_ATTESTATION_ACCEPTED')=='true','summary-owner')
      path=Path(os.environ['RUNNER_TEMP'])/'emulator-safe-report.json'
      rows=rows_from_text(path.read_text())
      for row in rows:output.write('| '+row['gate']+' | '+row['status']+' |\n')
      complete(rows,sha,run_id,os.environ.get('EXECUTION_STATUS'))
      output.write('Complete measured lifecycle and host-cleanup evidence recorded; independent review pending.\n')
      result=0
    except Exception:
      # Never echo corrupt report content, arbitrary exception text or credentials.
      output.write('FAIL/BLOCKED: SUMMARY_EVIDENCE_INVALID; no complete demonstration claimed.\n')
  return result
if __name__=='__main__':raise SystemExit(main())
