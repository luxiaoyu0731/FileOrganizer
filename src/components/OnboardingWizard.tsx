import { useRef, useState } from 'react'
import { useBackend } from '../hooks/useBackend'
import { useSettings } from '../hooks/useSettings'

interface Props {
  onComplete: () => void
}

const STEPS = ['欢迎', 'AI 配置', '扫描路径', '归档路径', '完成']

const isElectron = typeof window !== 'undefined'
  && typeof window.backend === 'object'
  && typeof (window as { backend?: { selectDirectory?: unknown } }).backend?.selectDirectory === 'function'

const inputClass = 'w-full border border-gray-300 rounded-lg px-3 py-2 text-sm text-gray-900 bg-white focus:outline-none focus:ring-2 focus:ring-blue-500'

export default function OnboardingWizard({ onComplete }: Props) {
  const { settings, setSettings } = useSettings()
  const { selectDirectory, testApiConnection } = useBackend()
  const [step, setStep] = useState(0)
  const [testing, setTesting] = useState(false)
  const [testResult, setTestResult] = useState<{ ok: boolean; message: string } | null>(null)
  const [manualScanPath, setManualScanPath] = useState('')
  const scanPickerRef = useRef<HTMLInputElement>(null)
  const archivePickerRef = useRef<HTMLInputElement>(null)

  const handleScanFolderPick = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files
    if (files && files.length > 0) {
      const rel = (files[0] as File & { webkitRelativePath: string }).webkitRelativePath
      setManualScanPath('/' + rel.split('/')[0])
    }
    e.target.value = ''
  }

  const handleArchiveFolderPick = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files
    if (files && files.length > 0) {
      const rel = (files[0] as File & { webkitRelativePath: string }).webkitRelativePath
      setSettings({ archivePath: '/' + rel.split('/')[0] })
    }
    e.target.value = ''
  }

  const aiConfig = settings.aiConfig

  const handleTestConnection = async () => {
    setTesting(true)
    setTestResult(null)
    const r = await testApiConnection(aiConfig) as { ok: boolean; message: string } | null
    setTestResult(r ?? { ok: false, message: '连接失败' })
    setTesting(false)
  }

  const addScanPath = async () => {
    const dir = await selectDirectory()
    if (dir && !settings.scanPaths.includes(dir)) {
      setSettings({ scanPaths: [...settings.scanPaths, dir] })
    }
  }

  const confirmManualScanPath = () => {
    const p = manualScanPath.trim()
    if (p && !settings.scanPaths.includes(p)) {
      setSettings({ scanPaths: [...settings.scanPaths, p] })
      setManualScanPath('')
    }
  }

  const pickArchivePath = async () => {
    const dir = await selectDirectory()
    if (dir) setSettings({ archivePath: dir })
  }

  const canNext = () => {
    if (step === 1) return !!aiConfig.apiKey && !!aiConfig.model
    if (step === 2) return settings.scanPaths.length > 0
    if (step === 3) return !!settings.archivePath
    return true
  }

  return (
    <div className="fixed inset-0 bg-gray-50 flex items-center justify-center z-50">
      <div className="bg-white rounded-2xl shadow-xl w-full max-w-lg mx-4 overflow-hidden">
        {/* Progress bar */}
        <div className="h-1 bg-gray-100">
          <div
            className="h-1 bg-blue-500 transition-all duration-500"
            style={{ width: `${((step) / (STEPS.length - 1)) * 100}%` }}
          />
        </div>

        {/* Step indicators */}
        <div className="flex justify-between px-8 pt-5 pb-1">
          {STEPS.map((label, i) => (
            <div key={i} className="flex flex-col items-center gap-1">
              <div className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold transition-colors ${
                i < step ? 'bg-blue-500 text-white' : i === step ? 'border-2 border-blue-500 text-blue-500' : 'border-2 border-gray-200 text-gray-300'
              }`}>
                {i < step ? '✓' : i + 1}
              </div>
              <span className={`text-xs ${i === step ? 'text-blue-600 font-medium' : 'text-gray-400'}`}>{label}</span>
            </div>
          ))}
        </div>

        <div className="px-8 py-6 min-h-[280px]">
          {/* Step 0: Welcome */}
          {step === 0 && (
            <div className="text-center pt-4">
              <div className="text-6xl mb-4">🗂️</div>
              <h2 className="text-2xl font-bold text-gray-900 mb-3">欢迎使用 FileOrganizer</h2>
              <p className="text-gray-500 leading-relaxed">
                智能文件整理助手，通过 AI 自动分析您的文件内容，<br />
                进行语义分类、智能重命名和自动归档。
              </p>
              <div className="mt-6 flex justify-center gap-6 text-sm text-gray-400">
                <span>🔒 本地运行</span>
                <span>🤖 AI 驱动</span>
                <span>↩️ 可回滚</span>
              </div>
            </div>
          )}

          {/* Step 1: AI Config */}
          {step === 1 && (
            <div className="space-y-4">
              <h2 className="text-xl font-bold text-gray-900">配置 AI 接口</h2>
              <p className="text-sm text-gray-500">支持 OpenAI、Claude、Ollama 等任意 OpenAI 兼容接口。</p>
              <div>
                <label className="block text-sm text-gray-600 mb-1">API Base URL</label>
                <input
                  type="text"
                  value={aiConfig.baseUrl}
                  onChange={(e) => setSettings({ aiConfig: { ...aiConfig, baseUrl: e.target.value } })}
                  placeholder="API Base URL"
                  className={inputClass}
                />
              </div>
              <div>
                <label className="block text-sm text-gray-600 mb-1">API Key</label>
                <input
                  type="password"
                  value={aiConfig.apiKey}
                  onChange={(e) => setSettings({ aiConfig: { ...aiConfig, apiKey: e.target.value } })}
                  placeholder="sk-..."
                  className={inputClass}
                />
              </div>
              <div>
                <label className="block text-sm text-gray-600 mb-1">模型名称</label>
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
                  className="px-3 py-1.5 border border-gray-300 rounded-lg text-sm text-gray-600 hover:bg-gray-50 disabled:opacity-40"
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
          )}

          {/* Step 2: Scan paths */}
          {step === 2 && (
            <div className="space-y-4">
              <h2 className="text-xl font-bold text-gray-900">选择扫描路径</h2>
              <p className="text-sm text-gray-500">选择需要整理的文件夹，可添加多个。</p>
              <div className="space-y-2">
                {settings.scanPaths.map((p) => (
                  <div key={p} className="flex items-center gap-2 bg-gray-50 border border-gray-200 rounded-lg px-3 py-2">
                    <span className="text-lg">📁</span>
                    <span className="flex-1 font-mono text-sm text-gray-700 truncate">{p}</span>
                    <button
                      onClick={() => setSettings({ scanPaths: settings.scanPaths.filter((x) => x !== p) })}
                      className="text-red-400 hover:text-red-600 text-xs"
                    >删除</button>
                  </div>
                ))}
                {settings.scanPaths.length === 0 && (
                  <p className="text-sm text-gray-400 italic">尚未添加扫描路径</p>
                )}
              </div>
              {/* Hidden folder picker */}
              <input
                ref={scanPickerRef}
                type="file"
                // @ts-ignore
                webkitdirectory=""
                multiple
                className="hidden"
                onChange={handleScanFolderPick}
              />

              {isElectron ? (
                <button
                  onClick={addScanPath}
                  className="px-3 py-1.5 border border-dashed border-gray-300 rounded-lg text-sm text-gray-500 hover:bg-gray-50 w-full"
                >
                  + 添加目录
                </button>
              ) : (
                <div className="space-y-2">
                  <div className="flex gap-2">
                    <input
                      type="text"
                      value={manualScanPath}
                      onChange={(e) => setManualScanPath(e.target.value)}
                      onKeyDown={(e) => e.key === 'Enter' && confirmManualScanPath()}
                      placeholder="/Users/yourname/Downloads"
                      className="flex-1 border border-gray-300 rounded-lg px-3 py-2 text-sm text-gray-900 bg-white focus:outline-none focus:ring-2 focus:ring-blue-500"
                    />
                    <button
                      onClick={() => scanPickerRef.current?.click()}
                      title="浏览选择文件夹"
                      className="px-3 py-2 border border-gray-300 rounded-lg text-sm text-gray-600 hover:bg-gray-50 transition-colors"
                    >
                      📎
                    </button>
                    <button
                      onClick={confirmManualScanPath}
                      disabled={!manualScanPath.trim()}
                      className="px-3 py-2 bg-blue-600 text-white rounded-lg text-sm hover:bg-blue-700 disabled:opacity-40 transition-colors"
                    >
                      添加
                    </button>
                  </div>
                  <p className="text-xs text-gray-400">📎 选择文件夹后会填入名称，请补全完整路径再点添加</p>
                </div>
              )}
            </div>
          )}

          {/* Step 3: Archive path */}
          {step === 3 && (
            <div className="space-y-4">
              <h2 className="text-xl font-bold text-gray-900">选择归档目标</h2>
              <p className="text-sm text-gray-500">整理后的文件将按分类存放到此目录。</p>
              {/* Hidden folder picker */}
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
                  <div className="flex-1 bg-gray-50 border border-gray-200 rounded-lg px-3 py-3 min-h-[44px]">
                    {settings.archivePath
                      ? <span className="font-mono text-sm text-gray-700">{settings.archivePath}</span>
                      : <span className="text-sm text-gray-400 italic">点击右侧选择目录</span>}
                  </div>
                  <button onClick={pickArchivePath} className="px-3 py-2.5 border border-gray-300 rounded-lg text-sm text-gray-600 hover:bg-gray-50 whitespace-nowrap">
                    选择…
                  </button>
                </div>
              ) : (
                <div className="space-y-2">
                  <div className="flex gap-2">
                    <input
                      type="text"
                      value={settings.archivePath}
                      onChange={(e) => setSettings({ archivePath: e.target.value })}
                      placeholder="/Users/yourname/Organized"
                      className="flex-1 border border-gray-300 rounded-lg px-3 py-2 text-sm text-gray-900 bg-white focus:outline-none focus:ring-2 focus:ring-blue-500"
                      autoFocus
                    />
                    <button
                      onClick={() => archivePickerRef.current?.click()}
                      title="浏览选择文件夹"
                      className="px-3 py-2 border border-gray-300 rounded-lg text-sm text-gray-600 hover:bg-gray-50 transition-colors"
                    >
                      📎
                    </button>
                  </div>
                  <p className="text-xs text-gray-400">📎 选择文件夹后会填入名称，请补全完整路径</p>
                </div>
              )}
              {settings.archivePath && (
                <div className="bg-blue-50 rounded-lg p-3 text-sm text-blue-700">
                  📂 归档结构示例：<br />
                  <span className="font-mono text-xs">{settings.archivePath}/文档/合同/2026-03-15_合同.pdf</span>
                </div>
              )}
            </div>
          )}

          {/* Step 4: Done */}
          {step === 4 && (
            <div className="text-center pt-4">
              <div className="text-6xl mb-4">🎉</div>
              <h2 className="text-2xl font-bold text-gray-900 mb-3">配置完成！</h2>
              <p className="text-gray-500 leading-relaxed">
                您已完成所有设置。<br />
                点击「开始使用」进入控制台，扫描并整理您的文件。
              </p>
              <div className="mt-4 text-sm text-gray-400">
                所有设置均可在「设置」页面随时修改
              </div>
            </div>
          )}
        </div>

        {/* Footer buttons */}
        <div className="px-8 pb-6 flex items-center justify-between">
          <button
            onClick={step === 0 ? onComplete : () => setStep(step - 1)}
            className="text-sm text-gray-400 hover:text-gray-600"
          >
            {step === 0 ? '跳过引导' : '← 上一步'}
          </button>
          <button
            onClick={step === STEPS.length - 1 ? onComplete : () => setStep(step + 1)}
            disabled={!canNext()}
            className="px-6 py-2 bg-blue-600 text-white rounded-lg font-medium hover:bg-blue-700 disabled:opacity-40 transition-colors"
          >
            {step === STEPS.length - 1 ? '开始使用 →' : '下一步 →'}
          </button>
        </div>
      </div>
    </div>
  )
}
