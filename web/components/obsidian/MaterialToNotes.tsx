'use client'
import { useCallback, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { obsidianRequest, materialPrompt, type Material } from '@/lib/obsidian-learning'
import { ObsidianDialog } from './ObsidianDialog'

export function MaterialToNotes({
  kb,
  onPrefill,
}: {
  kb: string
  onPrefill: (text: string) => void
}) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  const [url, setUrl] = useState('')
  const [material, setMaterial] = useState<Material | null>(null)
  const [text, setText] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const close = useCallback(() => setOpen(false), [])
  async function extract(file?: File) {
    setBusy(true)
    setError('')
    try {
      const form = new FormData()
      if (file) form.append('file', file)
      const result = await obsidianRequest<Material>(
        file ? '/api/obsidian/material' : '/api/obsidian/material/url',
        file
          ? { method: 'POST', body: form }
          : {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ url }),
            }
      )
      setMaterial(result)
      setText(result.text)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason))
    } finally {
      setBusy(false)
    }
  }
  return (
    <>
      <button
        type="button"
        className="mb-2 rounded border border-[var(--border)] px-3 py-1 text-sm"
        onClick={() => setOpen(true)}
      >
        {t('Materials to notes')}
      </button>
      {open && (
        <ObsidianDialog title={t('Materials to notes')} onClose={close}>
          <div className="space-y-4">
            <p>
              {t(
                'Upload Markdown, text or a text PDF, or extract a webpage. Review the text, then prepare a message. Nothing is sent or saved automatically.'
              )}
            </p>
            <p>
              {t(
                'Click note citations to inspect evidence. Open draft links to review and save learning notes.'
              )}
            </p>
            <label className="block">
              {t('Material file')}
              <input
                className="block w-full"
                type="file"
                accept=".md,.txt,.pdf"
                disabled={busy}
                onChange={event => {
                  const file = event.target.files?.[0]
                  if (file) void extract(file)
                  event.target.value = ''
                }}
              />
            </label>
            <label className="block">
              {t('Material URL')}
              <input
                className="block w-full rounded border bg-[var(--background)] p-2"
                type="url"
                value={url}
                onChange={event => setUrl(event.target.value)}
                disabled={busy}
              />
            </label>
            <button
              className="rounded border px-3 py-2"
              type="button"
              disabled={busy || !url.trim()}
              onClick={() => void extract()}
            >
              {t('Extract URL')}
            </button>
            {busy && <p role="status">{t('Extracting material…')}</p>}
            {error && (
              <p role="alert" className="text-red-600">
                {error}
              </p>
            )}
            {material && (
              <>
                <h3>{material.title}</h3>
                <p className="break-all">{material.source}</p>
                {material.truncated && (
                  <p role="status">
                    {t('The source was truncated. Review the extracted text before continuing.')}
                  </p>
                )}
                <label className="block">
                  {t('Source text')}
                  <textarea
                    rows={15}
                    className="block w-full rounded border bg-[var(--background)] p-2"
                    value={text}
                    onChange={event => setText(event.target.value)}
                  />
                </label>
                <button
                  className="rounded border px-3 py-2"
                  type="button"
                  disabled={busy || !text.trim()}
                  onClick={() => {
                    onPrefill(materialPrompt(kb, text, material.source))
                    close()
                  }}
                >
                  {t('Prepare learning note')}
                </button>
              </>
            )}
          </div>
        </ObsidianDialog>
      )}
    </>
  )
}
