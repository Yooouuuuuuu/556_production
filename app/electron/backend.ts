// Owns the 556d backend: spawn it from the repo root (dev) or resources (packaged), wait for
// health, and on quit ask it to shut down (companions finish up so no memory write is lost),
// killing only if it does not exit in time. If a 556d is already serving :55600 (started by
// hand), attach to it instead and leave it running on quit.
import { spawn, ChildProcess } from 'node:child_process';
import path from 'node:path';
import { app } from 'electron';

const HEALTH = 'http://127.0.0.1:55600/api/status';

export class Backend {
  private child: ChildProcess | null = null;
  attached = false;

  repoRoot(): string {
    return app.isPackaged ? process.resourcesPath : path.resolve(__dirname, '..', '..');
  }

  async isUp(): Promise<boolean> {
    try {
      const r = await fetch(HEALTH, { signal: AbortSignal.timeout(1500) });
      return r.ok;
    } catch {
      return false;
    }
  }

  async start(): Promise<void> {
    if (await this.isUp()) {
      this.attached = true;
      console.log('[backend] attached to a running 556d');
      return;
    }
    const root = this.repoRoot();
    const exe = path.join(root, '556d.exe');
    this.child = spawn(exe, ['-parent-pid', String(process.pid)], {
      cwd: root,
      stdio: ['ignore', 'pipe', 'pipe'],
      windowsHide: true,
    });
    this.child.stdout?.on('data', (b) => process.stdout.write(`[556d] ${b}`));
    this.child.stderr?.on('data', (b) => process.stdout.write(`[556d] ${b}`));
    this.child.on('exit', (code) => console.log(`[backend] 556d exited (${code})`));
    for (let i = 0; i < 60; i++) {
      if (await this.isUp()) {
        console.log('[backend] 556d ready');
        return;
      }
      await new Promise((r) => setTimeout(r, 500));
    }
    throw new Error('556d did not become healthy within 30s');
  }

  /** Graceful: POST /api/shutdown, wait for the process to exit (companions drain ≤ 60 s + kill), then kill as a last resort. */
  async stop(): Promise<void> {
    const child = this.child;
    if (!child || this.attached) return;
    this.child = null;
    const exited = new Promise<void>((res) => { if (child.exitCode !== null) res(); else child.once('exit', () => res()); });
    try {
      await fetch('http://127.0.0.1:55600/api/shutdown', { method: 'POST', signal: AbortSignal.timeout(3000) });
    } catch {
      /* not answering: kill below */
    }
    const clean = await Promise.race([exited.then(() => true), new Promise<boolean>((r) => setTimeout(() => r(false), 80_000))]);
    if (!clean) {
      console.log('[backend] 556d did not exit in time; killing');
      child.kill();
    }
  }
}
