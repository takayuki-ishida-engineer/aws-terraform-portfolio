"""Static contract of the Step 2 rehearsal workflow.

Mirrors scripts/emulator-verification/contracts.py where it applies: push to main
on exact paths or the Owner's manual dispatch only (Owner decision 2026-11-20, no
per-run billing attestation), read-only token, one standard free runner, a run
gate (main, the Owner, a public repository, attempt 1) before a pinned
credential-free checkout, no secrets/artifacts/caches/registry writes, and an
isolated container with exact flags and tmpfs bounds. Also used on unsafe
mutations in test_rehearse.py.
"""
import re
import shlex

from gates import require

CHECKOUT = 'actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1'
PATHS = ['infra/**', 'scripts/emulator-rehearsal/**', 'scripts/emulator-verification/gates.py',
         'scripts/emulator-verification/runtime_contracts.py', 'scripts/emulator-verification/prepare.py',
         'scripts/emulator-verification/versions.json', 'scripts/emulator-verification/awscli-publisher.asc',
         '.github/workflows/aws-emulator-rehearsal.yml']
JOB_ENV = {'ACTOR': '${{ github.actor }}', 'TRIGGERING_ACTOR': '${{ github.triggering_actor }}',
           'OWNER': '${{ github.repository_owner }}', 'VISIBILITY': '${{ github.event.repository.visibility }}',
           'TARGET_SHA': '${{ github.sha }}', 'SCENARIO': "${{ inputs.scenario || 'no-interface-endpoints' }}"}
TMPFS = sorted(['/opt/step2-work:rw,exec,nosuid,nodev,size=3g,uid=1000,gid=1000,mode=0700',
                '/opt/step2-evidence:rw,noexec,nosuid,nodev,size=1m,uid=1000,gid=1000,mode=0700',
                '/tmp:rw,noexec,nosuid,nodev,size=64m,uid=1000,gid=1000'])


def workflow_gate(w):
    require(set(w['on']) == {'push', 'workflow_dispatch'}, 'push-or-dispatch-only')
    require(w['on']['push'] == {'branches': ['main'], 'paths': PATHS}, 'push-main-exact-paths')
    require(w['permissions'] == {'contents': 'read'}
            and w['concurrency'] == {'group': 'aws-emulator-rehearsal', 'cancel-in-progress': 'false'}, 'permissions-concurrency')
    require(set(w['jobs']) == {'rehearsal'}, 'one-standard-job')
    j = w['jobs']['rehearsal']
    require(j['runs-on'] == 'ubuntu-24.04' and j['timeout-minutes'] == '30', 'standard-free-runner')
    require('permissions' not in j and 'container' not in j and 'services' not in j, 'no-extra-runtime-privileges')
    dispatch = w['on']['workflow_dispatch']['inputs']
    require(set(dispatch) == {'scenario'} and dispatch['scenario']['required'] == 'true', 'dispatch-contract')
    require(dispatch['scenario']['type'] == 'choice' and dispatch['scenario']['options'] == ['no-interface-endpoints', 'full']
            and dispatch['scenario']['default'] == 'no-interface-endpoints', 'scenario-choice')
    require(j.get('env') == JOB_ENV, 'job-env-contract')
    steps = j['steps']
    require(len(steps) == 5 and steps[0].get('id') == 'consent', 'consent-before-checkout')
    actions = [s for s in steps if 'uses' in s]
    require(len(actions) == 1 and actions[0]['uses'] == CHECKOUT and steps[1] is actions[0], 'pinned-approved-checkout-only')
    require(actions[0]['with'] == {'ref': '${{ github.sha }}', 'persist-credentials': 'false', 'submodules': 'false', 'lfs': 'false'},
            'checkout-no-auth-lfs')
    require(steps[2].get('env') == {'RUNNER_KIND': '${{ runner.environment }}'}
            and steps[2]['run'].strip() == 'STEP2_BASE="$RUNNER_TEMP/step2" python3 scripts/emulator-rehearsal/prepare.py --docker-context',
            'verified-preparation-step')
    text = str(w)
    require(not any(x in text for x in ['secrets.', 'id-token', 'upload-artifact', 'actions/cache', 'docker/login', 'docker push',
                                        '--privileged', '--network host', '/var/run/docker.sock', 'pull_request_target']),
            'no-external-writes-or-host-network')
    for token in ["e['ACTOR']==e['OWNER']", "e['TRIGGERING_ACTOR']==e['OWNER']", "e['GITHUB_REF']=='refs/heads/main'",
                  "e['TARGET_SHA']==e['GITHUB_SHA']", "e['GITHUB_RUN_ATTEMPT']=='1'", "e['VISIBILITY']=='public'",
                  "e['GITHUB_EVENT_NAME'] in ('push','workflow_dispatch')", "e['SCENARIO'] in ('no-interface-endpoints','full')"]:
        require(token in steps[0]['run'], 'run-gate-' + token)
    run = steps[3]['run']
    require(steps[3].get('id') == 'execution', 'execution-step')
    line = next(l for l in run.splitlines() if l.strip().startswith('docker run '))
    require(not re.search(r'(?:^|\s)(?:-p|-v|-e|--env|--publish|--volume|--mount|--env-file)(?:\s|=)', line), 'no-port-or-host-mount')
    isolated_run_gate(line)
    require(run.count('cleanup_failed=0') == 1 and 'docker container ls --all --filter' in run and 'trap cleanup EXIT' in run
            and "'{\"gate\":\"host-cleanup\",\"status\":\"FAIL\",\"diagnostic\":\"HOST_CLEANUP_FAILED\"}'" in run, 'strict-host-cleanup')
    require(steps[4].get('if') == 'always()' and steps[4].get('env') == {'EXECUTION_STATUS': '${{ steps.execution.outcome }}',
                                                                        'CONSENT_ACCEPTED': '${{ steps.consent.outputs.accepted }}'},
            'summary-real-outcome')
    require('python3 scripts/emulator-rehearsal/summarize.py' in steps[4]['run'] and 'CHECKOUT_UNAVAILABLE' in steps[4]['run']
            and 'exit 1' in steps[4]['run'], 'strict-summary')


def isolated_run_gate(line):
    words = shlex.split(line)
    require(words[:2] == ['docker', 'run'], 'docker-run-command')
    fixed = {'--name': '$container', '--network': 'none', '--cap-drop': 'ALL', '--security-opt': 'no-new-privileges:true',
             '--user': '1000:1000', '--memory': '6g', '--memory-swap': '6g', '--cpus': '2', '--pids-limit': '512'}
    switches = {'--rm', '--read-only'}
    seen, mounts, position = set(), [], 2
    while position < len(words) and words[position] != '$image':
        key = words[position]
        require(key in set(fixed) | switches | {'--tmpfs'}, 'unexpected-docker-option')
        require(key == '--tmpfs' or key not in seen, 'duplicate-docker-option')
        seen.add(key)
        position += 1
        if key not in switches:
            require(position < len(words), 'missing-docker-value')
            value = words[position]
            position += 1
            if key == '--tmpfs':
                mounts.append(value)
            else:
                require(value == fixed[key], 'docker-option-value')
    require(seen == set(fixed) | switches | {'--tmpfs'}, 'docker-options-missing')
    require(sorted(mounts) == TMPFS, 'docker-tmpfs-bounds')
    require(words[position:] == ['$image', '|', 'tee', '$RUNNER_TEMP/step2-safe-report.jsonl'], 'docker-image-and-report')
