const { app, BrowserWindow, ipcMain, shell } = require('electron');
const path = require('path');
const { spawn } = require('child_process');

let mainWindow = null;
let pythonWsProcess = null;
const WS_PORT = 8765;

function startPythonWsBackend() {
  // Start dedicated Python WebSocket Server (Zero FastAPI needed in Desktop App)
  pythonWsProcess = spawn('python', ['desktop/ws_server.py'], {
    cwd: path.join(__dirname, '..'),
    shell: true
  });

  pythonWsProcess.stdout.on('data', (data) => {
    console.log(`[Python WS]: ${data}`);
  });

  pythonWsProcess.stderr.on('data', (data) => {
    console.error(`[Python WS Err]: ${data}`);
  });
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1240,
    height: 820,
    minWidth: 980,
    minHeight: 650,
    frame: false, // Frameless for custom modern dark titlebar
    backgroundColor: '#090c15',
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

app.whenReady().then(() => {
  startPythonWsBackend();
  createWindow();

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on('window-all-closed', () => {
  if (pythonWsProcess) {
    pythonWsProcess.kill();
  }
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

app.on('before-quit', () => {
  if (pythonWsProcess) {
    pythonWsProcess.kill();
  }
});
