#!/usr/bin/env bash
# Operator watchdog for long unattended campaigns (no LLM). Restarts `rsi run` through the campaign launcher when the
# orchestrator died, or when it finished with a recoverable fault (a failed THINK/postprocess, unfinished nodes).
# Budget/saturation stops end the watch; runner_broken (agent runtime down, e.g. quota) waits 30 min, then retries.
#   scripts/autoresume.sh <experiment dir> <launcher command...>
set -uo pipefail
EXP="$(cd "$1" && pwd)"; shift
LOG="$EXP/autoresume.log"; MAX_RESTARTS="${MAX_RESTARTS:-25}"
log(){ echo "[$(date -u +%FT%TZ)] $*" | tee -a "$LOG"; }
alive(){ python3 - "$EXP" <<'EOF'
import json, os, sys, time
d = json.load(open(os.path.join(sys.argv[1], 'state.json')))
os.kill(d['pid'], 0)
sys.exit(0 if d.get('status') != 'finished' and time.time() - d['heartbeat'] < 900 else 1)
EOF
}
verdict(){ python3 - "$EXP" <<'EOF'
import json, os, sys
exp = sys.argv[1]
try:
    st = json.load(open(os.path.join(exp, 'state.json')))
except Exception:
    print('restart'); sys.exit()
if st.get('status') != 'finished':
    print('restart'); sys.exit()
fin = json.load(open(os.path.join(exp, 'final.json'))) if os.path.exists(os.path.join(exp, 'final.json')) else {}
faults = set(fin.get('faults') or [])
reason = st.get('stop_reason') or fin.get('stop_reason')
if 'runner_broken' in faults or reason == 'runner_broken':
    print('broken')
elif faults or reason in ('research_failed', 'postprocess_failed'):
    print('restart')
else:
    print('done:' + str(reason))
EOF
}
restarts=0
log "watching $EXP"
while true; do
  if [ -f "$EXP/state.json" ] && alive; then sleep 120; continue; fi
  v="$(verdict)"
  case "$v" in
    done:*) log "campaign finished cleanly (${v#done:}); watchdog exits"; exit 0;;
    broken) log "runner_broken: waiting 30 min before resuming"; sleep 1800;;
  esac
  restarts=$((restarts+1))
  if [ "$restarts" -gt "$MAX_RESTARTS" ]; then log "too many restarts ($restarts); giving up"; exit 1; fi
  log "resuming (#$restarts, verdict=$v)"
  "$@" >> "$EXP/run.log" 2>&1 < /dev/null
  log "launcher exited with $?"
  sleep 60
done
