const { app, BrowserWindow, dialog, ipcMain } = require('electron');
const fs = require('node:fs/promises');
const path = require('node:path');

const imageFilters = [
  { name: 'Metallographic images', extensions: ['png', 'jpg', 'jpeg', 'tif', 'tiff', 'bmp'] },
];

function createWindow() {
  const window = new BrowserWindow({
    width: 1440,
    height: 900,
    minWidth: 1050,
    minHeight: 680,
    backgroundColor: '#101820',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });
  window.loadFile('index.html');
}

app.whenReady().then(() => {
  ipcMain.handle('open-image', async () => {
    const result = await dialog.showOpenDialog({ properties: ['openFile'], filters: imageFilters });
    if (result.canceled || !result.filePaths[0]) return null;
    const filePath = result.filePaths[0];
    const data = await fs.readFile(filePath);
    return {
      name: path.basename(filePath),
      extension: path.extname(filePath).slice(1).toUpperCase(),
      data: data.buffer.slice(data.byteOffset, data.byteOffset + data.byteLength),
    };
  });

  ipcMain.handle('save-enhanced-png', async (_event, { data, suggestedName }) => {
    const result = await dialog.showSaveDialog({
      defaultPath: suggestedName,
      filters: [{ name: 'PNG image', extensions: ['png'] }],
    });
    if (result.canceled || !result.filePath) return false;
    await fs.writeFile(result.filePath, Buffer.from(data));
    return true;
  });
  createWindow();
});

app.on('window-all-closed', () => { if (process.platform !== 'darwin') app.quit(); });
app.on('activate', () => { if (BrowserWindow.getAllWindows().length === 0) createWindow(); });
