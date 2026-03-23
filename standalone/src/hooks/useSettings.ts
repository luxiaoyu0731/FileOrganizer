/**
 * Standalone 版 useSettings —— 纯 localStorage，无 safeStorage。
 * 构建时由 vite.standalone.config.ts 的 alias 替换掉主版本。
 */
import { useCallback, useState } from 'react'

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

const STORAGE_KEY = 'fileorganizer_settings'

const DEFAULT_SETTINGS: Settings = {
  scanPaths: [],
  archivePath: '',
  renameStrategy: 'semantic_date',
  maxSizeMb: 500,
  aiConfig: { baseUrl: '', apiKey: '', model: '' },
}

function load(): Settings {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return DEFAULT_SETTINGS
    const p = JSON.parse(raw) as Partial<Settings>
    return { ...DEFAULT_SETTINGS, ...p, aiConfig: { ...DEFAULT_SETTINGS.aiConfig, ...p.aiConfig } }
  } catch {
    return DEFAULT_SETTINGS
  }
}

export function useSettings() {
  const [settings, setSettingsState] = useState<Settings>(load)

  const setSettings = useCallback((patch: Partial<Settings>) => {
    setSettingsState((prev) => {
      const next = {
        ...prev,
        ...patch,
        aiConfig: patch.aiConfig ? { ...prev.aiConfig, ...patch.aiConfig } : prev.aiConfig,
      }
      localStorage.setItem(STORAGE_KEY, JSON.stringify(next))
      return next
    })
  }, [])

  // ready 始终为 true（无异步解密）
  return { settings, setSettings, ready: true }
}
