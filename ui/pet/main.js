// Desktop pet shell: transparent, frameless, always-on-top window showing the
// Live2D viewer in embed mode — the Bongo-cat presentation of the same page.
// Drag: grab her anywhere and pull (preload.js sends drag start/end over IPC;
// a 60fps loop pins the original grab point under the cursor). Alt+F4 closes.
const { app, BrowserWindow, ipcMain, screen } = require('electron');
const path = require('node:path');

let win = null;
let dragTimer = null;

function startDrag(offset) {
  stopDrag();
  dragTimer = setInterval(() => {
    if (!win || win.isDestroyed()) return stopDrag();
    const p = screen.getCursorScreenPoint();
    win.setPosition(p.x - offset.x, p.y - offset.y);
  }, 16);
}

function stopDrag() {
  if (dragTimer) {
    clearInterval(dragTimer);
    dragTimer = null;
  }
}

app.whenReady().then(() => {
  win = new BrowserWindow({
    width: 420,
    height: 640,
    transparent: true,
    frame: false,
    alwaysOnTop: true,
    hasShadow: false,
    resizable: true,
    title: '556 Production',
    webPreferences: {
      backgroundThrottling: false,
      preload: path.join(__dirname, 'preload.js'),
    },
  });
  win.setMenu(null);
  win.loadURL('http://127.0.0.1:55600/index.html?embed=1'); // served by 556d
});

ipcMain.on('pet-drag-start', (_e, offset) => startDrag(offset));
ipcMain.on('pet-drag-end', () => stopDrag());

app.on('window-all-closed', () => app.quit());
