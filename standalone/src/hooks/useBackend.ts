/**
 * Standalone 版 useBackend —— 直接 fetch /api/...，无需 Electron IPC。
 * 构建时由 config/vite.standalone.config.ts 的 alias 替换掉主版本。
 */
import { useCallback, useState } from 'react'
import type { AiConfig } from './useSettings'

export interface WatchStartPayload {
  paths: string[]
  ai_config: AiConfig
  archive_root: string
  rename_strategy: string
  auto_execute: boolean
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

const BASE = ''  // 同源，路径直接用 /api/...

async function apiFetch(path: string, options?: RequestInit): Promise<unknown> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(`${res.status} ${res.statusText}: ${text}`)
  }
  return res.json()
}

function normalizeAiConfig(payload: Record<string, unknown>): Record<string, unknown> {
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
    (paths: string[]) =>
      call(() => apiFetch('/api/scan', {
        method: 'POST',
        body: JSON.stringify({ paths }),
      }) as Promise<ScanResult>),
    [call]
  )

  const classify = useCallback(
    (payload: unknown) =>
      call(() => apiFetch('/api/classify', {
        method: 'POST',
        body: JSON.stringify(normalizeAiConfig(payload as Record<string, unknown>)),
      })),
    [call]
  )

  const execute = useCallback(
    (payload: unknown) =>
      call(() => apiFetch('/api/execute', {
        method: 'POST',
        body: JSON.stringify(normalizeAiConfig(payload as Record<string, unknown>)),
      })),
    [call]
  )

  const getHistory = useCallback(
    () => call(() => apiFetch('/api/history')),
    [call]
  )

  const rollback = useCallback(
    (id: string) =>
      call(() => apiFetch('/api/rollback', {
        method: 'POST',
        body: JSON.stringify({ operation_id: id }),
      })),
    [call]
  )

  const testApiConnection = useCallback(
    (config: AiConfig) =>
      call(() => apiFetch('/api/test-connection', {
        method: 'POST',
        body: JSON.stringify({
          base_url: config.baseUrl,
          api_key: config.apiKey,
          model: config.model,
        }),
      })),
    [call]
  )

  const watchStart = useCallback(
    (payload: WatchStartPayload) =>
      call(() => apiFetch('/api/watch/start', {
        method: 'POST',
        body: JSON.stringify(normalizeAiConfig(payload as unknown as Record<string, unknown>)),
      })),
    [call]
  )

  const watchStop = useCallback(
    () => call(() => apiFetch('/api/watch/stop', { method: 'POST' })),
    [call]
  )

  // Standalone 无文件选择器对话框，返回 null 让 Settings 降级到手动输入
  const selectDirectory = useCallback(
    () => Promise.resolve(null as string | null),
    []
  )

  const getHealth = useCallback(
    () => call(() => apiFetch('/api/health')),
    [call]
  )

  return {
    loading, error,
    scanFiles, classify, execute,
    getHistory, rollback,
    testApiConnection,
    watchStart, watchStop,
    selectDirectory, getHealth,
  }
}
