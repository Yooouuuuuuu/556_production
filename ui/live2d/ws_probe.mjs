// Diagnostic: connect to a bridge WebSocket, trigger /api/message over HTTP, and print
// the broadcast the viewer would receive. Usage: node ws_probe.mjs <wsUrl> <httpBase>
import WebSocket from 'ws';

const [wsUrl = 'ws://127.0.0.1:55600/ws', httpBase = 'http://127.0.0.1:55600'] = process.argv.slice(2);
const ws = new WebSocket(wsUrl);
const timer = setTimeout(() => { console.log('TIMEOUT: no broadcast received'); process.exit(1); }, 8000);

ws.on('open', async () => {
  console.log('ws open:', wsUrl);
  const r = await fetch(`${httpBase}/api/message?text=${encodeURIComponent('WS 測試 ok')}&duration=1500`);
  console.log('http ack:', await r.text());
});
ws.on('message', (data) => {
  console.log('broadcast:', data.toString());
  clearTimeout(timer);
  ws.close();
  process.exit(0);
});
ws.on('error', (e) => { console.log('ws error:', e.message); process.exit(1); });
