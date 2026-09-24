const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('desktopAPI', {
  openImage: () => ipcRenderer.invoke('open-image'),
  saveEnhancedPng: (payload) => ipcRenderer.invoke('save-enhanced-png', payload),
});
