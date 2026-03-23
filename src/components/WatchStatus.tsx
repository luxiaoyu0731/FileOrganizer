import { useCallback, useEffect, useRef, useState } from 'react'
import { useBackend } from '../hooks/useBackend'
import { useSettings } from '../hooks/useSettings'

interface RecentEntry {
  path: string
  category: string
  destination: string
  status: string
  timestamp: string
}

interface WatchState {
  watching: boolean
  paths: string[]
  recent: RecentEntry[]
}

export default function WatchStatus() {
  const { settings } = useSettings()
  const { watchStart, watchStop } = useBackend()
  const [state, setState] = useState<WatchState>({ watching: false, paths: [], recent: [] })
  const [loading, setLoading] = useState(false)
  const [autoExecute, setAutoExecute] = useState(false)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const fetchStatus = useCallback(async () => {
    try {
      const res = await window.backend.watchStatus() as WatchState
      setState(res)
    } catch {
      // backend not reachable in browser preview
    }
  }, [])

  // Poll every 3 seconds when watching
  useEffect(() => {
    fetchStatus()
    pollRef.current = setInterval(fetchStatus, 3000)
    return () => { if (pollRef.current) clearInterval(pollRef.current) }
  }, [fetchStatus])

  const handleToggle = async () => {
    setLoading(true)
    if (state.watching) {
      await watchStop()
    } else {
      await watchStart({
        paths: settings.scanPaths,
        ai_config: settings.aiConfig,
        archive_root: settings.archivePath,
        rename_strategy: settings.renameStrategy,
        auto_execute: autoExecute,
      })
    }
    await fetchStatus()
    setLoading(false)
  }

  const statusDot = state.watching
    ? 'bg-green-400 animate-pulse'
    : 'bg-gray-300'

  return (
    <div className="border border-gray-200 dark:border-gray-700 rounded-xl p-4 space-y-4">
      {/* Header row */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className={`w-2.5 h-2.5 rounded-full ${statusDot}`} />
          <span className="text-sm font-medium text-gray-800 dark:text-gray-200">
            {state.watching ? '后台监听中' : '监听未启动'}
          </span>
          {state.watching && (
            <span className="text-xs text-gray-400">({state.paths.length} 个目录)</span>
          )}
        </div>

        <div className="flex items-center gap-3">
          {!state.watching && (
            <label className="flex items-center gap-1.5 text-xs text-gray-500 cursor-pointer select-none">
              <input
                type="checkbox"
                checked={autoExecute}
                onChange={(e) => setAutoExecute(e.target.checked)}
                className="rounded"
              />
              自动归档
            </label>
          )}
          <button
            onClick={handleToggle}
            disabled={loading || (!state.watching && settings.scanPaths.length === 0)}
            className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors disabled:opacity-40 ${
              state.watching
                ? 'bg-red-50 dark:bg-red-900/30 text-red-600 dark:text-red-400 hover:bg-red-100 dark:hover:bg-red-900/50'
                : 'bg-blue-50 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400 hover:bg-blue-100 dark:hover:bg-blue-900/50'
            }`}
          >
            {loading ? '处理中…' : state.watching ? '停止监听' : '开启监听'}
          </button>
        </div>
      </div>

      {/* Paths */}
      {state.watching && state.paths.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {state.paths.map((p) => (
            <span key={p} className="text-xs font-mono bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400 rounded px-2 py-0.5 truncate max-w-xs">
              {p}
            </span>
          ))}
        </div>
      )}

      {/* Recent files */}
      {state.recent.length > 0 && (
        <div>
          <p className="text-xs text-gray-400 mb-2">最近处理</p>
          <div className="space-y-1 max-h-40 overflow-auto">
            {state.recent.map((entry, i) => (
              <div key={i} className="flex items-center gap-2 text-xs">
                <span className={entry.status === 'success' ? 'text-green-500' : entry.status === 'pending' ? 'text-yellow-500' : 'text-red-500'}>
                  {entry.status === 'success' ? '✅' : entry.status === 'pending' ? '⏳' : '❌'}
                </span>
                <span className="font-mono text-gray-600 truncate flex-1">{entry.path.split('/').pop()}</span>
                <span className="text-gray-400 shrink-0">{entry.category}</span>
                <span className="text-gray-300 shrink-0">{new Date(entry.timestamp).toLocaleTimeString('zh-CN')}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {!state.watching && settings.scanPaths.length === 0 && (
        <p className="text-xs text-gray-400 italic">请先在「设置」中配置扫描路径</p>
      )}
    </div>
  )
}
