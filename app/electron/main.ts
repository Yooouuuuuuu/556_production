// 556 Production — Electron main: single instance, backend lifecycle, tray, two windows.
//   office window  (#/office): chat + settings — closing it quits the app (and the backend)
//   avatar window  (#/avatar): transparent, frameless, always-on-top, drag-anywhere; toggled
import { app, BrowserWindow, ipcMain, Menu, Tray, nativeImage, screen } from 'electron';
import path from 'node:path';
import { Backend } from './backend';

const backend = new Backend();
let office: BrowserWindow | null = null;
let avatar: BrowserWindow | null = null;
let tray: Tray | null = null;
let quitting = false;

const DEV_URL = process.env.VITE_DEV_SERVER_URL;
function pageURL(route: string): string {
  return DEV_URL ? `${DEV_URL}#/${route}` : `file://${path.join(__dirname, '..', 'dist', 'index.html')}#/${route}`;
}

if (!app.requestSingleInstanceLock()) {
  app.quit();
} else {
  app.on('second-instance', () => showOffice());
  app.whenReady().then(boot);
}

async function boot() {
  createTray();
  createOffice();
  try {
    await backend.start();
  } catch (e) {
    console.error(e);
  }
  // avatar visibility on start follows the user setting (default: shown)
  try {
    const r = await fetch('http://127.0.0.1:55600/api/settings');
    const j = await r.json();
    if (j?.settings?.show_avatar_on_start) showAvatar();
  } catch {
    /* backend not up yet: the office window shows the status */
  }
}

const appIcon = () => nativeImage.createFromPath(path.join(__dirname, '..', 'assets', 'icon.png'));

function createOffice() {
  office = new BrowserWindow({
    width: 980,
    height: 720,
    minWidth: 640,
    minHeight: 480,
    title: '556 Production',
    icon: appIcon(),
    backgroundColor: '#14141c',
    webPreferences: { preload: path.join(__dirname, 'preload.js'), contextIsolation: true },
  });
  office.setMenuBarVisibility(false);
  office.loadURL(pageURL('office'));
  office.on('minimize', () => office?.hide()); // minimize → tray
  office.on('close', () => { quitting = true; });  // close → quit everything
  office.on('closed', () => { office = null; app.quit(); });
}

function showOffice() {
  if (!office) createOffice();
  office!.show();
  office!.focus();
}

function showAvatar() {
  if (avatar) {
    avatar.show();
    return;
  }
  const { workArea } = screen.getPrimaryDisplay();
  avatar = new BrowserWindow({
    width: 420,
    height: 640,
    x: workArea.x + workArea.width - 440,
    y: workArea.y + workArea.height - 660,
    transparent: true,
    frame: false,
    alwaysOnTop: true,
    hasShadow: false,
    resizable: true,
    skipTaskbar: true,
    title: '556 Production — companion',
    webPreferences: { preload: path.join(__dirname, 'preload.js'), contextIsolation: true, backgroundThrottling: false },
  });
  avatar.setMenu(null);
  avatar.loadURL(pageURL('avatar'));
  // She is toggled, never closed: Alt+F4 / WM_CLOSE on the avatar just hides it.
  avatar.on('close', (e) => { if (!quitting) { e.preventDefault(); avatar?.hide(); } });
  avatar.on('closed', () => { avatar = null; });
}

function toggleAvatar() {
  if (avatar && avatar.isVisible()) avatar.hide();
  else showAvatar();
}

function createTray() {
  const icon = nativeImage.createFromPath(path.join(__dirname, '..', 'assets', 'tray.png'));
  tray = new Tray(icon.isEmpty() ? nativeImage.createEmpty() : icon);
  tray.setToolTip('556 Production');
  tray.setContextMenu(Menu.buildFromTemplate([
    { label: '開啟 556 Production', click: showOffice },
    { label: '顯示／隱藏她', click: toggleAvatar },
    { type: 'separator' },
    { label: '結束', click: () => { quitting = true; app.quit(); } },
  ]));
  tray.on('click', showOffice);
}

// Bongo-cat drag for the avatar window (grab anywhere; taps still reach the page)
let dragTimer: NodeJS.Timeout | null = null;
ipcMain.on('avatar:drag-start', (_e, off: { x: number; y: number }) => {
  if (dragTimer) clearInterval(dragTimer);
  dragTimer = setInterval(() => {
    if (!avatar) return;
    const p = screen.getCursorScreenPoint();
    avatar.setPosition(p.x - off.x, p.y - off.y);
  }, 16);
});
ipcMain.on('avatar:drag-end', () => { if (dragTimer) { clearInterval(dragTimer); dragTimer = null; } });
ipcMain.on('avatar:toggle', toggleAvatar);

app.on('will-quit', () => backend.stop());
app.on('window-all-closed', () => { if (quitting) app.quit(); });
