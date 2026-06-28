// BioDize — Electron main process
//
// Starts the frozen FastAPI backend, serves the built React frontend via a
// local HTTP server, waits for the backend to be healthy, then loads the app.
// On exit, kills the backend process cleanly.

'use strict';

const { app, BrowserWindow, ipcMain, dialog } = require('electron');
const { autoUpdater } = require('electron-updater');
const path  = require('path');
const http  = require('http');
const fs    = require('fs');
const { spawn } = require('child_process');

// Ports used exclusively by this app — high enough to avoid collisions.
const BACKEND_PORT  = 48721;
const FRONTEND_PORT = 48720;

let mainWindow    = null;
let backendProcess  = null;
let frontendServer  = null;

// ── Path helpers ──────────────────────────────────────────────────────────────

function rp(...parts) {
  // Returns a path inside the app's resources directory (packaged) or the
  // repo root (development, for iterating without rebuilding the installer).
  if (app.isPackaged) return path.join(process.resourcesPath, ...parts);
  return path.join(__dirname, '..', ...parts);
}

function backendExe() {
  const ext = process.platform === 'win32' ? '.exe' : '';
  return rp('backend', `biodize-backend${ext}`);
}

// ── Frontend static server ────────────────────────────────────────────────────

const MIME_MAP = {
  '.html': 'text/html; charset=utf-8',
  '.js':   'application/javascript',
  '.mjs':  'application/javascript',
  '.css':  'text/css',
  '.json': 'application/json',
  '.png':  'image/png',
  '.jpg':  'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.svg':  'image/svg+xml',
  '.ico':  'image/x-icon',
  '.woff': 'font/woff',
  '.woff2':'font/woff2',
  '.ttf':  'font/ttf',
  '.otf':  'font/otf',
  '.map':  'application/json',
};

function startFrontendServer() {
  return new Promise((resolve, reject) => {
    const dir = rp('frontend');
    const srv = http.createServer((req, res) => {
      const urlPath  = req.url.split('?')[0].split('#')[0];
      let   filePath = path.join(dir, urlPath);

      // SPA: unknown paths get index.html so React Router handles them.
      if (!fs.existsSync(filePath) || fs.statSync(filePath).isDirectory()) {
        filePath = path.join(dir, 'index.html');
      }

      const ext = path.extname(filePath).toLowerCase();
      fs.readFile(filePath, (err, data) => {
        if (err) { res.writeHead(404); res.end('Not found'); return; }
        res.writeHead(200, {
          'Content-Type': MIME_MAP[ext] || 'application/octet-stream',
          'Cache-Control': 'no-cache',
          'X-Content-Type-Options': 'nosniff',
        });
        res.end(data);
      });
    });

    srv.on('error', reject);
    srv.listen(FRONTEND_PORT, '127.0.0.1', () => resolve(srv));
  });
}

// ── Backend process ───────────────────────────────────────────────────────────

function startBackend() {
  const exe = backendExe();
  if (!fs.existsSync(exe)) {
    console.warn('[backend] executable not found at', exe, '— skipping (dev mode?)');
    return null;
  }

  const dataDir = path.join(app.getPath('userData'), 'data');
  fs.mkdirSync(path.join(dataDir, 'var'), { recursive: true });

  const samplePdf = rp('data', 'scanned_batch_documentation.pdf');

  const proc = spawn(exe, [], {
    env: {
      ...process.env,
      PORT:             String(BACKEND_PORT),
      HOST:             '127.0.0.1',
      LOG_LEVEL:        'warning',
      DATABASE_URL:     `sqlite:///${path.join(dataDir, 'biodize.db')}`,
      STORAGE_DIR:      path.join(dataDir, 'var'),
      SAMPLE_PDF_PATH:  fs.existsSync(samplePdf) ? samplePdf : '',
    },
    cwd: path.dirname(exe),
  });

  proc.stdout.on('data', d => process.stdout.write('[backend] ' + d));
  proc.stderr.on('data', d => process.stderr.write('[backend] ' + d));
  proc.on('exit', code => {
    console.log(`[backend] exited (code ${code})`);
    backendProcess = null;
  });

  return proc;
}

function waitForBackend(timeoutMs = 45000) {
  return new Promise((resolve, reject) => {
    const deadline = Date.now() + timeoutMs;
    function check() {
      const req = http.get(`http://127.0.0.1:${BACKEND_PORT}/health`, res => {
        res.resume();
        if (res.statusCode === 200) resolve();
        else retry();
      });
      req.on('error', retry);
      req.setTimeout(900, () => { req.destroy(); retry(); });
    }
    function retry() {
      if (Date.now() > deadline) {
        reject(new Error(
          `The BioDize backend did not respond within ${timeoutMs / 1000} seconds.\n` +
          `Executable: ${backendExe()}`
        ));
        return;
      }
      setTimeout(check, 700);
    }
    check();
  });
}

// ── Auto-updater ──────────────────────────────────────────────────────────────

autoUpdater.autoDownload         = true;
autoUpdater.autoInstallOnAppQuit = true;
autoUpdater.allowPrerelease      = false;
autoUpdater.verifyUpdateCodeSignature = false;

autoUpdater.on('update-available',  info => { if (mainWindow) mainWindow.webContents.send('update-available',  info); });
autoUpdater.on('update-downloaded', info => {
  if (mainWindow) mainWindow.webContents.send('update-downloaded', info);
  setTimeout(() => { try { autoUpdater.quitAndInstall(false, true); } catch (_) {} }, 8000);
});
autoUpdater.on('error', () => {}); // non-fatal

// ── Window ────────────────────────────────────────────────────────────────────

function createWindow() {
  mainWindow = new BrowserWindow({
    width:           1440,
    height:          900,
    minWidth:        1024,
    minHeight:       700,
    backgroundColor: '#0f172a',
    show:            false,
    autoHideMenuBar: true,
    title:           'BioDize',
    icon:            path.join(__dirname, 'build', 'icon.png'),
    webPreferences: {
      preload:          path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration:  false,
      sandbox:          false,
    },
  });

  mainWindow.setMenuBarVisibility(false);
  mainWindow.loadFile(path.join(__dirname, 'loading.html'));
  mainWindow.once('ready-to-show', () => mainWindow.show());
  mainWindow.on('closed', () => { mainWindow = null; });
}

// ── App lifecycle ─────────────────────────────────────────────────────────────

app.whenReady().then(async () => {
  createWindow();

  try {
    frontendServer = await startFrontendServer();
    backendProcess = startBackend();

    if (backendProcess) {
      await waitForBackend();
    }

    if (mainWindow) {
      mainWindow.loadURL(`http://127.0.0.1:${FRONTEND_PORT}/`);
    }

    // Check for updates shortly after launch, then every 15 min.
    setTimeout(() => autoUpdater.checkForUpdates().catch(() => {}), 10000);
    setInterval(()  => autoUpdater.checkForUpdates().catch(() => {}), 15 * 60 * 1000);

  } catch (err) {
    console.error('[startup]', err);
    dialog.showErrorBox(
      'BioDize failed to start',
      `The backend could not be initialised:\n\n${err.message}\n\nPlease restart the application.`
    );
    app.quit();
  }

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

function cleanup() {
  if (frontendServer) { try { frontendServer.close(); } catch (_) {} frontendServer = null; }
  if (backendProcess) { try { backendProcess.kill();  } catch (_) {} backendProcess  = null; }
}

app.on('window-all-closed', () => {
  cleanup();
  if (process.platform !== 'darwin') app.quit();
});

app.on('will-quit', cleanup);
app.on('before-quit', cleanup);

// ── IPC ───────────────────────────────────────────────────────────────────────

ipcMain.handle('app:version',        () => app.getVersion());
ipcMain.handle('app:install-update', () => { try { autoUpdater.quitAndInstall(false, true); } catch (_) {} });
