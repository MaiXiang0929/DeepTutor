'use client'
import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import MarkdownRenderer from '@/components/common/MarkdownContent'
import {
  obsidianRequest,
  obsidianWorkspaceUrl,
  parseObsidianLink,
  prepareObsidianMarkdown,
  previewEndpoint,
  type ObsidianTarget,
  type NotePreview,
  type NoteDraft,
} from '@/lib/obsidian-learning'

const fieldClass =
  'block w-full rounded border border-[var(--border)] bg-[var(--background)] p-2 text-[var(--foreground)]'
type LinkCandidate = { path: string; link: string; shared_terms: string[]; score: number }
export function ObsidianPreview({ target }: { target: ObsidianTarget }) {
  const { t } = useTranslation()
  const [data, setData] = useState<NotePreview | NoteDraft | null>(null)
  const [error, setError] = useState('')
  const [attempt, setAttempt] = useState(0)
  const [path, setPath] = useState('')
  const [content, setContent] = useState('')
  const [properties, setProperties] = useState('')
  const [preview, setPreview] = useState(false)
  const [saving, setSaving] = useState(false)
  const [candidates, setCandidates] = useState<LinkCandidate[] | null>(null)
  const [selected, setSelected] = useState<string[]>([])
  const [loadingLinks, setLoadingLinks] = useState(false)
  const body = useRef<HTMLDivElement>(null)
  const endpoint = previewEndpoint(target)
  useEffect(() => {
    let active = true
    obsidianRequest<NotePreview | NoteDraft>(endpoint)
      .then(value => {
        if (!active) return
        setData(value)
        setError('')
        if ('content' in value) {
          setPath(value.path)
          setContent(value.content)
          setProperties(JSON.stringify(value.properties, null, 2))
        }
      })
      .catch(reason => {
        if (active) setError(String(reason.message ?? reason))
      })
    return () => {
      active = false
    }
  }, [endpoint, attempt])
  const heading = target.heading || (data && 'heading' in data ? data.heading : '')
  useEffect(() => {
    if (!heading || !body.current) return
    const highlight = () => {
      const found = Array.from(
        body.current?.querySelectorAll<HTMLElement>('h1,h2,h3,h4,h5,h6') ?? []
      ).find(element => element.textContent?.trim() === heading.replace(/^#+\s*/, ''))
      if (found) {
        found.tabIndex = -1
        found.style.backgroundColor = 'var(--accent)'
        found.setAttribute('data-obsidian-heading', 'true')
        found.focus()
        found.scrollIntoView?.({ block: 'center' })
      }
    }
    highlight()
    const observer = new MutationObserver(highlight)
    observer.observe(body.current, { childList: true, subtree: true })
    return () => observer.disconnect()
  }, [heading, data, preview])
  async function save() {
    if (!data || !('id' in data) || saving || data.status === 'saved') return
    setError('')
    try {
      const props: unknown = JSON.parse(properties)
      if (!props || typeof props !== 'object' || Array.isArray(props))
        throw new Error(t('Properties must be a JSON object.'))
      setSaving(true)
      const saved = await obsidianRequest<NoteDraft>(
        obsidianWorkspaceUrl(
          `/api/obsidian/drafts/${encodeURIComponent(data.id)}/save`,
          target.workspace
        ),
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ path, content, properties: props }),
        }
      )
      setData(saved)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason))
    } finally {
      setSaving(false)
    }
  }
  async function updateLinks() {
    if (!data || 'id' in data || loadingLinks) return
    setLoadingLinks(true)
    setError('')
    setSelected([])
    try {
      const query = new URLSearchParams({ kb: data.kb, note: data.path })
      const result = await obsidianRequest<{ candidates: LinkCandidate[] }>(
        obsidianWorkspaceUrl(`/api/obsidian/link-suggestions?${query}`, target.workspace)
      )
      setCandidates(result.candidates)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason))
    } finally { setLoadingLinks(false) }
  }
  async function prepareLinks() {
    if (!data || 'id' in data || !selected.length || loadingLinks) return
    setLoadingLinks(true)
    setError('')
    try {
      const result = await obsidianRequest<NoteDraft>(obsidianWorkspaceUrl('/api/obsidian/link-draft', target.workspace), {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ kb: data.kb, note: data.path, paths: selected }),
      })
      setData(result)
      setPath(result.path)
      setContent(result.content)
      setProperties(JSON.stringify(result.properties, null, 2))
      setPreview(true)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason))
    } finally { setLoadingLinks(false) }
  }
  if (!data)
    return (
      <div>
        {error ? (
          <>
            <p role="alert">{error}</p>
            <button
              onClick={() => {
                setError('')
                setAttempt(value => value + 1)
              }}
            >
              {t('Retry')}
            </button>
          </>
        ) : (
          <p role="status">{t('Loading note…')}</p>
        )}
      </div>
    )
  const draft = 'id' in data
  return (
    <div className="space-y-4">
      <h3 className="break-all font-semibold">{data.path}</h3>
      <p className="break-all text-sm text-[var(--muted-foreground)]">
        {t('Knowledge base')}: {data.kb}
      </p>
      {error && (
        <p role="alert" className="text-red-600">
          {error}
        </p>
      )}
      {draft ? (
        <>
          <p>{t('Review the destination, content and properties before saving to your vault.')}</p>
          <p>
            {t('Draft mode')}:{' '}
            {data.mode === 'create'
              ? t('Create note')
              : data.mode === 'append'
                ? t('Append to note')
                : t('Update properties')}
          </p>
          <label className="block">
            {t('Destination path')}
            <input
              className={fieldClass}
              value={path}
              onChange={event => setPath(event.target.value)}
              readOnly={data.mode !== 'create'}
              disabled={data.status === 'saved' || saving}
            />
          </label>
          <label className="block">
            {t('Note content')}
            <textarea
              className={fieldClass}
              rows={14}
              value={content}
              onChange={event => setContent(event.target.value)}
              readOnly={data.mode === 'property'}
              disabled={data.status === 'saved' || saving}
            />
          </label>
          <label className="block">
            {t('Properties (JSON)')}
            <textarea
              className={fieldClass}
              rows={6}
              value={properties}
              onChange={event => setProperties(event.target.value)}
              disabled={data.status === 'saved' || saving}
            />
          </label>
          <div className="flex gap-4">
            <button
              type="button"
              className="rounded border px-3 py-2"
              onClick={() => setPreview(value => !value)}
            >
              {t('Preview')}
            </button>
            <button
              type="button"
              className="rounded bg-[var(--primary)] px-3 py-2 text-[var(--primary-foreground)] disabled:opacity-50"
              onClick={save}
              disabled={saving || data.status === 'saved'}
            >
              {data.status === 'saved' ? t('Saved') : saving ? t('Saving…') : t('Save to vault')}
            </button>
          </div>
          {data.note_href && parseObsidianLink(data.note_href, window.location.origin) && (
            <a href={obsidianWorkspaceUrl(data.note_href, target.workspace)}>
              {t('Open saved note')}
            </a>
          )}
          {preview && (
            <div ref={body}>
              <MarkdownRenderer
                content={prepareObsidianMarkdown(content, data.kb, path, target.workspace)}
                allowHtml={false}
                enableImages
              />
            </div>
          )}
        </>
      ) : (
        <>
          <button type="button" className="rounded border px-3 py-2" onClick={updateLinks} disabled={loadingLinks}>
            {loadingLinks ? '正在查找…' : '更新双链'}
          </button>
          {candidates && (
            <section className="space-y-2" aria-label="双链候选">
              <p>按内容相似度查找的候选，请检查相关性后选择。</p>
              {candidates.length === 0 && <p>没有找到新的候选笔记。</p>}
              {candidates.map(candidate => (
                <label key={candidate.path} className="block">
                  <input type="checkbox" checked={selected.includes(candidate.path)}
                    onChange={event => setSelected(current => event.target.checked ? [...current, candidate.path] : current.filter(path => path !== candidate.path))} />{' '}
                  {candidate.path}
                  <span className="ml-2 text-sm">（共同词：{candidate.shared_terms.join('、')}）</span>
                </label>
              ))}
              {candidates.length > 0 && <button type="button" className="rounded border px-3 py-2" disabled={!selected.length || loadingLinks} onClick={prepareLinks}>生成双链草稿</button>}
            </section>
          )}
          {data.changed && (
            <p role="status">
              {t('This note changed since it was cited. Showing the current version.')}
            </p>
          )}
          {heading && (
            <p>
              {t('Referenced heading')}: {heading}
            </p>
          )}
          {data.obsidian_uri?.startsWith('obsidian://') && (
            <a className="underline" href={data.obsidian_uri}>
              {t('Open in Obsidian')}
            </a>
          )}
          {Object.keys(data.frontmatter).length > 0 && (
            <details>
              <summary>{t('Note properties')}</summary>
              <pre className="overflow-auto">{JSON.stringify(data.frontmatter, null, 2)}</pre>
            </details>
          )}
          <div ref={body}>
            <MarkdownRenderer
              content={prepareObsidianMarkdown(data.body, data.kb, data.path, target.workspace)}
              allowHtml={false}
              enableImages
            />
          </div>
          {data.links.length > 0 && (
            <nav aria-label={t('Related notes')} className="flex flex-wrap gap-3">
              {data.links
                .filter(link => parseObsidianLink(link.href, window.location.origin))
                .map((link, index) => (
                  <a
                    className="underline"
                    key={index}
                    href={obsidianWorkspaceUrl(link.href, target.workspace)}
                  >
                    {link.label}
                  </a>
                ))}
            </nav>
          )}
        </>
      )}
    </div>
  )
}
