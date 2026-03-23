import { useState } from 'react'

// ─── Types ────────────────────────────────────────────────────────────────────

export interface ClassificationOption {
  category: string
  subcategory: string
  suggested_name: string
  confidence: number
  reasoning: string
}

export interface ClassificationResult {
  path: string
  options: ClassificationOption[]
  classification_method: string
  selected_option_index: number
}

// Flat format expected by the execute endpoint
export interface FlatClassification {
  path: string
  category: string
  subcategory: string
  sub_path?: string[]       // multi-level path: [L1, L2, L3, ...]
  suggested_name: string
  confidence: number
  reasoning: string
  classification_method: string
}

interface Props {
  classifications: unknown[]
  archiveRoot: string
  onExecute: (confirmed: FlatClassification[]) => void
  onBack: () => void
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function confidenceBadge(c: number) {
  const pct = Math.round(c * 100)
  if (c >= 0.85) return <span className="text-xs bg-green-100 text-green-700 rounded px-1.5 py-0.5 font-medium">{pct}%</span>
  if (c >= 0.6)  return <span className="text-xs bg-yellow-100 text-yellow-700 rounded px-1.5 py-0.5 font-medium">{pct}%</span>
  return               <span className="text-xs bg-red-100 text-red-700 rounded px-1.5 py-0.5 font-medium">{pct}%</span>
}

function fileExt(path: string) {
  return path.includes('.') ? '.' + path.split('.').pop() : ''
}

// Normalise the API response — handles both new multi-option and legacy flat format
function normalise(raw: unknown[]): ClassificationResult[] {
  return raw.map((r) => {
    const item = r as Record<string, unknown>
    if (Array.isArray(item.options)) return item as unknown as ClassificationResult
    // Legacy flat format → wrap in options array
    return {
      path: item.path as string,
      classification_method: (item.classification_method as string) ?? 'ai',
      selected_option_index: 0,
      options: [{
        category: (item.category as string) ?? '其他',
        subcategory: (item.subcategory as string) ?? '其他',
        suggested_name: (item.suggested_name as string) ?? '',
        confidence: (item.confidence as number) ?? 0.7,
        reasoning: (item.reasoning as string) ?? '',
      }],
    }
  })
}

// ─── Component ────────────────────────────────────────────────────────────────

export default function FilePreview({ classifications, archiveRoot, onExecute, onBack }: Props) {
  const items = normalise(classifications)

  // Which row is checked for execution
  const [selected, setSelected] = useState<Set<number>>(new Set(items.map((_, i) => i)))
  // Which option (0-based) is chosen per row
  const [chosenOpts, setChosenOpts] = useState<Record<number, number>>(
    Object.fromEntries(items.map((item, i) => [i, item.selected_option_index ?? 0]))
  )
  // Inline editable name overrides
  const [editNames, setEditNames] = useState<Record<number, string>>({})
  // Expanded row for reasoning
  const [expanded, setExpanded] = useState<number | null>(null)

  const toggleAll = () => {
    if (selected.size === items.length) setSelected(new Set())
    else setSelected(new Set(items.map((_, i) => i)))
  }

  const toggle = (i: number) => {
    const next = new Set(selected)
    if (next.has(i)) next.delete(i); else next.add(i)
    setSelected(next)
  }

  const selectOption = (rowIdx: number, optIdx: number) => {
    setChosenOpts((prev) => ({ ...prev, [rowIdx]: optIdx }))
    // Clear name edit when switching options
    setEditNames((prev) => { const next = { ...prev }; delete next[rowIdx]; return next })
  }

  const getActiveOpt = (i: number): ClassificationOption => {
    const item = items[i]
    return item.options[chosenOpts[i] ?? 0] ?? item.options[0]
  }

  const getDestination = (i: number): string => {
    const opt = getActiveOpt(i)
    const name = editNames[i] ?? opt.suggested_name
    const ext = fileExt(items[i].path)
    return `${archiveRoot}/${opt.category}/${opt.subcategory}/${name}${ext}`
  }

  const handleExecute = () => {
    const confirmed: FlatClassification[] = items
      .filter((_, i) => selected.has(i))
      .map((item, i) => {
        const opt = getActiveOpt(i)
        return {
          path: item.path,
          category: opt.category,
          subcategory: opt.subcategory,
          suggested_name: editNames[i] ?? opt.suggested_name,
          confidence: opt.confidence,
          reasoning: opt.reasoning,
          classification_method: item.classification_method,
        }
      })
    onExecute(confirmed)
  }

  const selectedCount = selected.size

  return (
    <div className="flex-1 flex flex-col gap-3 overflow-hidden">
      {/* Toolbar */}
      <div className="flex items-center justify-between">
        <p className="text-sm text-gray-500">
          已选 <span className="font-medium text-gray-800">{selectedCount}</span> / {items.length} 个文件
          {items.some((item) => item.options.length > 1) && (
            <span className="ml-2 text-blue-600">· 点击分类标签可切换方案</span>
          )}
        </p>
        <div className="flex gap-2">
          <button onClick={onBack} className="px-3 py-1.5 border border-gray-300 text-sm text-gray-600 rounded-lg hover:bg-gray-50 transition-colors">
            返回
          </button>
          <button
            onClick={handleExecute}
            disabled={selectedCount === 0}
            className="px-4 py-1.5 bg-blue-600 text-white text-sm font-medium rounded-lg hover:bg-blue-700 disabled:opacity-50 transition-colors"
          >
            执行归档（{selectedCount} 个）
          </button>
        </div>
      </div>

      {/* Table */}
      <div className="flex-1 overflow-auto rounded-lg border border-gray-200">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 sticky top-0 z-10">
            <tr>
              <th className="px-3 py-3 w-8">
                <input
                  type="checkbox"
                  checked={selectedCount === items.length && items.length > 0}
                  onChange={toggleAll}
                  className="rounded"
                />
              </th>
              <th className="text-left px-3 py-3 font-medium text-gray-600 w-40">源文件</th>
              <th className="text-left px-3 py-3 font-medium text-gray-600">分类方案</th>
              <th className="text-left px-3 py-3 font-medium text-gray-600 w-44">文件名</th>
              <th className="text-left px-3 py-3 font-medium text-gray-600 w-16">置信度</th>
              <th className="w-10 px-3 py-3"></th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {items.map((item, i) => {
              const activeOpt = getActiveOpt(i)
              const isSelected = selected.has(i)
              const hasMultiple = item.options.length > 1

              return (
                <>
                  <tr
                    key={i}
                    className={`transition-colors ${isSelected ? 'bg-white' : 'bg-gray-50 opacity-60'}`}
                  >
                    {/* Checkbox */}
                    <td className="px-3 py-2.5 text-center">
                      <input type="checkbox" checked={isSelected} onChange={() => toggle(i)} className="rounded" />
                    </td>

                    {/* Source file */}
                    <td className="px-3 py-2.5 font-mono text-xs text-gray-600 max-w-[160px]" title={item.path}>
                      <div className="truncate">{item.path.split('/').pop()}</div>
                    </td>

                    {/* Classification options */}
                    <td className="px-3 py-2.5">
                      <div className="flex flex-wrap gap-1">
                        {item.options.map((opt, oi) => (
                          <button
                            key={oi}
                            onClick={() => selectOption(i, oi)}
                            title={opt.reasoning}
                            className={`px-2 py-0.5 rounded text-xs border transition-colors whitespace-nowrap ${
                              (chosenOpts[i] ?? 0) === oi
                                ? 'bg-blue-600 text-white border-blue-600'
                                : 'bg-white text-gray-600 border-gray-300 hover:border-blue-400 hover:text-blue-600'
                            }`}
                          >
                            {opt.category}/{opt.subcategory}
                            {hasMultiple && (
                              <span className="ml-1 opacity-75">{Math.round(opt.confidence * 100)}%</span>
                            )}
                          </button>
                        ))}
                      </div>
                      {item.classification_method === 'fallback_extension' && (
                        <span className="text-xs text-yellow-600 mt-0.5 block">⚠️ 扩展名规则</span>
                      )}
                    </td>

                    {/* Editable name */}
                    <td className="px-3 py-2.5">
                      <input
                        type="text"
                        value={editNames[i] ?? activeOpt.suggested_name}
                        onChange={(e) => setEditNames({ ...editNames, [i]: e.target.value })}
                        className="border border-transparent hover:border-gray-300 focus:border-blue-400 rounded px-1.5 py-0.5 text-xs w-full focus:outline-none text-gray-800 bg-transparent"
                      />
                    </td>

                    {/* Confidence */}
                    <td className="px-3 py-2.5">
                      {confidenceBadge(activeOpt.confidence)}
                    </td>

                    {/* Expand toggle */}
                    <td className="px-3 py-2.5 text-right">
                      <button
                        onClick={() => setExpanded(expanded === i ? null : i)}
                        className="text-xs text-gray-400 hover:text-gray-700"
                      >
                        {expanded === i ? '▲' : '▼'}
                      </button>
                    </td>
                  </tr>

                  {/* Expanded detail row */}
                  {expanded === i && (
                    <tr key={`${i}-detail`} className="bg-blue-50">
                      <td colSpan={6} className="px-6 py-3 space-y-1.5">
                        {item.options.map((opt, oi) => (
                          <div
                            key={oi}
                            className={`text-xs rounded p-2 ${(chosenOpts[i] ?? 0) === oi ? 'bg-blue-100 text-blue-800' : 'text-gray-600'}`}
                          >
                            <span className="font-medium">[方案{oi + 1}] {opt.category}/{opt.subcategory}</span>
                            {' · '}{opt.reasoning}
                          </div>
                        ))}
                        <p className="text-xs text-gray-500 font-mono pt-1">
                          目标路径：{getDestination(i)}
                        </p>
                      </td>
                    </tr>
                  )}
                </>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}
