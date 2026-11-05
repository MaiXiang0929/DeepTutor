'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import { ObsidianPreview } from '@/components/obsidian/ObsidianPreview'
import { obsidianRequest, obsidianWorkspaceUrl } from '@/lib/obsidian-learning'

type Diff = { kind: string; before: string[]; after: string[] }
type Change = { path: string; kind: 'added' | 'deleted' | 'modified'; before: string | null; after: string | null; diff: Diff[]; added_links: string[]; removed_links: string[] }
type Result = { changes: Change[]; updated: number | null; pending: boolean; offline?: boolean }

export default function ObsidianVaultFiles({ kbRef }: { kbRef: string }) {
  const [result, setResult] = useState<Result | null>(null)
  const [selected, setSelected] = useState<string | null>(null)
  const [showNote, setShowNote] = useState(false)
  const [error, setError] = useState('')
  const busy = useRef(false)
  const [workspace] = useState(() => {
    if (typeof window === 'undefined') return undefined
    const params = new URLSearchParams(window.location.search)
    return params.has('dt_workspace') ? params.get('dt_workspace') ?? '' : undefined
  })
  const load = useCallback(async () => {
    if (busy.current) return
    busy.current = true
    try {
      const url = obsidianWorkspaceUrl(`/api/obsidian/changes?kb=${encodeURIComponent(kbRef)}`, workspace)
      const value = await obsidianRequest<Result>(url)
      setResult(value)
      setError('')
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason))
    } finally { busy.current = false }
  }, [kbRef, workspace])
  useEffect(() => {
    void load()
    const timer = window.setInterval(() => { if (document.visibilityState === 'visible') void load() }, 3000)
    const onFocus = () => { void load() }
    window.addEventListener('focus', onFocus)
    return () => { window.clearInterval(timer); window.removeEventListener('focus', onFocus) }
  }, [load])
  const change = result?.changes.find(item => item.path === selected)
  const labels = { added: '新增', modified: '修改', deleted: '删除' }
  return <div className="flex h-full min-h-0">
    <aside className="w-72 shrink-0 overflow-auto border-r border-[var(--border)] p-4">
      <div className="mb-3 flex items-center justify-between"><span>最近一次变更 {result?.changes.length ?? 0}</span><button type="button" onClick={() => void load()} aria-label="刷新变更">↻</button></div>
      {error && <p role="alert">无法读取变更：{error}</p>}
      {!result && !error && <p role="status">正在读取…</p>}
      {result?.pending && <p role="status">正在收集变更…</p>}
      {result?.offline && result.changes.length > 0 && <p>离线期间的变化</p>}
      {result && !result.pending && result.changes.length === 0 && <p>已建立基线，尚未检测到新的变更。</p>}
      <ul>{result?.changes.map(item => <li key={item.path}><button type="button" className="w-full rounded p-2 text-left hover:bg-[var(--muted)]" onClick={() => { setSelected(item.path); setShowNote(false) }}><span>{labels[item.kind]} · </span>{item.path}</button></li>)}</ul>
    </aside>
    <main className="min-w-0 flex-1 overflow-auto p-5">
      {!change ? <p>请选择一篇变更笔记。</p> : <div className="space-y-4">
        <h2 className="break-all font-semibold">{change.path}</h2>
        <p>新增双链：{change.added_links.length ? change.added_links.map(link => `[[${link}]]`).join('、') : '无'}</p>
        <p>移除双链：{change.removed_links.length ? change.removed_links.map(link => `[[${link}]]`).join('、') : '无'}</p>
        {change.after !== null && <button className="rounded border px-3 py-2" type="button" onClick={() => setShowNote(!showNote)}>{showNote ? '关闭笔记预览' : '打开笔记与更新双链'}</button>}
        {showNote && <ObsidianPreview key={change.path} target={{ kb: kbRef, note: change.path, workspace }} />}
        <div className="grid grid-cols-2 gap-4">
          {(['before', 'after'] as const).map(side => <section key={side} className="min-w-0 rounded border p-3"><h3 className="mb-2 font-semibold">{side === 'before' ? '修改前' : '修改后'}</h3>
            {change[side] === null ? <p>{side === 'before' ? '笔记不存在' : '笔记已删除'}</p> : <pre className="whitespace-pre-wrap break-words">{change.diff.map((part, index) => <span key={index} className={(side === 'before' && (part.kind === 'delete' || part.kind === 'replace')) ? 'bg-red-500/20' : (side === 'after' && (part.kind === 'insert' || part.kind === 'replace')) ? 'bg-green-500/20' : ''}>{part[side].map(line => line + '\n').join('')}</span>)}</pre>}
          </section>)}
        </div>
      </div>}
    </main>
  </div>
}
