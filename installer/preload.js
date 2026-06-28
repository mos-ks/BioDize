// BioDize — Electron preload
// Exposes a minimal, typed surface to the renderer via contextBridge.
// Nothing from Node is leaked; only the listed methods are callable.

'use strict';

const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('biodize', {
  version: () => ipcRenderer.invoke('app:version'),

  installUpdate: () => ipcRenderer.invoke('app:install-update'),

  onUpdateAvailable: (cb) =>
    ipcRenderer.on('update-available', (_evt, info) => cb(info)),

  onUpdateDownloaded: (cb) =>
    ipcRenderer.on('update-downloaded', (_evt, info) => cb(info)),
});
