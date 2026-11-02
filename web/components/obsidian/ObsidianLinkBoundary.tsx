'use client'
import { useCallback, useState, type ReactNode, type MouseEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { parseObsidianLink, type ObsidianTarget } from '@/lib/obsidian-learning'
import { ObsidianPreview } from './ObsidianPreview'
import { ObsidianDialog } from './ObsidianDialog'

export function ObsidianLinkBoundary({ children }: { children: ReactNode }) {
  const { t } = useTranslation()
  const [target, setTarget] = useState<ObsidianTarget | null>(null)
  const close = useCallback(() => setTarget(null), [])
  function click(event: MouseEvent<HTMLDivElement>) {
    if (
      event.defaultPrevented ||
      event.button !== 0 ||
      event.ctrlKey ||
      event.metaKey ||
      event.shiftKey ||
      event.altKey
    )
      return
    const anchor = (event.target as Element).closest<HTMLAnchorElement>('a[href]')
    if (!anchor || anchor.hasAttribute('download')) return
    const parsed = parseObsidianLink(anchor.getAttribute('href') ?? '', window.location.origin)
    if (parsed) {
      event.preventDefault()
      event.stopPropagation()
      setTarget(parsed)
    }
  }
  return (
    <div onClick={click}>
      {children}
      {target && (
        <ObsidianDialog title={t('Obsidian note preview')} onClose={close}>
          <ObsidianPreview key={JSON.stringify(target)} target={target} />
        </ObsidianDialog>
      )}
    </div>
  )
}
