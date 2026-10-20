#!/usr/bin/env bash
# Live smoke (foreground, self-terminating; 556d must NOT be running). 0.5.0 eval set: the LLM eval set on a fresh throwaway character (foreground, self-terminating).
set -u
R=$(cd "$(dirname "$0")/../.." && pwd)
S="$R/tests/live/out"; mkdir -p "$S"
D=http://127.0.0.1:55600
PY=$R/vendor/hermes-agent/.venv/Scripts/python.exe
H=$R/vendor/hermes-agent/.venv/Scripts/hermes.exe
P=$R/home/profiles/probe
PW="$(cd "$R" && pwd -W)/home/profiles/probe"
LOG="$S/556d.smoke12.log"
cd "$R"
# never beside the app: the daemon owns :55600 and the app connects to whatever listens there
if curl -s -m 2 http://127.0.0.1:55600/api/companions >/dev/null 2>&1 || tasklist //FI "IMAGENAME eq electron.exe" 2>/dev/null | grep -qi electron; then
  echo "a 556d or the app is running — close the app first"; exit 2
fi
HERMES_HOME=$R/home PYTHONUTF8=1 timeout 60 $H profile delete probe --yes >/dev/null 2>&1; rm -rf "$P" 2>/dev/null
powershell -NoProfile -ExecutionPolicy Bypass -File "$R/new-companion.ps1" -Name probe -DisplayName "試音" >/dev/null 2>&1; echo "[smoke12] probe: $(ls $P/plugins | tr '\n' ' ')"
"$R/556d.exe" > "$LOG" 2>&1 &
PID=$!
cleanup() { if kill -0 $PID 2>/dev/null; then kill $PID 2>/dev/null; fi; wait $PID 2>/dev/null; }
trap cleanup EXIT
for i in $(seq 1 30); do curl -s "$D/api/companions" >/dev/null && break; sleep 1; done
isup() { curl -s "$D/api/companions" | PYTHONUTF8=1 $PY -c "import sys,json; d=json.load(sys.stdin); c=[x for x in d['companions'] if x['name']=='probe'][0]; sys.exit(0 if c['active'] and c['hermes_connected'] else 1)"; }
curl -s -X POST "$D/api/companions/probe/start" >/dev/null; for i in $(seq 1 120); do isup && break; sleep 1; done; echo "   up after ${i}s"
PYTHONUTF8=1 $PY "$R/tests/psyche_eval.py" --companion probe --out "$S/psyche_eval.jsonl" --wait 40 2>&1
echo "[smoke12] final state:"; curl -s "$D/api/psyche?companion=probe" | PYTHONUTF8=1 $PY -c "import sys,json; d=json.load(sys.stdin); print('   instances:', [(i['type'], round(i['intensity0'],2)) for i in d['instances'] if i['resolved_at'] is None]); print('   loops:', [(l['what'], l['state']) for l in d['loops']])"
curl -s -X POST "$D/api/companions/probe/stop" >/dev/null; for i in $(seq 1 90); do curl -s "$D/api/companions" | grep -q '"name":"probe"[^}]*"active":false' && break; sleep 1; done; echo "   stopped after ${i}s"
curl -s -X POST "$D/api/shutdown" >/dev/null; for i in $(seq 1 90); do kill -0 $PID 2>/dev/null || break; sleep 1; done
grep -h -i "psyche" "$P/logs/gateway.log" 2>/dev/null | grep -i "warn\|error\|fail" | tail -3 | cut -c1-200 | sed 's/^/   log: /'
echo "[smoke12] done (probe kept)"
