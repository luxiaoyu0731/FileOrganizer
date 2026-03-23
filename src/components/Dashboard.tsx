import { useEffect, useRef, useState } from 'react'
import { ScanFile, useBackend } from '../hooks/useBackend'
import { useSettings } from '../hooks/useSettings'
import type { Page } from '../App'
import type { FlatClassification } from './FilePreview'
import TreePreview, { type TreeResult } from './TreePreview'
import WatchStatus from './WatchStatus'

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString('zh-CN')
}

function fileIcon(ext: string): string {
  const e = ext.toLowerCase()
  if (['.pdf'].includes(e)) return '📄'
  if (['.doc', '.docx'].includes(e)) return '📝'
  if (['.xls', '.xlsx', '.csv'].includes(e)) return '📊'
  if (['.ppt', '.pptx'].includes(e)) return '📑'
  if (['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.heic', '.heif'].includes(e)) return '🖼️'
  if (['.mp4', '.mov', '.avi', '.mkv', '.wmv'].includes(e)) return '🎬'
  if (['.mp3', '.flac', '.aac', '.wav', '.m4a'].includes(e)) return '🎵'
  if (['.zip', '.rar', '.7z', '.tar', '.gz'].includes(e)) return '🗜️'
  if (['.py', '.js', '.ts', '.tsx', '.jsx', '.go', '.rs', '.java', '.c', '.cpp'].includes(e)) return '💻'
  if (['.sh', '.bat', '.ps1'].includes(e)) return '⚙️'
  if (['.md', '.txt'].includes(e)) return '📃'
  return '📎'
}

type DashboardStep =
  | 'idle'
  | 'scanned'
  | 'tree-classifying'
  | 'tree-previewing'
  | 'executing'
  | 'done'
  | 'rolling-back'
  | 'rolled-back'

export default function Dashboard({ onNavigate }: { onNavigate: (p: Page) => void }) {
  const { settings } = useSettings()
  const { loading, error, scanFiles, classifyTree, execute, rollback, cleanupDirs } = useBackend()

  const [step, setStep] = useState<DashboardStep>('idle')
  const [files, setFiles] = useState<ScanFile[]>([])
  const [treeResult, setTreeResult] = useState<TreeResult | null>(null)
  const [executeResult, setExecuteResult] = useState<{ executed: number; total: number; operation_id?: string } | null>(null)
  const [execProgress, setExecProgress] = useState(0)
  const [cleanupResult, setCleanupResult] = useState<{ removed: string[]; errors: string[] } | null>(null)
  const [rollbackResult, setRollbackResult] = useState<{ rolled_back: number; errors: string[]; auto_cleanup?: { removed: string[]; errors: string[] } } | null>(null)

  // Real-time progress for tree classification
  const [treeProgress, setTreeProgress] = useState<{
    current: number; total: number; stage: string; message: string
  } | null>(null)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const requestIdRef = useRef<string | null>(null)
  const abortRef = useRef<AbortController | null>(null)

  // Cleanup polling on unmount
  useEffect(() => {
    return () => {
      if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null }
    }
  }, [])

  // ─── Handlers ──────────────────────────────────────────────────────────────

  const handleScan = async () => {
    if (settings.scanPaths.length === 0) { onNavigate('settings'); return }
    const result = await scanFiles(settings.scanPaths)
    if (result) { setFiles(result.files); setStep('scanned') }
  }

  const handleTreeClassify = async () => {
    if (!settings.aiConfig?.apiKey) { onNavigate('settings'); return }

    const requestId = crypto.randomUUID()
    requestIdRef.current = requestId
    abortRef.current = new AbortController()
    setStep('tree-classifying')
    setTreeProgress(null)

    // Poll progress every second
    pollRef.current = setInterval(async () => {
      try {
        const res = await fetch(`http://127.0.0.1:18923/api/classify/tree/progress/${requestId}`)
        if (res.ok) {
          const data = await res.json()
          if (data.total > 0) setTreeProgress(data)
        }
      } catch { /* backend not ready yet */ }
    }, 1000)

    const result = await classifyTree({
      files,
      ai_config: settings.aiConfig,
      request_id: requestId,
    }) as (TreeResult & { cancelled?: boolean }) | null

    // Stop polling
    if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null }
    requestIdRef.current = null
    abortRef.current = null

    if (result && !result.cancelled) {
      setTreeResult(result)
      setStep('tree-previewing')
    } else {
      // Cancelled or failed — go back to scanned state
      setStep(files.length > 0 ? 'scanned' : 'idle')
    }
  }

  const handleStopClassify = async () => {
    const requestId = requestIdRef.current
    if (!requestId) return

    // Send cancel request to backend
    try {
      await fetch(`http://127.0.0.1:18923/api/classify/tree/cancel/${requestId}`, {
        method: 'POST',
      })
    } catch { /* ignore */ }

    // Stop polling
    if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null }
    requestIdRef.current = null

    setTreeProgress(null)
    setStep(files.length > 0 ? 'scanned' : 'idle')
  }

  const handleExecute = async (confirmed: FlatClassification[]) => {
    setStep('executing')
    setExecProgress(0)
    const interval = setInterval(() => setExecProgress((p) => Math.min(p + 5, 90)), 300)
    const result = await execute({
      classifications: confirmed,
      archive_root: settings.archivePath,
      rename_strategy: settings.renameStrategy,
      ai_config: settings.aiConfig,
      scan_paths: settings.scanPaths,
    }) as { executed: number; total: number; operation_id?: string; auto_cleanup?: { removed: string[]; errors: string[] } } | null
    clearInterval(interval)
    setExecProgress(100)
    if (result) {
      setExecuteResult(result)
      // Show auto-cleanup result if any folders were cleaned
      if (result.auto_cleanup && result.auto_cleanup.removed.length > 0) {
        setCleanupResult(result.auto_cleanup)
      }
      setStep('done')
    }
    else setStep('tree-previewing')
  }

  const handleCleanup = async () => {
    if (settings.scanPaths.length === 0) return
    const result = await cleanupDirs(settings.scanPaths) as { removed: string[]; errors: string[] } | null
    if (result) setCleanupResult(result)
  }

  const handleRollback = async () => {
    const opId = executeResult?.operation_id
    if (!opId) return
    if (!window.confirm('确定要撤销本次归档操作？文件将被还原到原始位置。')) return
    setStep('rolling-back')
    const result = await rollback(opId) as { rolled_back: number; errors: string[]; auto_cleanup?: { removed: string[]; errors: string[] } } | null
    if (result) {
      setRollbackResult(result)
      setStep('rolled-back')
    }
    else setStep('done')
  }

  const handleReset = () => {
    if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null }
    setStep('idle')
    setFiles([])
    setTreeResult(null)
    setTreeProgress(null)
    setExecuteResult(null)
    setCleanupResult(null)
    setRollbackResult(null)
  }

  // ─── Subtitle ──────────────────────────────────────────────────────────────

  const subtitle = (() => {
    if (step === 'scanned')         return `扫描到 ${files.length} 个文件`
    if (step === 'tree-previewing') return '智能分组已完成，可重命名文件夹后执行归档'
    if (step === 'done')            return `✅ 已成功归档 ${executeResult?.executed} 个文件`
    if (step === 'rolled-back')     return `↩️ 已撤销归档，还原 ${rollbackResult?.rolled_back} 个文件`
    return null
  })()

  // ─── Render ────────────────────────────────────────────────────────────────

  return (
    <div className="p-6 h-full flex flex-col gap-4">

      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">控制台</h1>
          {subtitle && (
            <p className={`text-sm mt-1 ${step === 'done' ? 'text-green-600' : 'text-gray-500'}`}>
              {subtitle}
            </p>
          )}
        </div>

        <div className="flex gap-2">
          {(step === 'done' || step === 'rolled-back') && (
            <button
              onClick={handleReset}
              className="px-4 py-2 border border-gray-300 dark:border-gray-600 text-gray-600 dark:text-gray-300 rounded-lg text-sm
                         hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors"
            >
              重新开始
            </button>
          )}

          {step === 'idle' && (
            <button
              onClick={handleScan}
              disabled={loading}
              className="px-4 py-2 bg-violet-600 text-white rounded-lg font-medium
                         hover:bg-violet-700 disabled:opacity-50 transition-colors"
            >
              {loading ? '扫描中…' : '扫描文件'}
            </button>
          )}

          {step === 'scanned' && (
            <>
              <button
                onClick={handleScan}
                disabled={loading}
                className="px-4 py-2 border border-gray-300 text-gray-600 rounded-lg text-sm
                           hover:bg-gray-50 transition-colors"
              >
                重新扫描
              </button>
              <button
                onClick={handleTreeClassify}
                disabled={loading || files.length === 0}
                className="px-4 py-2 bg-violet-600 text-white rounded-lg font-medium
                           hover:bg-violet-700 disabled:opacity-50 transition-colors"
              >
                ✨ 智能分组
              </button>
            </>
          )}

          {step === 'tree-classifying' && (
            <button
              onClick={handleStopClassify}
              className="px-4 py-2 bg-red-500 text-white rounded-lg font-medium
                         hover:bg-red-600 transition-colors"
            >
              ⏹ 停止分组
            </button>
          )}
        </div>
      </div>

      {/* Watch status - always visible in idle/scanned states */}
      {(step === 'idle' || step === 'scanned') && <WatchStatus />}

      {error && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-3 text-red-700 text-sm">
          {error}
        </div>
      )}

      {/* ── idle ──────────────────────────────────────────────────────────── */}
      {step === 'idle' && (
        <div className="flex flex-col gap-4">
          <div className="flex-1 flex items-center justify-center text-gray-400 py-16">
            <div className="text-center">
              <div className="text-5xl mb-3">📁</div>
              <p className="text-lg font-medium text-gray-500">尚未扫描</p>
              <p className="text-sm mt-1">
                {settings.scanPaths.length === 0
                  ? '请先在「设置」中配置扫描路径'
                  : `将扫描 ${settings.scanPaths.length} 个目录，点击「扫描文件」开始`}
              </p>
              {settings.scanPaths.length === 0 && (
                <button
                  onClick={() => onNavigate('settings')}
                  className="mt-3 text-blue-600 text-sm hover:underline"
                >
                  前往设置 →
                </button>
              )}
            </div>
          </div>
        </div>
      )}

      {/* ── scanned – empty ───────────────────────────────────────────────── */}
      {step === 'scanned' && files.length === 0 && (
        <div className="flex-1 flex items-center justify-center text-gray-400">
          <div className="text-center">
            <div className="text-5xl mb-3">✅</div>
            <p className="text-lg font-medium">未找到文件</p>
            <p className="text-sm mt-1">配置的扫描路径中没有符合条件的文件</p>
          </div>
        </div>
      )}

      {/* ── scanned – file table ──────────────────────────────────────────── */}
      {step === 'scanned' && files.length > 0 && (
        <div className="flex-1 overflow-auto rounded-lg border border-gray-200 dark:border-gray-700">
          <table className="w-full text-sm table-fixed">
            <thead className="bg-gray-50 dark:bg-gray-800 sticky top-0 z-10">
              <tr>
                <th className="text-left px-3 py-2 font-medium text-gray-600 dark:text-gray-300" style={{width:'45%'}}>文件名</th>
                <th className="text-left px-3 py-2 font-medium text-gray-600 dark:text-gray-300 whitespace-nowrap" style={{width:'15%'}}>类型</th>
                <th className="text-right px-3 py-2 font-medium text-gray-600 dark:text-gray-300 whitespace-nowrap" style={{width:'18%'}}>大小</th>
                <th className="text-left px-3 py-2 font-medium text-gray-600 dark:text-gray-300 whitespace-nowrap" style={{width:'22%'}}>修改时间</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100 dark:divide-gray-700">
              {files.map((file) => (
                <tr key={file.sha256} className="hover:bg-gray-50 dark:hover:bg-gray-800/50 transition-colors">
                  <td className="px-3 py-1.5 truncate">
                    <div className="flex items-center gap-1.5">
                      <span className="text-sm shrink-0">{fileIcon(file.extension)}</span>
                      <span className="font-mono text-xs truncate" title={file.path}>
                        {file.path.split('/').pop()}
                      </span>
                    </div>
                  </td>
                  <td className="px-3 py-1.5">
                    <span className="inline-block bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300 rounded px-1.5 py-0.5 text-xs font-mono">
                      {file.extension || '—'}
                    </span>
                  </td>
                  <td className="px-3 py-1.5 text-right text-gray-600 dark:text-gray-400 text-xs whitespace-nowrap">{formatBytes(file.size_bytes)}</td>
                  <td className="px-3 py-1.5 text-gray-500 dark:text-gray-400 text-xs whitespace-nowrap">{formatDate(file.modified_time)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* ── tree-classifying ──────────────────────────────────────────────── */}
      {step === 'tree-classifying' && (
        <div className="flex-1 flex items-center justify-center">
          <div className="w-[420px] text-center">
            <div className="text-5xl mb-4">🧩</div>
            <p className="text-lg font-semibold text-gray-700 dark:text-gray-200 mb-1">AI 正在分析文件关联性</p>

            {treeProgress && treeProgress.total > 0 ? (
              <>
                <p className="text-sm text-gray-500 mb-5">{treeProgress.message}</p>

                {/* Progress bar */}
                <div className="w-full bg-gray-100 dark:bg-gray-700 rounded-full h-2.5 overflow-hidden mb-3">
                  <div
                    className="h-2.5 bg-violet-500 rounded-full transition-all duration-700 ease-out"
                    style={{ width: `${Math.min(100, (treeProgress.current / treeProgress.total) * 100)}%` }}
                  />
                </div>

                {/* Stats row */}
                <div className="flex justify-between text-xs text-gray-400 mb-2">
                  <span className="font-medium text-violet-600">{treeProgress.stage}</span>
                  <span>{treeProgress.current.toLocaleString()} / {treeProgress.total.toLocaleString()} 个文件</span>
                </div>

                {/* Percentage */}
                <p className="text-2xl font-bold text-violet-600 mt-3">
                  {Math.min(100, Math.round((treeProgress.current / treeProgress.total) * 100))}%
                </p>
              </>
            ) : (
              <>
                <p className="text-sm text-gray-400 mb-5">
                  共 {files.length.toLocaleString()} 个文件，正在生成专属文件夹结构…
                </p>
                {/* Indeterminate bar while waiting for first progress update */}
                <div className="w-full bg-gray-100 dark:bg-gray-700 rounded-full h-2.5 overflow-hidden">
                  <div className="h-2.5 bg-violet-400 rounded-full w-1/3 animate-pulse" />
                </div>
              </>
            )}

            <p className="text-xs text-gray-400 mt-4">
              点击右上角「停止分组」可随时中断
            </p>
          </div>
        </div>
      )}

      {/* ── tree-previewing ───────────────────────────────────────────────── */}
      {step === 'tree-previewing' && treeResult && (
        <TreePreview
          result={treeResult}
          archiveRoot={settings.archivePath}
          onExecute={handleExecute}
          onBack={() => setStep('scanned')}
        />
      )}

      {/* ── executing ─────────────────────────────────────────────────────── */}
      {step === 'executing' && (
        <div className="flex-1 flex items-center justify-center text-gray-400">
          <div className="text-center w-80">
            <div className="text-5xl mb-4">📦</div>
            <p className="text-lg font-medium text-gray-600 mb-4">正在归档文件…</p>
            <div className="w-full bg-gray-100 dark:bg-gray-700 rounded-full h-2 overflow-hidden">
              <div
                className="h-2 bg-violet-500 rounded-full transition-all duration-300"
                style={{ width: `${execProgress}%` }}
              />
            </div>
            <p className="text-sm text-gray-400 mt-2">{execProgress}%</p>
          </div>
        </div>
      )}

      {/* ── done ──────────────────────────────────────────────────────────── */}
      {step === 'done' && (
        <div className="flex-1 flex items-center justify-center">
          <div className="text-center max-w-md">
            <div className="text-6xl mb-4">🎉</div>
            <p className="text-xl font-semibold text-gray-800 dark:text-gray-100">归档完成</p>
            <p className="text-gray-500 mt-2">已成功归档 {executeResult?.executed} 个文件</p>
            <p className="text-sm text-gray-400 mt-1">目标路径：{settings.archivePath}</p>

            {/* Action buttons */}
            <div className="flex justify-center gap-3 mt-6">
              <button
                onClick={handleCleanup}
                disabled={loading}
                className="px-4 py-2 border border-gray-300 text-gray-600 rounded-lg text-sm
                           hover:bg-gray-50 disabled:opacity-50 transition-colors"
              >
                🧹 清理空文件夹
              </button>
              {executeResult?.operation_id && (
                <button
                  onClick={handleRollback}
                  disabled={loading}
                  className="px-4 py-2 border border-red-300 text-red-600 rounded-lg text-sm
                             hover:bg-red-50 disabled:opacity-50 transition-colors"
                >
                  ↩️ 撤销归档
                </button>
              )}
            </div>

            {/* Cleanup result */}
            {cleanupResult && (
              <div className="mt-4 text-left bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg p-3 text-sm">
                {cleanupResult.removed.length > 0 ? (
                  <p className="text-green-600">✅ 已清理 {cleanupResult.removed.length} 个空文件夹</p>
                ) : (
                  <p className="text-gray-500">✔ 无需清理（没有空文件夹）</p>
                )}
                {cleanupResult.errors.length > 0 && (
                  <p className="text-red-500 mt-1">⚠ {cleanupResult.errors.length} 个文件夹清理失败</p>
                )}
              </div>
            )}
          </div>
        </div>
      )}

      {/* ── rolling-back ───────────────────────────────────────────────────── */}
      {step === 'rolling-back' && (
        <div className="flex-1 flex items-center justify-center text-gray-400">
          <div className="text-center">
            <div className="text-5xl mb-4 animate-pulse">↩️</div>
            <p className="text-lg font-medium text-gray-600">正在撤销归档…</p>
            <p className="text-sm text-gray-400 mt-1">文件将被还原到原始位置</p>
          </div>
        </div>
      )}

      {/* ── rolled-back ────────────────────────────────────────────────────── */}
      {step === 'rolled-back' && (
        <div className="flex-1 flex items-center justify-center">
          <div className="text-center max-w-md">
            <div className="text-6xl mb-4">↩️</div>
            <p className="text-xl font-semibold text-gray-800 dark:text-gray-100">撤销完成</p>
            <p className="text-gray-500 mt-2">已还原 {rollbackResult?.rolled_back} 个文件</p>
            {rollbackResult?.auto_cleanup && rollbackResult.auto_cleanup.removed.length > 0 && (
              <div className="mt-3 bg-green-50 border border-green-200 rounded-lg p-3 text-sm text-green-600 text-left">
                <p>已自动清理 {rollbackResult.auto_cleanup.removed.length} 个空文件夹</p>
              </div>
            )}
            {rollbackResult && rollbackResult.errors.length > 0 && (
              <div className="mt-3 bg-red-50 border border-red-200 rounded-lg p-3 text-sm text-red-600 text-left">
                <p className="font-medium mb-1">以下文件还原失败：</p>
                {rollbackResult.errors.slice(0, 5).map((e, i) => (
                  <p key={i} className="truncate text-xs">{e}</p>
                ))}
                {rollbackResult.errors.length > 5 && (
                  <p className="text-xs mt-1">...及 {rollbackResult.errors.length - 5} 个其他错误</p>
                )}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
