#!/usr/bin/env bash
# Step 2 rehearsal launcher. Owner-authorized local runs only; refused in CI.
#
# Stages public tools under /opt/step2-tools, then runs rehearse.py in a fresh
# network + mount namespace on a namespace-private tmpfs (/opt/step2-work), as
# uid 1000 with no capabilities and no_new_privs. Needs root for unshare/mount.
#
#   STEP2_BASE            directory prepared by prepare.py (artifacts, tools, prepared.json)
#   STEP2_PROVIDER_MIRROR filesystem mirror with the locked AWS provider (default: $STEP2_BASE/mirror)
#   TESTED_SHA            merged main SHA whose network root and vpc module are rehearsed
#   SCENARIO              all (default), network, network-full, tfstate or api
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
REPO=$(git -C "$HERE" rev-parse --show-toplevel)
BASE=${STEP2_BASE:?set STEP2_BASE to the prepare.py directory}
MIRROR=${STEP2_PROVIDER_MIRROR:-$BASE/mirror}
SHA=${TESTED_SHA:?set TESTED_SHA}
SCENARIO=${SCENARIO:-all}
T=/opt/step2-tools
RUN_ID=$(date -u +%Y%m%d%H%M%S)-1

if [ -n "${CI:-}${GITHUB_ACTIONS:-}" ]; then echo '{"gate":"local-only","status":"BLOCKED"}'; exit 1; fi
[ "$(id -u)" = 0 ] || { echo '{"gate":"root-for-namespaces","status":"BLOCKED"}'; exit 1; }
case "$SCENARIO" in all|network|network-full|tfstate|api) ;; *) echo '{"gate":"scenario","status":"BLOCKED"}'; exit 1;; esac
[[ "$SHA" =~ ^[0-9a-f]{40}$ ]] && git -C "$REPO" merge-base --is-ancestor "$SHA" origin/main \
  || { echo '{"gate":"tested-sha-on-main","status":"BLOCKED"}'; exit 1; }

rm -rf "$T" /opt/step2-work /opt/step2-evidence
mkdir -p "$T/bin" "$T/harness" "$T/source" /opt/step2-work /opt/step2-evidence
cp -a "$BASE/tools/emulator" "$T/emulator"
ln -s "$T/emulator/opt/aws-emulator/bin/aws-emulator" "$T/bin/aws-emulator"
rm -rf "$BASE/awscli-src"; unzip -q "$BASE/artifacts/awscli.zip" -d "$BASE/awscli-src"
"$BASE/awscli-src/aws/install" --install-dir "$T/aws-cli" --bin-dir "$T/bin" >/dev/null
rm -rf "$BASE/awscli-src"
cp "$BASE/tools/bin/terraform" "$T/bin/terraform"
cp -a "$MIRROR" "$T/mirror"
git -C "$REPO" archive "$SHA" infra/services/dev/ca-central-1 infra/modules | tar -x -C "$T/source"
cp "$REPO/scripts/emulator-verification/gates.py" "$REPO/scripts/emulator-verification/runtime_contracts.py" \
   "$HERE/rehearse.py" "$T/harness/"
cp "$BASE/prepared.json" "$T/prepared.json"
HARNESS_SHA256=$(sha256sum "$HERE/rehearse.py" | cut -d' ' -f1)
printf '{"sha":"%s","run_id":"%s","scenario":"%s","harness_sha256":"%s"}\n' "$SHA" "$RUN_ID" "$SCENARIO" "$HARNESS_SHA256" > "$T/run.json"
chmod -R a+rX,go-w "$T"
chown 1000:1000 /opt/step2-evidence; chmod 700 /opt/step2-evidence
echo "{\"gate\":\"staged\",\"status\":\"PASS\",\"sha\":\"$SHA\",\"run_id\":\"$RUN_ID\",\"scenario\":\"$SCENARIO\",\"harness_sha256\":\"$HARNESS_SHA256\"}"

set +e
unshare --net --mount --fork --propagation private -- bash -c '
  set -e
  mount -t tmpfs -o size=8g,mode=0700,uid=1000,gid=1000 tmpfs /opt/step2-work
  /usr/sbin/ip link set lo up
  exec setpriv --reuid=1000 --regid=1000 --clear-groups --no-new-privs --inh-caps=-all --bounding-set=-all -- \
    env -i PATH=/usr/bin:/bin HOME=/opt/step2-work/home LANG=C.UTF-8 PYTHONDONTWRITEBYTECODE=1 \
    /usr/local/bin/python3 -I /opt/step2-tools/harness/rehearse.py'
code=$?
set -e
# Host-side receipts: the namespace and its tmpfs are gone; nothing private remains.
mountpoint -q /opt/step2-work && echo '{"gate":"host-tmpfs-unmounted","status":"FAIL"}' || echo '{"gate":"host-tmpfs-unmounted","status":"PASS"}'
[ -z "$(ls -A /opt/step2-work)" ] && echo '{"gate":"host-work-empty","status":"PASS"}' || echo '{"gate":"host-work-empty","status":"FAIL"}'
pgrep -f aws-emulator >/dev/null && echo '{"gate":"host-no-emulator-process","status":"FAIL"}' || echo '{"gate":"host-no-emulator-process","status":"PASS"}'
mkdir -p "$BASE/evidence"; cp /opt/step2-evidence/*.json "$BASE/evidence/" 2>/dev/null || true
exit $code
