import { useRef, useState } from 'react'
import { useBackend } from '../hooks/useBackend'
import { useSettings } from '../hooks/useSettings'

// 模型预设 — 按接口提供商分组，覆盖主流 OpenAI API 兼容服务
const MODEL_PRESETS = [
  // OpenRouter（聚合平台，一个 Key 调用多家模型）
  { label: 'Gemini Flash',  baseUrl: 'https://openrouter.ai/api/v1', model: 'google/gemini-2.0-flash-001', group: 'OpenRouter' },
  { label: 'GPT-4o',        baseUrl: 'https://openrouter.ai/api/v1', model: 'openai/gpt-4o',               group: 'OpenRouter' },
  { label: 'Claude Sonnet', baseUrl: 'https://openrouter.ai/api/v1', model: 'anthropic/claude-sonnet-4',   group: 'OpenRouter' },
  { label: 'DeepSeek V3',   baseUrl: 'https://openrouter.ai/api/v1', model: 'deepseek/deepseek-chat-v3-0324', group: 'OpenRouter' },
  { label: 'Qwen3 235B',    baseUrl: 'https://openrouter.ai/api/v1', model: 'qwen/qwen3-235b-a22b',       group: 'OpenRouter' },
  // 官方直连
  { label: 'OpenAI',    baseUrl: 'https://api.openai.com/v1',    model: 'gpt-4o',          group: '直连' },
  { label: 'DeepSeek',  baseUrl: 'https://api.deepseek.com/v1',  model: 'deepseek-chat',   group: '直连' },
  { label: '通义千问',   baseUrl: 'https://dashscope.aliyuncs.com/compatible-mode/v1', model: 'qwen-plus', group: '直连' },
  { label: '智谱 GLM',  baseUrl: 'https://open.bigmodel.cn/api/paas/v4', model: 'glm-4-flash', group: '直连' },
  // 本地
  { label: 'Ollama',    baseUrl: 'http://localhost:11434/v1',     model: 'llama3',          group: '本地' },
]

const isElectron = typeof window !== 'undefined'
  && typeof window.backend === 'object'
  && typeof (window as { backend?: { selectDirectory?: unknown } }).backend?.selectDirectory === 'function'

export default function Settings() {
  const { settings, setSettings } = useSettings()
  const { selectDirectory, testApiConnection } = useBackend()
  const [testing, setTesting] = useState(false)
  const [testResult, setTestResult] = useState<{ ok: boolean; message: string } | null>(null)
  const [manualPath, setManualPath] = useState('')
  const [showManualInput, setShowManualInput] = useState(!isElectron)
  const scanPickerRef = useRef<HTMLInputElement>(null)
  const archivePickerRef = useRef<HTMLInputElement>(null)

  // Browser folder picker: extract root folder name from webkitRelativePath
  const handleScanFolderPick = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files
    if (files && files.length > 0) {
      const rel = (files[0] as File & { webkitRelativePath: string }).webkitRelativePath
      const folderName = rel.split('/')[0]
      setManualPath('/' + folderName)
      setShowManualInput(true)
    }
    e.target.value = ''
  }

  const handleArchiveFolderPick = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files
    if (files && files.length > 0) {
      const rel = (files[0] as File & { webkitRelativePath: string }).webkitRelativePath
      const folderName = rel.split('/')[0]
      setSettings({ archivePath: '/' + folderName })
    }
    e.target.value = ''
  }

  const addScanPath = async () => {
    if (isElectron) {
      const dir = await selectDirectory()
      if (dir && !settings.scanPaths.includes(dir)) {
        setSettings({ scanPaths: [...settings.scanPaths, dir] })
      }
    } else {
      setShowManualInput(true)
    }
  }

  const confirmManualPath = () => {
    const p = manualPath.trim()
    if (p && !settings.scanPaths.includes(p)) {
      setSettings({ scanPaths: [...settings.scanPaths, p] })
      setManualPath('')
    }
  }

  const removeScanPath = (path: string) => {
    setSettings({ scanPaths: settings.scanPaths.filter((p) => p !== path) })
  }

  const pickArchivePath = async () => {
    if (isElectron) {
      const dir = await selectDirectory()
      if (dir) setSettings({ archivePath: dir })
    }
  }

  const handleTestConnection = async () => {
    setTesting(true)
    setTestResult(null)
    const result = await testApiConnection(settings.aiConfig) as { ok: boolean; message: string } | null
    setTestResult(result ?? { ok: false, message: '连接失败' })
    setTesting(false)
  }

  const applyPreset = (preset: typeof MODEL_PRESETS[number]) => {
    setSettings({ aiConfig: { ...aiConfig, baseUrl: preset.baseUrl, model: preset.model } })
  }

  const aiConfig = settings.aiConfig ?? { baseUrl: '', apiKey: '', model: '' }

  const inputClass = 'w-full border border-gray-300 dark:border-gray-600 rounded-lg px-3 py-2 text-sm text-gray-900 dark:text-gray-100 bg-white dark:bg-gray-800 focus:outline-none focus:ring-2 focus:ring-blue-500'

  return (
    <div className="p-6 max-w-2xl space-y-8">
      <h1 className="text-2xl font-semibold">设置</h1>

      {/* AI API 配置 */}
      <section>
        <h2 className="text-base font-medium text-gray-800 dark:text-gray-200 mb-3">AI 接口配置</h2>

        {/* 模型快选 */}
        <div className="mb-4">
          <p className="text-xs text-gray-500 mb-2">快速选择模型（自动填入地址和模型名）：</p>
          <div className="flex flex-wrap gap-1.5">
            {(['OpenRouter', '直连', '本地'] as const).map((group, gi, arr) => (
              <div key={group} className="flex flex-wrap gap-1.5 items-center">
                <span className="text-xs text-gray-400 mr-0.5">{group}</span>
                {MODEL_PRESETS.filter((p) => p.group === group).map((preset) => (
                  <button
                    key={preset.label}
                    onClick={() => applyPreset(preset)}
                    className="px-2.5 py-1 text-xs border border-gray-200 dark:border-gray-600 rounded-full text-gray-600 dark:text-gray-300 hover:border-blue-400 hover:text-blue-600 hover:bg-blue-50 dark:hover:bg-blue-900 transition-colors"
                  >
                    {preset.label}
                  </button>
                ))}
                {gi < arr.length - 1 && <span className="text-gray-200 dark:text-gray-600 mx-1">|</span>}
              </div>
            ))}
          </div>
        </div>

        <div className="space-y-3">
          <div>
            <label className="block text-sm text-gray-600 dark:text-gray-400 mb-1">API Base URL</label>
            <input
              type="text"
              value={aiConfig.baseUrl}
              onChange={(e) => setSettings({ aiConfig: { ...aiConfig, baseUrl: e.target.value } })}
              placeholder="API Base URL"
              className={inputClass}
            />
          </div>
          <div>
            <label className="block text-sm text-gray-600 dark:text-gray-400 mb-1">API Key</label>
            <input
              type="password"
              value={aiConfig.apiKey}
              onChange={(e) => setSettings({ aiConfig: { ...aiConfig, apiKey: e.target.value } })}
              placeholder="sk-..."
              className={inputClass}
            />
          </div>
          <div>
            <label className="block text-sm text-gray-600 dark:text-gray-400 mb-1">模型名称</label>
            <input
              type="text"
              value={aiConfig.model}
              onChange={(e) => setSettings({ aiConfig: { ...aiConfig, model: e.target.value } })}
              placeholder="模型名称"
              className={inputClass}
            />
          </div>
          <div className="flex items-center gap-3">
            <button
              onClick={handleTestConnection}
              disabled={testing || !aiConfig.apiKey}
              className="px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg text-sm text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700 disabled:opacity-40 transition-colors"
            >
              {testing ? '测试中…' : '测试连接'}
            </button>
            {testResult && (
              <span className={`text-sm ${testResult.ok ? 'text-green-600' : 'text-red-600'}`}>
                {testResult.ok ? '✅ ' : '❌ '}{testResult.message}
              </span>
            )}
          </div>
        </div>
      </section>

      {/* 扫描路径 */}
      <section>
        <h2 className="text-base font-medium text-gray-800 dark:text-gray-200 mb-3">扫描路径</h2>
        <div className="space-y-2">
          {settings.scanPaths.map((p) => (
            <div key={p} className="flex items-center gap-2 bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-gray-600 rounded-lg px-3 py-2">
              <span className="flex-1 font-mono text-sm text-gray-700 dark:text-gray-300 truncate">{p}</span>
              <button onClick={() => removeScanPath(p)} className="text-red-400 hover:text-red-600 text-xs shrink-0">删除</button>
            </div>
          ))}
          {settings.scanPaths.length === 0 && <p className="text-sm text-gray-400 italic">未配置扫描路径</p>}
        </div>

        {/* 手动输入路径（浏览器模式 / Electron 均支持） */}
        {showManualInput && (
          <div className="mt-3 flex gap-2">
            <input
              type="text"
              value={manualPath}
              onChange={(e) => setManualPath(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && confirmManualPath()}
              placeholder="/Users/yourname/Downloads"
              className="flex-1 border border-gray-300 dark:border-gray-600 rounded-lg px-3 py-1.5 text-sm text-gray-900 dark:text-gray-100 bg-white dark:bg-gray-800 focus:outline-none focus:ring-2 focus:ring-blue-500"
              autoFocus
            />
            <button
              onClick={confirmManualPath}
              disabled={!manualPath.trim()}
              className="px-3 py-1.5 bg-blue-600 text-white rounded-lg text-sm hover:bg-blue-700 disabled:opacity-40 transition-colors"
            >
              添加
            </button>
            {!isElectron && (
              <button
                onClick={() => { setShowManualInput(false); setManualPath('') }}
                className="px-3 py-1.5 border border-gray-200 dark:border-gray-600 text-gray-500 dark:text-gray-400 rounded-lg text-sm hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors"
              >
                取消
              </button>
            )}
          </div>
        )}

        {/* Hidden folder picker for browser mode */}
        <input
          ref={scanPickerRef}
          type="file"
          // @ts-ignore
          webkitdirectory=""
          multiple
          className="hidden"
          onChange={handleScanFolderPick}
        />

        <div className="mt-3 flex gap-2 flex-wrap">
          {isElectron && (
            <button onClick={addScanPath} className="px-3 py-1.5 border border-gray-300 dark:border-gray-600 rounded-lg text-sm text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors">
              + 选择目录
            </button>
          )}
          {!isElectron && (
            <button
              onClick={() => scanPickerRef.current?.click()}
              title="浏览文件夹（仅显示文件夹名，需补全完整路径）"
              className="px-3 py-1.5 border border-gray-300 dark:border-gray-600 rounded-lg text-sm text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors flex items-center gap-1"
            >
              📎 浏览文件夹
            </button>
          )}
          <button
            onClick={() => { setShowManualInput(true); setManualPath('') }}
            className="px-3 py-1.5 border border-gray-300 dark:border-gray-600 rounded-lg text-sm text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors"
          >
            + 手动输入路径
          </button>
        </div>
      </section>

      {/* 归档目标路径 */}
      <section>
        <h2 className="text-base font-medium text-gray-800 dark:text-gray-200 mb-3">归档目标路径</h2>
        {/* Hidden folder picker for browser mode */}
        <input
          ref={archivePickerRef}
          type="file"
          // @ts-ignore
          webkitdirectory=""
          multiple
          className="hidden"
          onChange={handleArchiveFolderPick}
        />

        {isElectron ? (
          <div className="flex items-center gap-2">
            <div className="flex-1 bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-gray-600 rounded-lg px-3 py-2 min-h-[38px]">
              {settings.archivePath
                ? <span className="font-mono text-sm text-gray-700 dark:text-gray-300">{settings.archivePath}</span>
                : <span className="text-sm text-gray-400 italic">未设置</span>}
            </div>
            <button onClick={pickArchivePath} className="px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg text-sm text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors whitespace-nowrap">
              选择…
            </button>
          </div>
        ) : (
          <div className="flex gap-2">
            <input
              type="text"
              value={settings.archivePath}
              onChange={(e) => setSettings({ archivePath: e.target.value })}
              placeholder="/Users/yourname/Organized"
              className="flex-1 border border-gray-300 dark:border-gray-600 rounded-lg px-3 py-2 text-sm text-gray-900 dark:text-gray-100 bg-white dark:bg-gray-800 focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
            <button
              onClick={() => archivePickerRef.current?.click()}
              title="浏览文件夹（仅显示文件夹名，需补全完整路径）"
              className="px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg text-sm text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors"
            >
              📎
            </button>
          </div>
        )}
      </section>

      {/* 重命名策略 */}
      <section>
        <h2 className="text-base font-medium text-gray-800 dark:text-gray-200 mb-3">重命名策略</h2>
        <div className="space-y-2">
          {(
            [
              ['semantic_date', '语义 + 日期前缀', '2026-03-15_腾讯NDA保密协议.pdf'],
              ['date_prefix', '日期前缀 + 原名', '2026-03-15_contract.pdf'],
              ['preserve_original', '保留原文件名', 'contract.pdf'],
            ] as const
          ).map(([value, label, example]) => (
            <label key={value} className="flex items-start gap-3 cursor-pointer">
              <input
                type="radio"
                name="rename_strategy"
                value={value}
                checked={settings.renameStrategy === value}
                onChange={() => setSettings({ renameStrategy: value })}
                className="mt-0.5"
              />
              <div>
                <div className="text-sm font-medium text-gray-800 dark:text-gray-200">{label}</div>
                <div className="text-xs font-mono text-gray-500 dark:text-gray-400 mt-0.5">{example}</div>
              </div>
            </label>
          ))}
        </div>
      </section>

      {/* 文件大小限制 */}
      <section>
        <h2 className="text-base font-medium text-gray-800 dark:text-gray-200 mb-3">文件大小上限</h2>
        <div className="flex items-center gap-3">
          <input
            type="number"
            min={1}
            max={10000}
            value={settings.maxSizeMb}
            onChange={(e) => setSettings({ maxSizeMb: Number(e.target.value) })}
            className="w-28 border border-gray-300 dark:border-gray-600 rounded-lg px-3 py-2 text-sm text-gray-900 dark:text-gray-100 bg-white dark:bg-gray-800 focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
          <span className="text-sm text-gray-500 dark:text-gray-400">MB（超过此大小的文件将跳过）</span>
        </div>
      </section>
    </div>
  )
}
