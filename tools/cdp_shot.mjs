// Screenshot a URL via CDP against a real (non-headless) Chrome — real GPU pipeline.
// Usage: node cdp_shot.mjs <url> <outfile.png> [waitMs]
import WebSocket from 'ws';
import fs from 'node:fs';

const [url, outfile, waitMs = '6000'] = process.argv.slice(2);

const targets = await (await fetch('http://127.0.0.1:9222/json')).json();
const page = targets.find(t => t.type === 'page');
if (!page) { console.error('no page target'); process.exit(1); }

const ws = new WebSocket(page.webSocketDebuggerUrl, { maxPayload: 64 * 1024 * 1024 });
let id = 0;
const pending = new Map();
function send(method, params = {}) {
  return new Promise((resolve, reject) => {
    const mid = ++id;
    pending.set(mid, { resolve, reject });
    ws.send(JSON.stringify({ id: mid, method, params }));
  });
}
ws.on('message', raw => {
  const msg = JSON.parse(raw);
  if (msg.id && pending.has(msg.id)) {
    const { resolve, reject } = pending.get(msg.id);
    pending.delete(msg.id);
    msg.error ? reject(new Error(msg.error.message)) : resolve(msg.result);
  }
});
await new Promise(r => ws.on('open', r));

await send('Page.enable');
await send('Emulation.setDeviceMetricsOverride', { width: 700, height: 900, deviceScaleFactor: 1, mobile: false });
await send('Page.navigate', { url });
await new Promise(r => setTimeout(r, Number(waitMs)));
const shot = await send('Page.captureScreenshot', { format: 'png' });
fs.writeFileSync(outfile, Buffer.from(shot.data, 'base64'));
console.log('saved', outfile, fs.statSync(outfile).size, 'bytes');
ws.close();
process.exit(0);
