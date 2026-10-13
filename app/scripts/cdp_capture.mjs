// Diagnostic: screenshot an EXISTING Electron page via the app's remote-debugging port
// (launch the app with --remote-debugging-port=9223). Picks the target whose URL contains
// <match>; with <hash> it first navigates that page to `#/<hash>` and waits.
// Usage: node cdp_capture.mjs <match> <outfile.png> [port] [hash]
import WebSocket from 'ws';
import fs from 'node:fs';

const [match = 'office', outfile = 'capture.png', port = '9223', hash = ''] = process.argv.slice(2);
const targets = await (await fetch(`http://127.0.0.1:${port}/json`)).json();
const page = targets.find((t) => t.type === 'page' && t.url.includes(match));
if (!page) { console.error('no page matching', match, targets.map((t) => t.url)); process.exit(1); }

const ws = new WebSocket(page.webSocketDebuggerUrl, { maxPayload: 64 * 1024 * 1024 });
let id = 0;
const pending = new Map();
const send = (method, params = {}) => new Promise((resolve, reject) => {
  const mid = ++id;
  pending.set(mid, { resolve, reject });
  ws.send(JSON.stringify({ id: mid, method, params }));
});
ws.on('message', (raw) => {
  const msg = JSON.parse(raw);
  if (msg.id && pending.has(msg.id)) {
    const { resolve, reject } = pending.get(msg.id);
    pending.delete(msg.id);
    msg.error ? reject(new Error(msg.error.message)) : resolve(msg.result);
  }
});
await new Promise((r) => ws.on('open', r));
if (hash) {
  const base = page.url.split('#')[0];
  await send('Page.navigate', { url: `${base}?r=${Date.now()}#/${hash}` }); // query change forces a real reload
  await new Promise((r) => setTimeout(r, 2500));
}
const shot = await send('Page.captureScreenshot', { format: 'png' });
fs.writeFileSync(outfile, Buffer.from(shot.data, 'base64'));
console.log('saved', outfile, fs.statSync(outfile).size, 'bytes');
ws.close();
process.exit(0);
