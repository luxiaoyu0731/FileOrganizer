import { useCallback, useEffect, useState } from 'react'

export interface AiConfig {
  baseUrl: string
  apiKey: string
  model: string
}

export interface Settings {
  scanPaths: string[]
  archivePath: string
  renameStrategy: 'semantic_date' | 'date_prefix' | 'preserve_original'
  maxSizeMb: number
  aiConfig: AiConfig
}

// On-disk shape: apiKey is encrypted (Electron) or plain (browser dev)
interface StoredAiConfig {
  baseUrl: string
  encryptedKey: string
  keyFallback: boolean  // true = safeStorage unavailable, stored as plaintext
  model: string
}

interface StoredSettings {
  scanPaths: string[]
  archivePath: string
  renameStrategy: 'semantic_date' | 'date_prefix' | 'preserve_original'
  maxSizeMb: number
  aiConfig: StoredAiConfig
}

const STORAGE_KEY = 'fileorganizer_settings'

const DEFAULT_STORED: StoredSettings = {
  scanPaths: [],
  archivePath: '',
  renameStrategy: 'semantic_date',
  maxSizeMb: 500,
  aiConfig: { baseUrl: '', encryptedKey: '', keyFallback: true, model: '' },
}

// Running inside Electron with safeStorage IPC exposed?
const isElectron = typeof window !== 'undefined' && typeof (window as Record<string, unknown>).backend === 'object'
  && typeof (window as { backend?: { setApiKey?: unknown } }).backend?.setApiKey === 'function'

/** Remove any accidental surrounding quotes from a path string. */
function cleanPath(p: unknown): string {
  if (typeof p !== 'string') return ''
  // Strip leading/trailing " or ' that can appear from double-JSON-serialisation
  return p.replace(/^["']+|["']+$/g, '').trim()
}

function loadStored(): StoredSettings {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return DEFAULT_STORED
    const p = JSON.parse(raw) as Partial<StoredSettings>
    const base = { ...DEFAULT_STORED, ...p, aiConfig: { ...DEFAULT_STORED.aiConfig, ...p.aiConfig } }
    // Sanitise paths that may have been double-serialised (e.g. '"/some/path"')
    base.archivePath = cleanPath(base.archivePath)
    base.scanPaths = (base.scanPaths ?? []).map(cleanPath).filter(Boolean)
    return base
  } catch {
    return DEFAULT_STORED
  }
}

function saveStored(s: StoredSettings) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(s))
}

export function useSettings() {
  const [stored, setStored] = useState<StoredSettings>(loadStored)
  const [apiKey, setApiKeyState] = useState('')
  const [ready, setReady] = useState(!isElectron)

  // Decrypt stored key on mount
  useEffect(() => {
    if (!isElectron) {
      setApiKeyState(stored.aiConfig.encryptedKey)
      setReady(true)
      return
    }
    window.backend.getApiKey(stored.aiConfig.encryptedKey, stored.aiConfig.keyFallback)
      .then((k) => { setApiKeyState(k as string); setReady(true) })
      .catch(() => setReady(true))
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const settings: Settings = {
    scanPaths: stored.scanPaths,
    archivePath: stored.archivePath,
    renameStrategy: stored.renameStrategy,
    maxSizeMb: stored.maxSizeMb,
    aiConfig: { baseUrl: stored.aiConfig.baseUrl, apiKey, model: stored.aiConfig.model },
  }

  const setSettings = useCallback(async (patch: Partial<Settings>) => {
    // Non-apiKey fields update synchronously
    setStored((prev) => {
      const next: StoredSettings = {
        scanPaths: patch.scanPaths ?? prev.scanPaths,
        archivePath: patch.archivePath ?? prev.archivePath,
        renameStrategy: patch.renameStrategy ?? prev.renameStrategy,
        maxSizeMb: patch.maxSizeMb ?? prev.maxSizeMb,
        aiConfig: patch.aiConfig
          ? { ...prev.aiConfig, baseUrl: patch.aiConfig.baseUrl, model: patch.aiConfig.model }
          : prev.aiConfig,
      }
      saveStored(next)
      return next
    })

    // Encrypt and save API key separately
    if (patch.aiConfig?.apiKey !== undefined) {
      const plain = patch.aiConfig.apiKey
      setApiKeyState(plain)

      if (isElectron) {
        const { encrypted, fallback } = await window.backend.setApiKey(plain)
        setStored((prev) => {
          const next = { ...prev, aiConfig: { ...prev.aiConfig, encryptedKey: encrypted, keyFallback: fallback } }
          saveStored(next)
          return next
        })
      } else {
        setStored((prev) => {
          const next = { ...prev, aiConfig: { ...prev.aiConfig, encryptedKey: plain, keyFallback: true } }
          saveStored(next)
          return next
        })
      }
    }
  }, [])

  return { settings, setSettings, ready }
}
