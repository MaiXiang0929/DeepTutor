import React from 'react'
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { initI18n } from '@/i18n/init'
import MarkdownRenderer from '@/components/common/MarkdownRenderer'
initI18n('en')
// Preserve the actual rich renderer, loading synchronously in the test runner.
vi.mock('next/dynamic', async () => {
  const react = await import('react')
  return {
    default: (loader: () => Promise<{ default: React.ComponentType<Record<string, unknown>> }>) => {
      const Lazy = react.lazy(loader)
      return function Dynamic(props: Record<string, unknown>) {
        return (
          <react.Suspense>
            <Lazy {...props} />
          </react.Suspense>
        )
      }
    },
  }
})
vi.mock('@/shared/api/client', () => ({
  apiUrl: (p: string) => p,
  apiFetch: (...args: unknown[]) => fetch(...(args as Parameters<typeof fetch>)),
}))
describe('Obsidian links in rendered chat', () => {
  for (const rich of [false, true])
    it(`opens ${rich ? 'rich' : 'simple'} citations in an accessible drawer`, async () => {
      const fetcher = vi
        .fn()
        .mockResolvedValue(
          new Response(
            JSON.stringify({
              kb: 'ta',
              path: 'a.md',
              body: '## Space\nEvidence',
              frontmatter: {},
              heading: 'Space',
              obsidian_uri: 'obsidian://open?vault=TA&file=a',
              links: [],
            })
          )
        )
      vi.stubGlobal('fetch', fetcher)
      render(
        <MarkdownRenderer
          content="[Evidence](/obsidian?source=s&heading=Space)"
          enableCode={rich}
        />
      )
      const link = await screen.findByRole('link', { name: 'Evidence' })
      link.focus()
      fireEvent.click(link)
      expect(await screen.findByRole('dialog')).toBeVisible()
      const heading = await screen.findByRole('heading', { name: 'Space' })
      await waitFor(() => expect(heading).toHaveAttribute('data-obsidian-heading', 'true'))
      fireEvent.keyDown(document, { key: 'Escape' })
      expect(screen.queryByRole('dialog')).toBeNull()
      expect(link).toHaveFocus()
    })
  it('leaves modified clicks and foreign links to the browser', () => {
    render(
      <MarkdownRenderer content="[Draft](/obsidian?draft=d) [Foreign](https://example.test/obsidian?draft=d)" />
    )
    fireEvent.click(screen.getByRole('link', { name: 'Draft' }), { ctrlKey: true })
    expect(screen.queryByRole('dialog')).toBeNull()
    fireEvent.click(screen.getByRole('link', { name: 'Foreign' }))
    expect(screen.queryByRole('dialog')).toBeNull()
  })
})
