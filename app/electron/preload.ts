import { contextBridge, ipcRenderer } from 'electron';

// Minimal, explicit bridge — the renderer never sees Node.
contextBridge.exposeInMainWorld('desktop', {
  toggleAvatar: () => ipcRenderer.send('avatar:toggle'),
  dragStart: (x: number, y: number) => ipcRenderer.send('avatar:drag-start', { x, y }),
  dragEnd: () => ipcRenderer.send('avatar:drag-end'),
});

// Avatar window: press anywhere and pull; a 5px threshold keeps taps as taps.
if (window.location.hash.includes('avatar')) {
  window.addEventListener('DOMContentLoaded', () => {
    let grab: { x: number; y: number } | null = null;
    let dragging = false;
    window.addEventListener('pointerdown', (e) => {
      if (e.button !== 0) return;
      grab = { x: e.clientX, y: e.clientY };
      dragging = false;
    }, true);
    window.addEventListener('pointermove', (e) => {
      if (!grab || dragging) return;
      if (Math.abs(e.clientX - grab.x) + Math.abs(e.clientY - grab.y) > 5) {
        dragging = true;
        ipcRenderer.send('avatar:drag-start', grab);
      }
    }, true);
    const end = () => {
      if (dragging) ipcRenderer.send('avatar:drag-end');
      grab = null;
      dragging = false;
    };
    window.addEventListener('pointerup', end, true);
    window.addEventListener('blur', end);
  });
}
