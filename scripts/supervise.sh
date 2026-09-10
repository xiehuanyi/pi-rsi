#!/usr/bin/env bash
# External supervisor: keeps `rsi run <exp>` alive until the experiment reports finished.
# No LLM here. If the orchestrator dies (crash, OOM, reboot), it is restarted; `rsi run` itself performs crash
# recovery (stale running nodes -> failed -> diagnosed -> retried).
#   scripts/supervise.sh experiments/<name> [check_interval_s]
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
EXP="$(cd "$1" && pwd)"; INTERVAL="${2:-60}"
LOG="$EXP/supervise.log"
log(){ echo "[$(date -u +%FT%TZ)] $*" | tee -a "$LOG"; }
finished(){ python3 -c "import json,sys; d=json.load(open('$EXP/state.json')); sys.exit(0 if d.get('status')=='finished' else 1)" 2>/dev/null; }
alive(){ python3 -c "import json,os,sys,time; d=json.load(open('$EXP/state.json')); pid=d['pid']; os.kill(pid,0); sys.exit(0 if time.time()-d['heartbeat']<600 else 1)" 2>/dev/null; }
restarts=0
while true; do
  if finished; then log "experiment finished; supervisor exiting"; exit 0; fi
  if ! alive; then
    restarts=$((restarts+1))
    if [ "$restarts" -gt 20 ]; then log "too many restarts; giving up"; exit 1; fi
    log "orchestrator not alive; (re)starting (#$restarts)"
    (cd "$EXP" && setsid nohup "$HERE/rsi" run . >> "$EXP/run.log" 2>&1 < /dev/null &)
    sleep 15
  fi
  sleep "$INTERVAL"
done
