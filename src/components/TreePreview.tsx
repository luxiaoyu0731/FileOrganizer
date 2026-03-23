/**
 * TreePreview.tsx
 *
 * Renders the AI-generated multi-level folder hierarchy (recursive).
 *
 * Features
 * --------
 * • Recursive collapsible folders at any depth
 * • Inline rename for any folder node (click ✏️)
 * • File chips that can be excluded with a single click
 * • Bottom bar shows selected count and a "确认归档" button
 */

import { useRef, useState } from 'react'
import type { FlatClassification } from './FilePreview'

// ─── Types ─────────────────────────────────────────────────────────────────────

/** Recursive tree node from backend */
export interface TreeNode {
  files: string[]
  children: Record<string, TreeNode>
}

export interface TreeResult {
  tree: Record<string, TreeNode>
  assignments: Record<string, { sub_path: string[] }>
  uncertain_paths?: string[]
}

interface Props {
  result: TreeResult
  archiveRoot: string
  onExecute: (confirmed: FlatClassification[]) => void
  onBack: () => void
}

// ─── Helpers ───────────────────────────────────────────────────────────────────

function fileBasename(path: string): string {
  return path.split('/').pop() ?? path
}

function fileExt(path: string): string {
  const name = fileBasename(path)
  const idx = name.lastIndexOf('.')
  return idx >= 0 ? name.slice(idx) : ''
}

function fileIcon(ext: string): string {
  const e = ext.toLowerCase()
  if (e === '.pdf') return '📄'
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

/** Collect all file paths from a recursive tree node */
function collectFiles(node: TreeNode): string[] {
  const paths = [...node.files]
  for (const child of Object.values(node.children)) {
    paths.push(...collectFiles(child))
  }
  return paths
}

/** Count total files across a Record of top-level nodes */
function countAllFiles(tree: Record<string, TreeNode>): number {
  return Object.values(tree).reduce((sum, node) => sum + collectFiles(node).length, 0)
}

// ─── Component ─────────────────────────────────────────────────────────────────

export default function TreePreview({ result, archiveRoot, onExecute, onBack }: Props) {
  const uncertainSet = new Set(result.uncertain_paths ?? [])

  // Folder renames: keyed by pathKey (segments joined with \0)
  const [renames, setRenames] = useState<Record<string, string>>({})
  const [deselected, setDeselected] = useState<Set<string>>(new Set())
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set())
  const [editingKey, setEditingKey] = useState<string | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  const totalFiles = countAllFiles(result.tree)
  const selectedCount = totalFiles - deselected.size

  // ── Handlers ──────────────────────────────────────────────────────────────

  const toggleFile = (path: string) =>
    setDeselected((prev) => {
      const next = new Set(prev)
      next.has(path) ? next.delete(path) : next.add(path)
      return next
    })

  const toggleCollapse = (pathKey: string) =>
    setCollapsed((prev) => {
      const next = new Set(prev)
      next.has(pathKey) ? next.delete(pathKey) : next.add(pathKey)
      return next
    })

  const commitRename = (pathKey: string, val: string) => {
    const name = val.trim()
    if (name) setRenames((prev) => ({ ...prev, [pathKey]: name }))
    setEditingKey(null)
  }

  const getDisplayName = (pathKey: string, originalName: string): string => {
    return renames[pathKey] ?? originalName
  }

  /** Build the renamed sub_path for a file, applying any renames along its path */
  const buildRenamedPath = (originalSubPath: string[]): string[] => {
    const result: string[] = []
    for (let i = 0; i < originalSubPath.length; i++) {
      const pathKey = originalSubPath.slice(0, i + 1).join('\0')
      result.push(renames[pathKey] ?? originalSubPath[i])
    }
    return result
  }

  const handleExecute = () => {
    const confirmed: FlatClassification[] = []
    for (const [filePath, info] of Object.entries(result.assignments)) {
      if (deselected.has(filePath)) continue
      const renamedPath = buildRenamedPath(info.sub_path)
      confirmed.push({
        path: filePath,
        category: renamedPath[0] ?? '',
        subcategory: renamedPath[1] ?? '',
        sub_path: renamedPath,
        suggested_name: fileBasename(filePath).replace(/\.[^.]+$/, ''),
        confidence: 0.9,
        reasoning: '智能分组',
        classification_method: 'ai_tree',
      })
    }
    onExecute(confirmed)
  }

  // ── Recursive folder renderer ─────────────────────────────────────────────

  function renderNode(
    node: TreeNode,
    originalName: string,
    parentSegments: string[],  // original segments leading to this node
    depth: number,
  ) {
    const currentSegments = [...parentSegments, originalName]
    const pathKey = currentSegments.join('\0')
    const displayName = getDisplayName(pathKey, originalName)
    const isCollapsed = collapsed.has(pathKey)
    const allPaths = collectFiles(node)
    const selectedHere = allPaths.filter((p) => !deselected.has(p)).length
    const hasChildren = Object.keys(node.children).length > 0 || node.files.length > 0

    const indent = depth * 24  // px per depth level
    const isTopLevel = depth === 0
    const bgClass = isTopLevel
      ? 'bg-gray-50 hover:bg-gray-100'
      : 'bg-white hover:bg-gray-50'
    const fontClass = isTopLevel
      ? 'text-sm font-semibold text-gray-800'
      : 'text-sm font-medium text-gray-700'

    return (
      <div key={pathKey}>
        {/* Folder header */}
        <div
          className={`flex items-center gap-2 px-4 py-2 cursor-pointer select-none group ${bgClass}`}
          style={{ paddingLeft: `${16 + indent}px` }}
          onClick={() => toggleCollapse(pathKey)}
        >
          {hasChildren && (
            <span className="text-gray-400 text-xs w-4 shrink-0">
              {isCollapsed ? '▶' : '▼'}
            </span>
          )}
          <span className="text-base shrink-0">{isTopLevel ? '📁' : '📂'}</span>

          {editingKey === pathKey ? (
            <input
              ref={inputRef}
              className={`flex-1 ${fontClass} border-b border-blue-400
                         bg-transparent outline-none min-w-0`}
              defaultValue={displayName}
              onClick={(e) => e.stopPropagation()}
              onBlur={(e) => commitRename(pathKey, e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') (e.target as HTMLInputElement).blur()
                if (e.key === 'Escape') setEditingKey(null)
              }}
              autoFocus
            />
          ) : (
            <span className={`flex-1 ${fontClass} min-w-0 truncate`}>
              {displayName}
            </span>
          )}

          <button
            className="text-gray-300 hover:text-blue-500 shrink-0 transition-colors opacity-0 group-hover:opacity-100"
            onClick={(e) => { e.stopPropagation(); setEditingKey(pathKey) }}
            title="重命名文件夹"
          >
            ✏️
          </button>
          <span className="text-xs text-gray-400 shrink-0 ml-1">
            {selectedHere} / {allPaths.length}
          </span>
        </div>

        {/* Children (recursive) and files */}
        {!isCollapsed && (
          <>
            {/* Child folders */}
            {Object.entries(node.children).map(([childName, childNode]) =>
              renderNode(childNode, childName, currentSegments, depth + 1)
            )}

            {/* Direct files in this node */}
            {node.files.length > 0 && (
              <div
                className="flex flex-wrap gap-2 py-2 pb-3"
                style={{ paddingLeft: `${40 + indent}px`, paddingRight: '16px' }}
              >
                {node.files.map((path) => {
                  const excluded = deselected.has(path)
                  const uncertain = uncertainSet.has(path)
                  const name = fileBasename(path)
                  const ext = fileExt(path)
                  return (
                    <button
                      key={path}
                      onClick={() => toggleFile(path)}
                      title={
                        excluded
                          ? `${path}\n点击重新加入`
                          : uncertain
                            ? `${path}\n⚠️ 未精确匹配关键词，归类可信度较低\n点击排除此文件`
                            : `${path}\n点击排除此文件`
                      }
                      className={`flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs
                                  border transition-all max-w-48 ${
                        excluded
                          ? 'opacity-40 line-through border-gray-200 text-gray-400 bg-gray-50'
                          : uncertain
                            ? 'border-amber-300 text-amber-700 bg-amber-50 hover:bg-amber-100 hover:border-amber-400'
                            : 'border-blue-200 text-blue-700 bg-blue-50 hover:bg-blue-100 hover:border-blue-300'
                      }`}
                    >
                      {uncertain && !excluded && <span className="shrink-0 text-amber-500">⚠</span>}
                      <span className="shrink-0">{fileIcon(ext)}</span>
                      <span className="truncate">{name}</span>
                    </button>
                  )
                })}
              </div>
            )}
          </>
        )}
      </div>
    )
  }

  // ─── Render ────────────────────────────────────────────────────────────────
  return (
    <div className="flex-1 flex flex-col gap-3 overflow-hidden min-h-0">

      {/* Info bar */}
      <div className="flex items-center justify-between text-sm">
        <span className="text-gray-500">
          AI 已生成文件夹结构，共{' '}
          <span className="font-semibold text-gray-800">{totalFiles}</span> 个文件
          {deselected.size > 0 && (
            <span className="text-orange-500 ml-2">（已排除 {deselected.size} 个）</span>
          )}
        </span>
        <span className="text-xs text-gray-400 bg-gray-100 rounded px-2 py-1 truncate max-w-56">
          归档至：{archiveRoot}
        </span>
      </div>

      {/* Uncertainty warning */}
      {uncertainSet.size > 0 && (
        <div className="flex items-start gap-2 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2 text-xs text-amber-700">
          <span className="text-base shrink-0">⚠️</span>
          <span>
            <span className="font-semibold">{uncertainSet.size} 个文件</span>
            {' '}未能精确匹配项目关键词，已自动归入最相近分组（标记为
            <span className="inline-block mx-1 px-1.5 py-0.5 rounded border border-amber-300 bg-amber-100 font-medium">橙色边框</span>
            ）。建议检查这些文件的归属是否正确，可点击排除不确定的文件。
          </span>
        </div>
      )}

      {/* Tip */}
      <p className="text-xs text-gray-400">
        点击 ✏️ 重命名文件夹 · 点击文件标签排除该文件 · 点击文件夹标题折叠/展开
      </p>

      {/* Tree */}
      <div className="flex-1 overflow-auto rounded-lg border border-gray-200 bg-white min-h-0">
        {Object.entries(result.tree).map(([name, node]) =>
          renderNode(node, name, [], 0)
        )}
      </div>

      {/* Bottom action bar */}
      <div className="flex items-center justify-between pt-1 shrink-0">
        <button
          onClick={onBack}
          className="px-4 py-2 border border-gray-300 text-gray-600 rounded-lg text-sm
                     hover:bg-gray-50 transition-colors"
        >
          ← 返回
        </button>
        <div className="flex items-center gap-3">
          <span className="text-sm text-gray-500">
            将归档 <span className="font-semibold text-gray-800">{selectedCount}</span> 个文件
          </span>
          <button
            onClick={handleExecute}
            disabled={selectedCount === 0}
            className="px-5 py-2 bg-green-600 text-white rounded-lg font-medium
                       hover:bg-green-700 disabled:opacity-50 transition-colors"
          >
            确认归档 →
          </button>
        </div>
      </div>
    </div>
  )
}
