import React from 'react'
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { initI18n } from '@/i18n/init'
import { parseObsidianLink, prepareObsidianMarkdown, materialPrompt } from '@/lib/obsidian-learning'
import { ObsidianPreview } from '@/components/obsidian/ObsidianPreview'
import { MaterialToNotes } from '@/components/obsidian/MaterialToNotes'
initI18n('en')
vi.mock('@/shared/api/client', () => ({
  apiUrl: (p: string) => p,
  apiFetch: (...args: unknown[]) => fetch(...(args as Parameters<typeof fetch>)),
}))
vi.mock('@/components/common/MarkdownContent', () => ({
  default: ({ content }: { content: string }) => <div>{content}</div>,
}))
const draft = {
  id: 'd',
  kb: 'ta',
  path: '学习.md',
  content: 'original',
  properties: { type: 'learning' },
  mode: 'create',
  status: 'pending',
  preview_href: '/obsidian?draft=d',
}
describe('Obsidian learning', () => {
  it('accepts only same-origin complete preview links', () => {
    expect(parseObsidianLink('/obsidian?source=abc&heading=坐标', 'http://localhost')).toEqual({
      source: 'abc',
      heading: '坐标',
    })
    expect(parseObsidianLink('https://evil.test/obsidian?draft=d', 'http://localhost')).toBeNull()
    expect(parseObsidianLink('/obsidian?note=x', 'http://localhost')).toBeNull()
  })
  it('rewrites wiki navigation and local images through scoped routes without touching code', () => {
    const md = prepareObsidianMarkdown(
      '[[TA/坐标#空间|空间]] ![[images/a.png]] ![a](../img.png) `[[literal]]`',
      'ta',
      'notes/学习.md'
    )
    expect(md).toContain('/obsidian?kb=ta&note=TA%2F%E5%9D%90%E6%A0%87&heading=%E7%A9%BA%E9%97%B4')
    expect(md).toContain('/api/obsidian/asset?kb=ta&path=images%2Fa.png')
    expect(md).toContain('path=img.png')
    expect(md).toContain('`[[literal]]`')
  })
  it('loads a source', async () => {
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValue(
          new Response(
            JSON.stringify({
              kb: 'ta',
              path: 'a.md',
              body: '## Space\ntext',
              frontmatter: {},
              heading: 'Space',
              obsidian_uri: 'obsidian://open?vault=TA&file=a',
              links: [],
            })
          )
        )
    )
    render(<ObsidianPreview target={{ source: 's' }} />)
    expect(await screen.findByText('a.md')).toBeVisible()
    expect(screen.getByRole('link', { name: 'Open in Obsidian' })).toHaveAttribute(
      'href',
      expect.stringContaining('obsidian://')
    )
  })
  it('offers link candidates and prepares a draft for selected notes', async () => {
    const fetcher = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ kb: 'ta', path: 'a.md', body: 'body', frontmatter: {}, heading: '', obsidian_uri: '', links: [] })))
      .mockResolvedValueOnce(new Response(JSON.stringify({ candidates: [{ path: 'b.md', link: '[[b.md]]', shared_terms: ['rendering'], score: 2 }] })))
      .mockResolvedValueOnce(new Response(JSON.stringify({ ...draft, mode: 'append', content: '\n## 相关笔记\n- [[b.md]]' })))
    vi.stubGlobal('fetch', fetcher)
    render(<ObsidianPreview target={{ kb: 'ta', note: 'a.md' }} />)
    fireEvent.click(await screen.findByRole('button', { name: '更新双链' }))
    fireEvent.click(await screen.findByRole('checkbox', { name: /b\.md/ }))
    fireEvent.click(screen.getByRole('button', { name: '生成双链草稿' }))
    expect(await screen.findByLabelText('Note content')).toHaveValue('\n## 相关笔记\n- [[b.md]]')
    expect(JSON.parse(fetcher.mock.calls[2][1].body).paths).toEqual(['b.md'])
  })
  it('retains edited draft after failed save and disables duplicate save after success', async () => {
    const fetcher = vi
      .fn()
      .mockResolvedValueOnce(new Response(JSON.stringify(draft)))
      .mockResolvedValueOnce(new Response(JSON.stringify({ detail: 'Conflict' }), { status: 409 }))
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({ ...draft, status: 'saved', note_href: '/obsidian?kb=ta&note=x' })
        )
      )
    vi.stubGlobal('fetch', fetcher)
    render(<ObsidianPreview target={{ draft: 'd' }} />)
    const content = await screen.findByLabelText('Note content')
    fireEvent.change(content, { target: { value: 'edited' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save to vault' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Conflict')
    expect(content).toHaveValue('edited')
    fireEvent.click(screen.getByRole('button', { name: 'Save to vault' }))
    await waitFor(() => expect(screen.getByRole('button', { name: 'Saved' })).toBeDisabled())
    expect(JSON.parse(fetcher.mock.calls[1][1].body).content).toBe('edited')
  })
  it('extracts a URL and prefills editable source without sending', async () => {
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValue(
          new Response(
            JSON.stringify({
              text: 'source text',
              source: 'https://example.test',
              title: 'Lesson',
              truncated: false,
            })
          )
        )
    )
    const prefill = vi.fn()
    render(<MaterialToNotes kb="ta" onPrefill={prefill} />)
    fireEvent.click(screen.getByRole('button', { name: 'Materials to notes' }))
    fireEvent.change(screen.getByLabelText('Material URL'), {
      target: { value: 'https://example.test' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Extract URL' }))
    const source = await screen.findByLabelText('Source text')
    fireEvent.change(source, { target: { value: 'reviewed' } })
    fireEvent.click(screen.getByRole('button', { name: 'Prepare learning note' }))
    expect(prefill).toHaveBeenCalledWith(expect.stringContaining('reviewed'))
    expect(prefill).toHaveBeenCalledTimes(1)
  })
  it('builds instructions to read related notes and stage a reviewed draft', () => {
    expect(materialPrompt('ta', 'text', 'url')).toContain('draft')
  })
  it('uploads a file as multipart and preserves source edits on extraction failure', async () => {
    const fetcher = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            text: 'uploaded',
            source: 'lesson.md',
            title: 'Lesson',
            truncated: true,
          })
        )
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ detail: 'Cannot extract PDF' }), { status: 422 })
      )
    vi.stubGlobal('fetch', fetcher)
    render(<MaterialToNotes kb="ta" onPrefill={vi.fn()} />)
    fireEvent.click(screen.getByRole('button', { name: 'Materials to notes' }))
    fireEvent.change(screen.getByLabelText('Material file'), {
      target: { files: [new File(['hello'], 'lesson.md', { type: 'text/markdown' })] },
    })
    const source = await screen.findByLabelText('Source text')
    expect(fetcher.mock.calls[0][1].body).toBeInstanceOf(FormData)
    fireEvent.change(source, { target: { value: 'keep edit' } })
    fireEvent.change(screen.getByLabelText('Material file'), {
      target: { files: [new File(['empty'], 'scan.pdf', { type: 'application/pdf' })] },
    })
    expect(await screen.findByRole('alert')).toHaveTextContent('Cannot extract PDF')
    expect(source).toHaveValue('keep edit')
  })
  it('retries a failed source preview', async () => {
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValueOnce(
          new Response(JSON.stringify({ detail: 'Unavailable' }), { status: 503 })
        )
        .mockResolvedValueOnce(
          new Response(
            JSON.stringify({
              kb: 'ta',
              path: 'recovered.md',
              body: 'text',
              frontmatter: {},
              heading: null,
              obsidian_uri: '',
              links: [],
            })
          )
        )
    )
    render(<ObsidianPreview target={{ source: 'retry' }} />)
    expect(await screen.findByRole('alert')).toHaveTextContent('Unavailable')
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }))
    expect(await screen.findByText('recovered.md')).toBeVisible()
  })
  it('restricts property drafts to property edits and pins saves to the source workspace', async () => {
    const fetcher = vi
      .fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ ...draft, mode: 'property' })))
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ ...draft, mode: 'property', status: 'saved' }))
      )
    vi.stubGlobal('fetch', fetcher)
    render(<ObsidianPreview target={{ draft: 'd', workspace: '' }} />)
    expect(await screen.findByLabelText('Destination path')).toHaveAttribute('readonly')
    expect(screen.getByLabelText('Note content')).toHaveAttribute('readonly')
    expect(screen.getByLabelText('Properties (JSON)')).not.toHaveAttribute('readonly')
    fireEvent.click(screen.getByRole('button', { name: 'Save to vault' }))
    await screen.findByRole('button', { name: 'Saved' })
    expect(fetcher.mock.calls[0][0]).toBe('/api/obsidian/drafts/d?dt_workspace=')
    expect(fetcher.mock.calls[1][0]).toBe('/api/obsidian/drafts/d/save?dt_workspace=')
  })
})
