'use client'
import MarkdownContent from './MarkdownContent'
import type { MarkdownRendererProps } from './markdown-renderer-types'
import { ObsidianLinkBoundary } from '@/components/obsidian/ObsidianLinkBoundary'
export type { MarkdownRendererProps } from './markdown-renderer-types'
export default function MarkdownRenderer(props: MarkdownRendererProps) {
  return (
    <ObsidianLinkBoundary>
      <MarkdownContent {...props} />
    </ObsidianLinkBoundary>
  )
}
