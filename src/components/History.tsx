import { useEffect, useState } from 'react'
import { useBackend } from '../hooks/useBackend'

interface Operation {
  operation_id: string
  timestamp: string
  mode: string
  dry_run: boolean
  ai_model_used: string
  rolled_back?: boolean
  rolled_back_at?: string
  actions: {
    source: string
    destination: string
    status: string
    classification: { category: string; confidence: number }
    classification_method: string
    error: string | null
  }[]
}

export default function History() {
  const { getHistory, rollback, loading } = useBackend()
  const [operations, setOperations] = useState<Operation[]>([])
  const [expanded, setExpanded] = useState<string | null>(null)

  useEffect(() => {
    getHistory().then((r) => {
      if (r) setOperations((r as { operations: Operation[] }).operations)
    })
  }, [])

  const handleRollback = async (id: string) => {
    if (!confirm('确定要回滚此次操作吗？')) return
    await rollback(id)
    const r = await getHistory()
    if (r) setOperations((r as { operations: Operation[] }).operations)
  }

  if (loading) return (
    <div className="p-6 flex items-center justify-center h-full text-gray-400">加载中…</div>
  )

  return (
    <div className="p-6 h-full flex flex-col gap-4">
      <h1 className="text-2xl font-semibold">操作历史</h1>

      {operations.length === 0 ? (
        <div className="flex-1 flex items-center justify-center text-gray-400">
          <div className="text-center">
            <div className="text-5xl mb-3">📋</div>
            <p className="text-lg font-medium">暂无操作记录</p>
            <p className="text-sm mt-1">执行归档后，操作记录将显示在这里</p>
          </div>
        </div>
      ) : (
        <div className="space-y-3 overflow-auto">
          {operations.map((op) => (
            <div key={op.operation_id} className="border border-gray-200 dark:border-gray-700 rounded-lg overflow-hidden">
              <div className="flex items-center justify-between px-4 py-3 bg-gray-50 dark:bg-gray-800">
                <div className="flex items-center gap-3">
                  <span className="text-xs text-gray-500">{new Date(op.timestamp).toLocaleString('zh-CN')}</span>
                  <span className={`text-xs rounded px-2 py-0.5 ${
                    op.mode === 'rollback' ? 'bg-orange-100 text-orange-700' :
                    op.rolled_back ? 'bg-gray-100 text-gray-500' :
                    'bg-blue-100 text-blue-700'
                  }`}>
                    {op.mode === 'rollback' ? '回滚操作' : op.rolled_back ? '已回滚' : op.mode}
                  </span>
                  <span className="text-xs text-gray-600">{op.actions.length} 个文件</span>
                  {op.ai_model_used && <span className="text-xs text-gray-400">模型：{op.ai_model_used}</span>}
                </div>
                <div className="flex gap-2">
                  <button
                    onClick={() => setExpanded(expanded === op.operation_id ? null : op.operation_id)}
                    className="text-xs text-gray-500 hover:text-gray-800"
                  >
                    {expanded === op.operation_id ? '收起' : '展开详情'}
                  </button>
                  {!op.rolled_back && op.mode !== 'rollback' && (
                    <button
                      onClick={() => handleRollback(op.operation_id)}
                      className="text-xs text-red-500 hover:text-red-700"
                    >
                      回滚
                    </button>
                  )}
                </div>
              </div>
              {expanded === op.operation_id && (
                <div className="divide-y divide-gray-100">
                  {op.actions.map((action, i) => (
                    <div key={i} className="px-4 py-2 flex items-start gap-3 text-xs">
                      <span className={`mt-0.5 shrink-0 ${action.status === 'success' ? 'text-green-500' : 'text-red-500'}`}>
                        {action.status === 'success' ? '✅' : '❌'}
                      </span>
                      <div className="flex-1 min-w-0">
                        <p className="font-mono text-gray-500 truncate">{action.source.split('/').pop()}</p>
                        <p className="text-gray-400 mt-0.5">→ {action.destination}</p>
                        {action.error && <p className="text-red-500 mt-0.5">{action.error}</p>}
                      </div>
                      <span className="shrink-0 text-gray-400">{action.classification?.category}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
