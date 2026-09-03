const { app, BrowserWindow, ipcMain, shell, dialog } = require('electron');
const path = require('path');
const { spawn } = require('child_process');
const net = require('net');

let mainWindow = null;
let pythonWsProcess = null;
const WS_PORT = 8765;
const REPOSITORY_URL = 'https://github.com/hunterv9/Dowloadapi';
const hasSingleInstanceLock = app.requestSingleInstanceLock();

// ── Auto-update ─────────────────────────────────────────────────────────────
let autoUpdater;
try {
  autoUpdater = require('electron-updater').autoUpdater;
  autoUpdater.autoDownload = false;
  autoUpdater.autoInstallOnAppQuit = true;
} catch (e) {
  console.log('[AutoUpdate]: electron-updater not available');
}

function isWebSocketBackendRunning() {
  return new Promise((resolve) => {
    const socket = net.createConnection({ host: '127.0.0.1', port: WS_PORT });
    socket.once('connect', () => {
      socket.destroy();
      resolve(true);
    });
    socket.once('error', () => resolve(false));
  });
}

async function startPythonWsBackend() {
  if (await isWebSocketBackendRunning()) {
    console.log(`[Python WS]: Reusing existing backend on port ${WS_PORT}`);
    return;
  }

  const appRoot = app.isPackaged
    ? path.join(process.resourcesPath, 'app.asar.unpacked')
    : path.join(__dirname, '..');

  if (app.isPackaged) {
    // Use bundled Python executable (PyInstaller output)
    const backendExe = path.join(appRoot, 'tiktok-backend.exe');
    pythonWsProcess = spawn(backendExe, [], {
      cwd: appRoot,
      windowsHide: true
    });
  } else {
    // Development: use system Python
    const backendScript = path.join(appRoot, 'desktop', 'ws_server.py');
    pythonWsProcess = spawn('python', [backendScript], {
      cwd: appRoot,
      windowsHide: true
    });
  }

  pythonWsProcess.on('error', (error) => {
    console.error(`[Python WS Err]: ${error.message}`);
  });

  pythonWsProcess.on('exit', (code) => {
    if (code && mainWindow && !mainWindow.isDestroyed()) {
      console.error(`[Python WS Err]: backend exited with code ${code}`);
    }
  });

  pythonWsProcess.stdout.on('data', (data) => {
    console.log(`[Python WS]: ${data}`);
  });

  pythonWsProcess.stderr.on('data', (data) => {
    console.error(`[Python WS Err]: ${data}`);
  });

  // Wait for backend to be ready (up to 10 seconds)
  const maxWait = 10000;
  const interval = 200;
  let waited = 0;
  while (waited < maxWait) {
    if (await isWebSocketBackendRunning()) {
      console.log(`[Python WS]: Backend ready after ${waited}ms`);
      return;
    }
    await new Promise(r => setTimeout(r, interval));
    waited += interval;
  }
  console.error(`[Python WS]: Backend not ready after ${maxWait}ms, proceeding anyway`);
}

function stopPythonWsBackend() {
  if (pythonWsProcess && !pythonWsProcess.killed) {
    pythonWsProcess.kill();
    pythonWsProcess = null;
  }
}

ipcMain.handle('open-repository', () => shell.openExternal(REPOSITORY_URL));

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1240,
    height: 820,
    minWidth: 980,
    minHeight: 650,
    frame: false, // Frameless window with custom controls in the shared UI
    backgroundColor: '#ffffff',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      nodeIntegration: false,
      contextIsolation: true
    },
    show: false
  });

  // Load the Desktop UI directly from static files
  const indexPath = path.join(__dirname, '..', 'web', 'static', 'index.html');
  mainWindow.loadFile(indexPath);

  mainWindow.once('ready-to-show', () => {
    mainWindow.show();
  });

  // Handle window control IPC
  ipcMain.on('window-minimize', () => {
    if (mainWindow) mainWindow.minimize();
  });

  ipcMain.on('window-maximize', () => {
    if (mainWindow) {
      if (mainWindow.isMaximized()) {
        mainWindow.unmaximize();
      } else {
        mainWindow.maximize();
      }
    }
  });

  ipcMain.on('window-close', () => {
    if (mainWindow) mainWindow.close();
  });
}

if (!hasSingleInstanceLock) {
  app.quit();
} else {
  app.on('second-instance', () => {
    if (mainWindow) {
      if (mainWindow.isMinimized()) mainWindow.restore();
      mainWindow.focus();
    }
  });

  app.whenReady().then(async () => {
    await startPythonWsBackend();
    createWindow();

    // Check for updates after window is shown
    if (autoUpdater && app.isPackaged) {
      autoUpdater.checkForUpdates().catch(() => {});
      autoUpdater.on('update-available', (info) => {
        dialog.showMessageBox(mainWindow, {
          type: 'info',
          title: 'Cập nhật mới',
          message: `Có phiên bản mới v${info.version}`,
          detail: 'Bạn có muốn tải xuống và cài đặt không?',
          buttons: ['Tải ngay', 'Để sau'],
        }).then(({ response }) => {
          if (response === 0) autoUpdater.downloadUpdate();
        });
      });
      autoUpdater.on('update-downloaded', () => {
        dialog.showMessageBox(mainWindow, {
          type: 'info',
          title: 'Sẵn sàng cài đặt',
          message: 'Đã tải xong bản cập nhật. Khởi động lại để áp dụng.',
          buttons: ['Khởi động lại', 'Để sau'],
        }).then(({ response }) => {
          if (response === 0) autoUpdater.quitAndInstall();
        });
      });
    }

    app.on('activate', () => {
      if (BrowserWindow.getAllWindows().length === 0) createWindow();
    });
  });
}

app.on('window-all-closed', () => {
  stopPythonWsBackend();
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

app.on('before-quit', () => {
  stopPythonWsBackend();
});
