import { contextBridge, ipcRenderer } from 'electron'

export interface BackendAPI {
  getHealth: () => Promise<unknown>
  scanFiles: (config: { paths: string[]; max_size_mb?: number }) => Promise<unknown>
  classify: (payload: unknown) => Promise<unknown>
  execute: (payload: unknown) => Promise<unknown>
  getHistory: () => Promise<unknown>
  rollback: (operationId: string) => Promise<unknown>
  testApiConnection: (config: unknown) => Promise<unknown>
  watchStart: (payload: unknown) => Promise<unknown>
  watchStop: () => Promise<unknown>
  watchStatus: () => Promise<unknown>
  selectDirectory: () => Promise<string | null>
  setApiKey: (plaintext: string) => Promise<{ encrypted: string; fallback: boolean }>
  getApiKey: (stored: string, fallback: boolean) => Promise<string>
}

const api: BackendAPI = {
  getHealth: () => ipcRenderer.invoke('backend:health'),
  scanFiles: (config) => ipcRenderer.invoke('backend:scan', config),
  classify: (payload) => ipcRenderer.invoke('backend:classify', payload),
  execute: (payload) => ipcRenderer.invoke('backend:execute', payload),
  getHistory: () => ipcRenderer.invoke('backend:history'),
  rollback: (id) => ipcRenderer.invoke('backend:rollback', id),
  testApiConnection: (config) => ipcRenderer.invoke('backend:test-connection', config),
  watchStart: (payload) => ipcRenderer.invoke('backend:watch:start', payload),
  watchStop: () => ipcRenderer.invoke('backend:watch:stop'),
  watchStatus: () => ipcRenderer.invoke('backend:watch:status'),
  selectDirectory: () => ipcRenderer.invoke('dialog:selectDirectory'),
  setApiKey: (plaintext) => ipcRenderer.invoke('settings:set-api-key', plaintext),
  getApiKey: (stored, fallback) => ipcRenderer.invoke('settings:get-api-key', stored, fallback),
}

contextBridge.exposeInMainWorld('backend', api)
