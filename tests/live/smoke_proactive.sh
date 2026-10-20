#!/usr/bin/env bash
# Live smoke (foreground, self-terminating; 556d must NOT be running). 0.6.0 proactive on a test character (foreground, self-terminating): plugin loads with proactive on, the 主動 settings API,
# a reminder queued as a command fires on time as an event turn through her API -> her reply is a row in her ONE
# conversation (user row = 【事件】 cue, hidden by the follower), sent to Telegram by 556d; graceful stop.
set -u
C=${1:?usage: smoke_proactive.sh <character id>}
R=$(cd "$(dirname "$0")/../.." && pwd)
S="$R/tests/live/out"; mkdir -p "$S"
D=http://127.0.0.1:55600
PY=$R/vendor/hermes-agent/.venv/Scripts/python.exe
P=$R/home/profiles/$C
PW="$(cd "$R" && pwd -W)/home/profiles/$C"
LOG="$S/556d.smoke13.log"
cd "$R"
# never beside the app: the daemon owns :55600 and the app connects to whatever listens there
if curl -s -m 2 http://127.0.0.1:55600/api/companions >/dev/null 2>&1 || tasklist //FI "IMAGENAME eq electron.exe" 2>/dev/null | grep -qi electron; then
  echo "a 556d or the app is running — close the app first"; exit 2
fi
"$R/556d.exe" > "$LOG" 2>&1 &
PID=$!
cleanup() { if kill -0 $PID 2>/dev/null; then kill $PID 2>/dev/null; fi; wait $PID 2>/dev/null; }
trap cleanup EXIT
for i in $(seq 1 30); do curl -s "$D/api/companions" >/dev/null && break; sleep 1; done
hdr=(-H "X-556-Companion: $C")
isup() { curl -s "$D/api/companions" | PYTHONUTF8=1 $PY -c "import sys,json; d=json.load(sys.stdin); c=[x for x in d['companions'] if x['name']=='$C'][0]; sys.exit(0 if c['active'] and c['hermes_connected'] else 1)"; }
echo "[smoke13] start $C"; curl -s -X POST "$D/api/companions/$C/start" >/dev/null; for i in $(seq 1 120); do isup && break; sleep 1; done; echo "   up after ${i}s"
sleep 3; grep -h "psyche:" "$P/logs/agent.log" | tail -n 1 | cut -c1-160 | sed 's/^/   log: /'
echo "[smoke13] settings API:"; curl -s "$D/api/psyche/settings?companion=$C" | PYTHONUTF8=1 $PY -c "import sys,json; d=json.load(sys.stdin); print('   exists=',d['exists'],'proactive=',d['settings'].get('proactive',{}).get('enabled'),'cap=',d['settings'].get('proactive',{}).get('daily_cap'))"
curl -s -X PUT "$D/api/psyche/settings?companion=$C" -H "Content-Type: application/json" -d '{"proactive":{"enabled":true,"no_disturb":[[23.0,8.0]],"min_gap_min":1},"life":{"busyness_mode":"hobby"}}' | PYTHONUTF8=1 $PY -c "import sys,json; d=json.load(sys.stdin); print('   PUT hot: restart_required=',d['restart_required'])"
echo "[smoke13] one normal turn (so the engine knows her session)"
printf '%s' '{"model":"556","stream":false,"messages":[{"role":"user","content":"我回來了，今天有點忙。等一下我要去倒垃圾。"}]}' > "$S/$C_q.json"
curl -s -X POST "$D/api/chat" -H "Content-Type: application/json" -H "X-556-Client: smoke" "${hdr[@]}" --data-binary @"$S/$C_q.json" | PYTHONUTF8=1 $PY -c "import sys,json; d=json.load(sys.stdin); print('   reply=',d['choices'][0]['message']['content'][:160].replace(chr(10),' '))"
CUE=$(PYTHONUTF8=1 $PY -c "import datetime; print((datetime.datetime.now()+datetime.timedelta(minutes=2)).strftime('%Y-%m-%dT%H:%M'))")
echo "[smoke13] queue a reminder for $CUE (two minutes out)"
printf '{"op":"add_loop","payload":{"what":"提醒製作人倒垃圾","cue_time":"%s","importance":0.9}}' "$CUE" > "$S/cmd1.json"
curl -s -X POST "$D/api/psyche/command?companion=$C" -H "Content-Type: application/json" --data-binary @"$S/cmd1.json" | PYTHONUTF8=1 $PY -c "import sys,json; print('   ', json.load(sys.stdin))"
n0=$(PYTHONUTF8=1 $PY -c "import sqlite3; c=sqlite3.connect('$PW/state.db'); print(c.execute(\"select count(*) from messages where role='assistant'\").fetchone()[0])")
echo "[smoke13] waiting for the event turn (up to 5 min)…"
for i in $(seq 1 300); do
  n=$(PYTHONUTF8=1 $PY -c "import sqlite3; c=sqlite3.connect('$PW/state.db'); print(c.execute(\"select count(*) from messages where role='assistant'\").fetchone()[0])")
  [ "$n" -gt "$n0" ] && break; sleep 1
done
sleep 4; echo "   after ${i}s:"
PYTHONUTF8=1 $PY - <<EOF
import sqlite3, json
c = sqlite3.connect('$PW/state.db')
for role, content in c.execute("select role, content from messages order by id desc limit 3").fetchall()[::-1]:
    print('   ', role, '|', (content or '')[:220].replace('\n', ' / '))
p = sqlite3.connect('$PW/psyche.db')
print('   loops:', p.execute("select what, state from loops order by created_at desc limit 3").fetchall())
print('   events:', [r[0] + ':' + r[1][:70] for r in p.execute("select kind, payload from events where kind in ('proactive_fired','sent','silent','send_failed','loop_due') order by id desc limit 5").fetchall()])
print('   checks:', p.execute("select count(*) from checks").fetchone()[0])
EOF
grep -h -i -E "psyche|spoke first|telegram mirror" "$LOG" | tail -n 4 | cut -c1-160 | sed 's/^/   556d: /'
grep -h "psyche" "$P/logs/agent.log" | grep -i -E "event turn|warn|error|check" | tail -n 4 | cut -c1-180 | sed 's/^/   log: /'
echo "[smoke13] /api/psyche:"; curl -s "$D/api/psyche?companion=$C" | PYTHONUTF8=1 $PY -c "import sys,json; d=json.load(sys.stdin); s=d['snapshot']; print('   activity=',s.get('activity'),'phase=',s.get('contact',{}).get('phase'),'proactive_today=',s.get('contact',{}).get('proactive_today'),'awaiting=',s.get('contact',{}).get('awaiting_since') is not None,'share=',[x['what'] for x in s.get('share_backlog',[])]); print('   block:', ' / '.join((s.get('last_block',{}).get('text','') or '').splitlines()[1:4]))"
curl -s -X PUT "$D/api/psyche/settings?companion=$C" -H "Content-Type: application/json" -d '{"proactive":{"min_gap_min":90},"life":{"busyness_mode":"work"}}' >/dev/null; echo "   settings restored"
echo "[smoke13] stop"; t0=$(date +%s); curl -s -X POST "$D/api/companions/$C/stop" >/dev/null
for i in $(seq 1 90); do curl -s "$D/api/companions" | grep -q "\"name\":\"$C\"[^}]*\"active\":false" && break; sleep 1; done; echo "   stopped after $(( $(date +%s) - t0 ))s"
curl -s -X POST "$D/api/shutdown" >/dev/null; for i in $(seq 1 90); do kill -0 $PID 2>/dev/null || break; sleep 1; done
echo "[smoke13] done"
