'use client'
import { useEffect, useRef, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

export function ObsidianDialog({
  children,
  onClose,
  title,
}: {
  children: ReactNode
  onClose: () => void
  title: string
}) {
  const { t } = useTranslation()
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null
    const panel = ref.current
    panel?.focus()
    const keydown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault()
        event.stopPropagation()
        onClose()
      }
      if (event.key === 'Tab' && panel) {
        const focusable = Array.from(
          panel.querySelectorAll<HTMLElement>(
            'button:not([disabled]), a[href], input:not([disabled]), textarea:not([disabled]), [tabindex="0"]'
          )
        )
        const first = focusable[0],
          last = focusable.at(-1)
        if (!first) {
          event.preventDefault()
          panel.focus()
        } else if (
          event.shiftKey &&
          (document.activeElement === first || document.activeElement === panel)
        ) {
          event.preventDefault()
          last?.focus()
        } else if (
          !event.shiftKey &&
          (document.activeElement === last || document.activeElement === panel)
        ) {
          event.preventDefault()
          first.focus()
        }
      }
    }
    document.addEventListener('keydown', keydown, true)
    return () => {
      document.removeEventListener('keydown', keydown, true)
      previous?.focus()
    }
  }, [onClose])
  return (
    <div
      className="fixed inset-0 z-[100] bg-black/20"
      onClick={event => {
        if (event.target === event.currentTarget) onClose()
      }}
    >
      <div
        ref={ref}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        tabIndex={-1}
        className="absolute inset-y-0 right-0 w-full max-w-2xl overflow-auto border-l border-[var(--border)] bg-[var(--background)] p-6 text-[var(--foreground)] shadow-xl"
      >
        <div className="mb-4 flex items-center justify-between">
          <h2 className="font-semibold">{title}</h2>
          <button type="button" onClick={onClose} className="rounded border px-3 py-1">
            {t('Close')}
          </button>
        </div>
        {children}
      </div>
    </div>
  )
}
