import { app, BrowserWindow, dialog, ipcMain, Menu, nativeImage, safeStorage, shell, Tray } from 'electron'
import path from 'path'
import { BACKEND_BASE_URL, startSidecar, stopSidecar } from './sidecar'

const isDev = !app.isPackaged

let mainWindow: BrowserWindow | null = null
let tray: Tray | null = null
let isWatching = false

// ─── Window ───────────────────────────────────────────────────────────────────

function createWindow(): void {
  mainWindow = new BrowserWindow({
    width: 1200,
    height: 800,
    minWidth: 900,
    minHeight: 600,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
    titleBarStyle: process.platform === 'darwin' ? 'hiddenInset' : 'default',
    show: false,
  })

  if (isDev) {
    mainWindow.loadURL('http://localhost:5173')
    mainWindow.webContents.openDevTools()
  } else {
    mainWindow.loadFile(path.join(__dirname, '../dist/index.html'))
  }

  mainWindow.once('ready-to-show', () => mainWindow?.show())

  // When watching, minimize to tray instead of closing
  mainWindow.on('close', (e) => {
    if (isWatching && tray) {
      e.preventDefault()
      mainWindow?.hide()
    }
  })

  mainWindow.on('closed', () => { mainWindow = null })

  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url)
    return { action: 'deny' }
  })
}

// ─── System tray ──────────────────────────────────────────────────────────────

function createTray(): void {
  // Use a built-in template image on macOS, fallback to empty on other platforms
  const iconPath = path.join(__dirname, '..', 'resources', 'icon.png')
  let icon: Electron.NativeImage
  try {
    icon = nativeImage.createFromPath(iconPath)
    if (icon.isEmpty()) {
      icon = nativeImage.createEmpty()
    }
  } catch {
    icon = nativeImage.createEmpty()
  }

  tray = new Tray(icon)
  tray.setToolTip('FileOrganizer')
  updateTrayMenu()

  tray.on('double-click', () => {
    mainWindow?.show()
    mainWindow?.focus()
  })
}

function updateTrayMenu(): void {
  if (!tray) return
  const menu = Menu.buildFromTemplate([
    {
      label: '打开主窗口',
      click: () => { mainWindow?.show(); mainWindow?.focus() },
    },
    { type: 'separator' },
    {
      label: isWatching ? '停止后台监听' : '后台监听未启动',
      enabled: isWatching,
      click: async () => {
        await backendFetch('/api/watch/stop', { method: 'POST' })
        isWatching = false
        updateTrayMenu()
      },
    },
    { type: 'separator' },
    {
      label: '退出',
      click: () => {
        isWatching = false  // allow window close
        app.quit()
      },
    },
  ])
  tray.setContextMenu(menu)
}

// ─── Backend fetch ─────────────────────────────────────────────────────────────

async function backendFetch(endpoint: string, options?: RequestInit): Promise<unknown> {
  const url = `${BACKEND_BASE_URL}${endpoint}`
  const res = await fetch(url, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  return res.json()
}

function normalizeAiConfig(payload: Record<string, unknown>): Record<string, unknown> {
  const cfg = payload.ai_config as Record<string, unknown> | undefined
  if (!cfg) return payload
  return {
    ...payload,
    ai_config: {
      base_url: cfg.baseUrl ?? cfg.base_url ?? '',
      api_key: cfg.apiKey ?? cfg.api_key ?? '',
      model: cfg.model ?? '',
    },
  }
}

// ─── IPC handlers ─────────────────────────────────────────────────────────────

function registerIpcHandlers(): void {
  ipcMain.handle('backend:health', () => backendFetch('/api/health'))

  ipcMain.handle('backend:scan', (_, config) =>
    backendFetch('/api/scan', { method: 'POST', body: JSON.stringify(config) })
  )
  ipcMain.handle('backend:classify', (_, payload) =>
    backendFetch('/api/classify', { method: 'POST', body: JSON.stringify(normalizeAiConfig(payload)) })
  )
  ipcMain.handle('backend:execute', (_, payload) =>
    backendFetch('/api/execute', { method: 'POST', body: JSON.stringify(normalizeAiConfig(payload)) })
  )

  ipcMain.handle('backend:history', () => backendFetch('/api/history'))
  ipcMain.handle('backend:rollback', (_, operationId: string) =>
    backendFetch('/api/rollback', { method: 'POST', body: JSON.stringify({ operation_id: operationId }) })
  )

  ipcMain.handle('backend:test-connection', (_, config: { baseUrl: string; apiKey: string; model: string }) =>
    backendFetch('/api/test-connection', {
      method: 'POST',
      body: JSON.stringify({ base_url: config.baseUrl, api_key: config.apiKey, model: config.model }),
    })
  )

  ipcMain.handle('backend:watch:start', async (_, payload: Record<string, unknown>) => {
    const result = await backendFetch('/api/watch/start', {
      method: 'POST',
      body: JSON.stringify(normalizeAiConfig(payload)),
    })
    isWatching = true
    updateTrayMenu()
    return result
  })

  ipcMain.handle('backend:watch:stop', async () => {
    const result = await backendFetch('/api/watch/stop', { method: 'POST' })
    isWatching = false
    updateTrayMenu()
    return result
  })

  ipcMain.handle('backend:watch:status', async () => {
    const result = await backendFetch('/api/watch/status') as { watching?: boolean }
    isWatching = result?.watching ?? false
    updateTrayMenu()
    return result
  })

  ipcMain.handle('dialog:selectDirectory', async () => {
    const result = await dialog.showOpenDialog(mainWindow!, { properties: ['openDirectory'] })
    return result.canceled ? null : result.filePaths[0]
  })

  // ─── safeStorage: encrypted API key ───────────────────────────────────────
  ipcMain.handle('settings:set-api-key', (_, plaintext: string) => {
    if (safeStorage.isEncryptionAvailable()) {
      const encrypted = safeStorage.encryptString(plaintext)
      return { encrypted: encrypted.toString('base64'), fallback: false }
    }
    // Fallback: store as-is (Linux without libsecret, etc.)
    return { encrypted: plaintext, fallback: true }
  })

  ipcMain.handle('settings:get-api-key', (_, stored: string, fallback: boolean) => {
    if (!stored) return ''
    if (fallback || !safeStorage.isEncryptionAvailable()) return stored
    try {
      return safeStorage.decryptString(Buffer.from(stored, 'base64'))
    } catch {
      return ''
    }
  })
}

// ─── Graceful shutdown ────────────────────────────────────────────────────────

async function gracefulShutdown(): Promise<void> {
  if (isWatching) {
    try {
      await backendFetch('/api/watch/stop', { method: 'POST' })
    } catch { /* ignore */ }
  }
  stopSidecar()
}

// ─── App lifecycle ────────────────────────────────────────────────────────────

app.whenReady().then(async () => {
  registerIpcHandlers()
  createTray()

  try {
    await startSidecar()
  } catch (err) {
    console.error('Failed to start backend sidecar:', err)
  }

  createWindow()

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow()
    else mainWindow?.show()
  })
})

app.on('will-quit', async (e) => {
  e.preventDefault()
  await gracefulShutdown()
  app.exit(0)
})

app.on('window-all-closed', () => {
  // On macOS keep running in tray if watching; otherwise quit
  if (process.platform !== 'darwin' && !isWatching) {
    app.quit()
  }
})
