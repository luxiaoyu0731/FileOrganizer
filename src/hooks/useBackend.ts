import { useCallback, useState } from 'react'
import type { AiConfig } from './useSettings'

export interface WatchStartPayload {
  paths: string[]
  ai_config: AiConfig
  archive_root: string
  rename_strategy: string
  auto_execute: boolean
}

declare global {
  interface Window {
    backend: {
      getHealth: () => Promise<unknown>
      scanFiles: (config: { paths: string[]; max_size_mb?: number }) => Promise<unknown>
      classify: (payload: unknown) => Promise<unknown>
      classifyTree: (payload: unknown) => Promise<unknown>
      execute: (payload: unknown) => Promise<unknown>
      getHistory: () => Promise<unknown>
      rollback: (operationId: string) => Promise<unknown>
      testApiConnection: (config: unknown) => Promise<unknown>
      cleanupDirs: (payload: { scan_paths: string[] }) => Promise<unknown>
      watchStart: (payload: WatchStartPayload) => Promise<unknown>
      watchStop: () => Promise<unknown>
      watchStatus: () => Promise<unknown>
      selectDirectory: () => Promise<string | null>
      setApiKey: (plaintext: string) => Promise<{ encrypted: string; fallback: boolean }>
      getApiKey: (stored: string, fallback: boolean) => Promise<string>
    }
  }
}

export interface ScanFile {
  path: string
  size_bytes: number
  modified_time: string
  extension: string
  sha256: string
}

export interface ScanResult {
  total: number
  files: ScanFile[]
}

// ─── Browser-mode direct fetch (when no Electron context) ─────────────────────

const BACKEND_ORIGIN = 'http://127.0.0.1:18923'

// Detect Electron: contextBridge exposes window.backend
const hasElectron = typeof window !== 'undefined'
  && typeof (window as Record<string, unknown>).backend === 'object'

async function apiFetch(path: string, options?: RequestInit): Promise<unknown> {
  const res = await fetch(`${BACKEND_ORIGIN}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(`${res.status}: ${text}`)
  }
  return res.json()
}

// Convert camelCase ai_config keys to snake_case for direct fetch calls
function normalizePayload(payload: Record<string, unknown>): Record<string, unknown> {
  const cfg = payload.ai_config as Record<string, unknown> | undefined
  if (!cfg) return payload
  return {
    ...payload,
    ai_config: {
      base_url: (cfg.baseUrl ?? cfg.base_url ?? '') as string,
      api_key: (cfg.apiKey ?? cfg.api_key ?? '') as string,
      model: (cfg.model ?? '') as string,
    },
  }
}

// ─── Hook ─────────────────────────────────────────────────────────────────────

export function useBackend() {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const call = useCallback(async <T>(fn: () => Promise<T>): Promise<T | null> => {
    setLoading(true)
    setError(null)
    try {
      return await fn()
    } catch (e) {
      setError(e instanceof Error ? e.message : '未知错误')
      return null
    } finally {
      setLoading(false)
    }
  }, [])

  const scanFiles = useCallback(
    (paths: string[]) => call(() =>
      hasElectron
        ? window.backend.scanFiles({ paths }) as Promise<ScanResult>
        : apiFetch('/api/scan', { method: 'POST', body: JSON.stringify({ paths }) }) as Promise<ScanResult>
    ),
    [call]
  )

  const classifyTree = useCallback(
    (payload: unknown) => call(() =>
      hasElectron
        ? window.backend.classifyTree(payload)
        : apiFetch('/api/classify/tree', {
            method: 'POST',
            body: JSON.stringify(normalizePayload(payload as Record<string, unknown>)),
          })
    ),
    [call]
  )

  const execute = useCallback(
    (payload: unknown) => call(() =>
      hasElectron
        ? window.backend.execute(payload)
        : apiFetch('/api/execute', {
            method: 'POST',
            body: JSON.stringify(normalizePayload(payload as Record<string, unknown>)),
          })
    ),
    [call]
  )

  const getHistory = useCallback(
    () => call(() =>
      hasElectron
        ? window.backend.getHistory()
        : apiFetch('/api/history')
    ),
    [call]
  )

  const rollback = useCallback(
    (id: string) => call(() =>
      hasElectron
        ? window.backend.rollback(id)
        : apiFetch('/api/rollback', { method: 'POST', body: JSON.stringify({ operation_id: id }) })
    ),
    [call]
  )

  const testApiConnection = useCallback(
    (config: AiConfig) => call(() =>
      hasElectron
        ? window.backend.testApiConnection(config)
        : apiFetch('/api/test-connection', {
            method: 'POST',
            body: JSON.stringify({
              base_url: config.baseUrl,
              api_key: config.apiKey,
              model: config.model,
            }),
          })
    ),
    [call]
  )

  const cleanupDirs = useCallback(
    (scanPaths: string[]) => call(() =>
      hasElectron
        ? window.backend.cleanupDirs({ scan_paths: scanPaths })
        : apiFetch('/api/cleanup-empty-dirs', {
            method: 'POST',
            body: JSON.stringify({ scan_paths: scanPaths }),
          })
    ),
    [call]
  )

  const watchStart = useCallback(
    (payload: WatchStartPayload) => call(() =>
      hasElectron
        ? window.backend.watchStart(payload)
        : apiFetch('/api/watch/start', {
            method: 'POST',
            body: JSON.stringify(normalizePayload(payload as unknown as Record<string, unknown>)),
          })
    ),
    [call]
  )

  const watchStop = useCallback(
    () => call(() =>
      hasElectron
        ? window.backend.watchStop()
        : apiFetch('/api/watch/stop', { method: 'POST' })
    ),
    [call]
  )

  const selectDirectory = useCallback(
    () => call(() =>
      hasElectron
        ? window.backend.selectDirectory()
        : Promise.resolve(null)
    ),
    [call]
  )

  const getHealth = useCallback(
    () => call(() =>
      hasElectron
        ? window.backend.getHealth()
        : apiFetch('/api/health')
    ),
    [call]
  )

  return {
    loading, error,
    scanFiles, classifyTree, execute,
    getHistory, rollback, cleanupDirs,
    testApiConnection,
    watchStart, watchStop,
    selectDirectory, getHealth,
  }
}
