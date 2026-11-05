import React from 'react'
import { describe, expect, it, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import ObsidianVaultFiles from '@/components/knowledge/ObsidianVaultFiles'

vi.mock('@/lib/obsidian-learning', () => ({
  obsidianWorkspaceUrl: (p: string) => p,
  obsidianRequest: (...args: unknown[]) => fetch(args[0] as string).then(r => r.json()),
}))
vi.mock('@/components/obsidian/ObsidianPreview', () => ({ ObsidianPreview: () => <div>笔记预览</div> }))

describe('Obsidian changes', () => {
  it('shows the latest changed note and before and after content', async () => {
    const change = { path: 'folder/new.md', kind: 'modified', before: 'old [[A]]', after: 'new [[B]]', added_links: ['B'], removed_links: ['A'], diff: [{ kind: 'replace', before: ['old [[A]]'], after: ['new [[B]]'] }] }
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ changes: [change], pending: false }))))
    render(<ObsidianVaultFiles kbRef="kb" />)
    fireEvent.click(await screen.findByRole('button', { name: /folder\/new.md/ }))
    expect(screen.getByText('old [[A]]')).toBeVisible()
    expect(screen.getByText('new [[B]]')).toBeVisible()
    expect(screen.getByText('新增双链：[[B]]')).toBeVisible()
    fireEvent.click(screen.getByRole('button', { name: '打开笔记与更新双链' }))
    expect(screen.getByText('笔记预览')).toBeVisible()
  })
})
