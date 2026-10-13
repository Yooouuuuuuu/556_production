#!/usr/bin/env bash
# Live smoke (foreground, self-terminating; 556d must NOT be running). 0.7.0 multi-agent (foreground, self-terminating): seed the three characters' memories, start 千尋 and 小夜,
# one turn each with you, then a conversation between them through 556d's relay; check both sides' sessions,
# their memories about each other (subject = the other's name), their relationship state, the 狀態 log API; stop.
set -u
R=/d/dev/556_production
S="$R/tests/live/out"; mkdir -p "$S"
D=http://127.0.0.1:55600
PY=/d/dev/KeepsakeDB/.venv/Scripts/python.exe
PW=D:/dev/556_production/home/profiles
LOG="$S/556d.smoke14.log"
cd "$R"
"$R/556d.exe" > "$LOG" 2>&1 &
PID=$!
cleanup() { if kill -0 $PID 2>/dev/null; then kill $PID 2>/dev/null; fi; wait $PID 2>/dev/null; }
trap cleanup EXIT
for i in $(seq 1 30); do curl -s "$D/api/companions" >/dev/null && break; sleep 1; done
for i in $(seq 1 60); do curl -s -X POST http://127.0.0.1:55602/v1/embeddings -H "Content-Type: application/json" -d '{"model":"bge-m3","input":"hi"}' | grep -q '"embedding"' && break; sleep 1; done; echo "[smoke14] embedder up after ${i}s"
echo "[smoke14] seed memories"; for n in sayo chihiro yuma; do PYTHONUTF8=1 $PY "$R/tools/seed-memories.py" $n 2>&1 | tail -1 | sed 's/^/   /'; done
isup() { curl -s "$D/api/companions" | PYTHONUTF8=1 $PY -c "import sys,json; d=json.load(sys.stdin); c=[x for x in d['companions'] if x['name']=='$1'][0]; sys.exit(0 if c['active'] and c['hermes_connected'] else 1)"; }
for n in chihiro sayo; do curl -s -X POST "$D/api/companions/$n/start" >/dev/null; done
for n in chihiro sayo; do for i in $(seq 1 120); do isup $n && break; sleep 1; done; echo "   $n up after ${i}s: $(grep -h 'psyche:' $R/home/profiles/$n/logs/agent.log 2>/dev/null | tail -n 1 | cut -c25-120)"; done
turn() { printf '%s' "{\"model\":\"556\",\"stream\":false,\"messages\":[{\"role\":\"user\",\"content\":\"$2\"}]}" > "$S/q_$1.json"; curl -s -X POST "$D/api/chat" -H "Content-Type: application/json" -H "X-556-Client: smoke" -H "X-556-Companion: $1" --data-binary @"$S/q_$1.json" | PYTHONUTF8=1 $PY -c "import sys,json; d=json.load(sys.stdin); print('   $1 ->', d['choices'][0]['message']['content'][:140].replace(chr(10),' '))"; }
echo "[smoke14] a turn with each"; turn chihiro "千尋，第二張專輯錄得怎麼樣？"; turn sayo "小夜，〈路燈〉的副歌有進展嗎？"
echo "[smoke14] relay: 千尋 → 小夜"
printf '%s' '{"from":"chihiro","to":"sayo","text":"小夜，妳〈路燈〉的副歌弄得怎麼樣了？上次聽的版本後面可以再放開一點。"}' > "$S/relay.json"
curl -s -X POST "$D/api/relay" -H "Content-Type: application/json" --data-binary @"$S/relay.json" | sed 's/^/   /'; echo
for i in $(seq 1 240); do grep -q "turn cap reached\|stays quiet\|conversation ends\|turn failed" "$LOG" && break; sleep 1; done; echo "   relay finished after ${i}s"
grep -h "\[relay\]" "$LOG" | cut -c1-150 | sed 's/^/   /'
PYTHONUTF8=1 $PY - <<EOF
import sqlite3, json
for n, other in (("sayo", "chihiro"), ("chihiro", "sayo")):
    c = sqlite3.connect('$PW/%s/state.db' % n)
    rows = c.execute("select s.session_key, count(m.id) from sessions s left join messages m on m.session_id = s.id where s.session_key like '556:agent:%' group by s.id").fetchall()
    print('  ', n, 'agent sessions:', rows)
    p = sqlite3.connect('$PW/%s/psyche.db' % n)
    st = json.loads(p.execute("select state from snapshots order by id desc limit 1").fetchone()[0])
    print('     others:', {k: (round(v['need'], 2), v['contact'].get('phase')) for k, v in st.get('others', {}).items()})
    print('     rel:', {k: {'bond': round(v['bond'], 2), 'hours': round(v['hours'], 2), 'att': round(v['attachment'], 3)} for k, v in st.get('rel', {}).items()})
    print('     appraisals by counterpart:', p.execute("select counterpart, count(*) from appraisals group by counterpart").fetchall())
    m = sqlite3.connect('$PW/%s/memory/%s.db' % (n, n))
    print('     memories mentioning the other:', [t[0][:50] for t in m.execute("select text from memories where json_extract(meta,'$.seed') is null order by id desc limit 6").fetchall()])
EOF
echo "[smoke14] relay log API:"; curl -s "$D/api/relay/log?companion=sayo" | PYTHONUTF8=1 $PY -c "import sys,json; d=json.load(sys.stdin); print('   names=',d.get('names'),'convs=',[(c['counterpart'], len(c['messages'])) for c in d['conversations']])"
echo "[smoke14] a block with the other as counterpart (sayo's last):"; PYTHONUTF8=1 $PY -c "
import sqlite3
c = sqlite3.connect('$PW/sayo/state.db')
r = c.execute(\"select api_content from messages where role='user' and session_id in (select id from sessions where session_key like '556:agent:%') order by id desc limit 1\").fetchone()
s = (r[0] or '') if r else ''
i = s.find('【她現在】'); print('   ' + ' / '.join(s[i:].split('\n')[0:6]) if i >= 0 else '   (no block)')"
for n in chihiro sayo; do curl -s -X POST "$D/api/companions/$n/stop" >/dev/null; done
for i in $(seq 1 90); do curl -s "$D/api/companions" | grep -q '"name":"sayo"[^}]*"active":false' && curl -s "$D/api/companions" | grep -q '"name":"chihiro"[^}]*"active":false' && break; sleep 1; done; echo "[smoke14] stopped after ${i}s"
curl -s -X POST "$D/api/shutdown" >/dev/null; for i in $(seq 1 90); do kill -0 $PID 2>/dev/null || break; sleep 1; done
echo "[smoke14] done"
