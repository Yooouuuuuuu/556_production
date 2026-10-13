// Diagnostic: subscribe to the 556d hub WebSocket, send a chat via HTTP as client "probe",
// and print every hub event until chat.complete. Usage: node hub_probe.mjs [text]
import WebSocket from 'ws';

const base = 'http://127.0.0.1:55600';
const text = process.argv[2] || '一句話：你記得我的貓叫什麼嗎？';
const ws = new WebSocket('ws://127.0.0.1:55600/ws');
const timer = setTimeout(() => { console.log('TIMEOUT'); process.exit(1); }, 180000);

ws.on('open', async () => {
  console.log('ws open');
  const r = await fetch(`${base}/api/chat`, {
    method: 'POST',
    headers: { 'content-type': 'application/json', 'X-556-Client': 'probe' },
    body: JSON.stringify({ model: '556', stream: false, messages: [{ role: 'user', content: text }] }),
  });
  const j = await r.json();
  console.log('http reply:', j.choices?.[0]?.message?.content ?? j);
});
ws.on('message', (data) => {
  const ev = JSON.parse(data.toString());
  const short = ev.type === 'chat.delta' ? `chat.delta "${ev.text}"` : JSON.stringify(ev).slice(0, 160);
  console.log('event:', short);
  if (ev.type === 'chat.complete') { clearTimeout(timer); setTimeout(() => process.exit(0), 300); }
});
ws.on('error', (e) => { console.log('ws error:', e.message); process.exit(1); });
