// Bongo-cat style dragging: press anywhere on the pet and pull. A small
// movement threshold separates drags from taps, so tapping her still plays
// the TapBody motions on the page.
const { ipcRenderer } = require('electron');

window.addEventListener('DOMContentLoaded', () => {
  let grab = null;      // grab point in window coords (CSS px == DIP, frameless)
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
      ipcRenderer.send('pet-drag-start', grab);
    }
  }, true);

  const end = () => {
    if (dragging) ipcRenderer.send('pet-drag-end');
    grab = null;
    dragging = false;
  };
  window.addEventListener('pointerup', end, true);
  window.addEventListener('blur', end);
});
