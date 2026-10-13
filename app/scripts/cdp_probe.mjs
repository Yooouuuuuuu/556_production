// Step-logged CDP probe: DOM summary of the Memory tab, then a screenshot. Usage: node cdp_probe.mjs <match> <out.png> [port]
import WebSocket from 'ws';
import fs from 'node:fs';
const [match = 'memory', outfile = 'probe.png', port = '9223'] = process.argv.slice(2);
const targets = await (await fetch(`http://127.0.0.1:${port}/json`)).json();
const page = targets.find((t) => t.type === 'page' && t.url.includes(match));
if (!page) { console.error('no page', targets.map((t) => t.url)); process.exit(1); }
console.log('target', page.url.slice(-40));
const ws = new WebSocket(page.webSocketDebuggerUrl, { maxPayload: 64 * 1024 * 1024 });
let id = 0; const pending = new Map();
const send = (method, params = {}, ms = 15000) => new Promise((resolve, reject) => {
  const mid = ++id; pending.set(mid, { resolve, reject });
  const timer = setTimeout(() => { pending.delete(mid); reject(new Error(`${method} timed out after ${ms} ms`)); }, ms);
  ws.send(JSON.stringify({ id: mid, method, params }));
  pending.get(mid).timer = timer;
});
ws.on('message', (raw) => { const m = JSON.parse(raw); if (m.id && pending.has(m.id)) { const p = pending.get(m.id); clearTimeout(p.timer); pending.delete(m.id); m.error ? p.reject(new Error(m.error.message)) : p.resolve(m.result); } });
await new Promise((r) => ws.on('open', r));
console.log('ws open');
const ev = (expr) => send('Runtime.evaluate', { expression: expr, returnByValue: true }).then((r) => r.result.value);
console.log('title:', await ev('document.title'));
console.log('header:', await ev(`(document.querySelector('main div.text-sm')||{}).innerText`));
console.log('rows:', await ev(`document.querySelectorAll('main ul li').length`), '| first row:', await ev(`(document.querySelector('main ul li p')||{}).innerText`));
console.log('tag chips:', await ev(`document.querySelectorAll('main .rounded-full').length`));
try {
  await send('Page.bringToFront', {}, 5000).catch(() => {});
  await new Promise((r) => setTimeout(r, 800));
  const shot = await send('Page.captureScreenshot', { format: 'png' }, 20000);
  fs.writeFileSync(outfile, Buffer.from(shot.data, 'base64'));
  console.log('saved', outfile, fs.statSync(outfile).size, 'bytes');
} catch (e) { console.log('screenshot failed:', e.message); }
ws.close(); process.exit(0);
