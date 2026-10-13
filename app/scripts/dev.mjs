// Dev runner: start vite, wait for it, then start electron pointed at the dev server.
import { spawn } from 'node:child_process';

const vite = spawn('npx', ['vite'], { stdio: 'inherit', shell: true });
const url = 'http://localhost:5173';
for (let i = 0; i < 60; i++) {
  try { await fetch(url); break; } catch { await new Promise((r) => setTimeout(r, 500)); }
}
const electron = spawn('npx', ['electron', '.'], {
  stdio: 'inherit', shell: true, env: { ...process.env, VITE_DEV_SERVER_URL: url },
});
electron.on('exit', () => { vite.kill(); process.exit(0); });
