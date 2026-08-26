const { contextBridge, ipcRenderer, shell } = require('electron');

// Expose safe API to the renderer process (web UI)
contextBridge.exposeInMainWorld('electronAPI', {
  isElectron: true,
  minimize: () => ipcRenderer.send('window-minimize'),
  maximize: () => ipcRenderer.send('window-maximize'),
  close: () => ipcRenderer.send('window-close'),
  openExternal: () => ipcRenderer.invoke('open-repository'),
  openPath: (path) => shell.openPath(path),
  showItemInFolder: (path) => shell.showItemInFolder(path)
});
