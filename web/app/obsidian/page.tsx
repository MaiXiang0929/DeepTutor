'use client'
import { Suspense } from 'react'
import { useSearchParams } from 'next/navigation'
import { useTranslation } from 'react-i18next'
import { ObsidianPreview } from '@/components/obsidian/ObsidianPreview'
import { ObsidianLinkBoundary } from '@/components/obsidian/ObsidianLinkBoundary'
import { parseObsidianLink } from '@/lib/obsidian-learning'
import { useAuthStatus } from '@/hooks/useAuthStatus'
import { navVisibleUnderPolicy } from '@/components/sidebar/nav-entries'

function NotePage() {
  const { t } = useTranslation()
  const params = useSearchParams()
  const auth = useAuthStatus()
  const target = parseObsidianLink(`/obsidian?${params.toString()}`, 'http://localhost')
  if (auth.loading) return <p role="status">{t('Loading note…')}</p>
  if (!navVisibleUnderPolicy('/obsidian', auth.learningPolicy?.allowedSurfaces ?? null))
    return <p role="alert">{t('This feature is unavailable under your learning policy.')}</p>
  return (
    <main className="mx-auto max-w-4xl p-6">
      <h1 className="mb-6 text-xl font-semibold">{t('Obsidian note preview')}</h1>
      {target ? (
        <ObsidianLinkBoundary>
          <ObsidianPreview key={JSON.stringify(target)} target={target} />
        </ObsidianLinkBoundary>
      ) : (
        <p role="alert">{t('This note link is incomplete.')}</p>
      )}
    </main>
  )
}
export default function ObsidianPage() {
  return (
    <Suspense>
      <NotePage />
    </Suspense>
  )
}
