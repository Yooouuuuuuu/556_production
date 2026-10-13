// Copies the browser VAD assets (silero model, audio worklet, ONNX runtime wasm) into public/vad so
// the renderer bundle ships them. They are fetched from 556d (http://127.0.0.1:55600/vad/...) at
// runtime because wasm/worklet fetches are not allowed from a file:// page.
import { cpSync, mkdirSync, readdirSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const out = path.join(root, 'public', 'vad');
mkdirSync(out, { recursive: true });
let n = 0;
const vad = path.join(root, 'node_modules', '@ricky0123', 'vad-web', 'dist');
for (const f of readdirSync(vad)) {
  if (/\.onnx$/.test(f) || f === 'vad.worklet.bundle.min.js') { cpSync(path.join(vad, f), path.join(out, f)); n++; }
}
const ort = path.join(root, 'node_modules', 'onnxruntime-web', 'dist');
for (const f of readdirSync(ort)) {
  if (/^ort-wasm-simd-threaded\.(wasm|mjs)$/.test(f)) { cpSync(path.join(ort, f), path.join(out, f)); n++; }
}
console.log(`[vad] ${n} assets copied to public/vad`);
