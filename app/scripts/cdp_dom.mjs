// Diagnostic: evaluate JS in a running Electron page and print the result (JSON). Also reports
// uncaught exceptions seen while connected. Usage: node cdp_dom.mjs <urlMatch> "<js expression>" [port]
import WebSocket from 'ws';

const [match = 'office', expr = 'document.title', port = '9223'] = process.argv.slice(2);
const targets = await (await fetch(`http://127.0.0.1:${port}/json`)).json();
const page = targets.find((t) => t.type === 'page' && t.url.includes(match));
if (!page) { console.error('no page matching', match, targets.map((t) => t.url)); process.exit(1); }
const ws = new WebSocket(page.webSocketDebuggerUrl, { maxPayload: 64 * 1024 * 1024 });
let id = 0; const pending = new Map();
const send = (method, params = {}, ms = 15000) => new Promise((resolve, reject) => {
  const mid = ++id; const timer = setTimeout(() => { pending.delete(mid); reject(new Error(`${method} timed out`)); }, ms);
  pending.set(mid, { resolve, reject, timer }); ws.send(JSON.stringify({ id: mid, method, params }));
});
ws.on('message', (raw) => {
  const m = JSON.parse(raw);
  if (m.id && pending.has(m.id)) { const p = pending.get(m.id); clearTimeout(p.timer); pending.delete(m.id); m.error ? p.reject(new Error(m.error.message)) : p.resolve(m.result); }
  else if (m.method === 'Runtime.exceptionThrown') console.log('EXCEPTION:', m.params.exceptionDetails.text, m.params.exceptionDetails.exception?.description?.slice(0, 300));
  else if (m.method === 'Runtime.consoleAPICalled' && m.params.type === 'error') console.log('CONSOLE.ERROR:', m.params.args.map((a) => a.value ?? a.description).join(' ').slice(0, 300));
});
await new Promise((r) => ws.on('open', r));
await send('Runtime.enable');
const r = await send('Runtime.evaluate', { expression: expr, returnByValue: true, awaitPromise: true });
if (r.exceptionDetails) console.log('EVAL EXCEPTION:', r.exceptionDetails.exception?.description ?? r.exceptionDetails.text);
else console.log(JSON.stringify(r.result.value, null, 1));
await new Promise((r) => setTimeout(r, 800));
ws.close(); process.exit(0);
