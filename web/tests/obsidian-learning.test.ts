import test from 'node:test'
import assert from 'node:assert/strict'
import {
  parseObsidianLink,
  prepareObsidianMarkdown,
  previewEndpoint,
} from '../lib/obsidian-learning'

test('Obsidian targets reject foreign and incomplete links and encode opaque identifiers', () => {
  assert.equal(parseObsidianLink('//evil.test/obsidian?source=x', 'http://localhost'), null)
  assert.equal(parseObsidianLink('javascript:alert(1)', 'http://localhost'), null)
  assert.equal(parseObsidianLink('/obsidian?kb=x', 'http://localhost'), null)
  assert.equal(previewEndpoint({ source: 'a/b' }), '/api/obsidian/sources/a%2Fb')
  assert.deepEqual(
    parseObsidianLink(
      '/obsidian?kb=ta&note=%E5%AD%A6%E4%B9%A0.md&heading=%E7%A9%BA%E9%97%B4',
      'http://localhost'
    ),
    { kb: 'ta', note: '学习.md', heading: '空间' }
  )
})
test('asset URLs are scoped and traversal and absolute filesystem images never reach the browser', () => {
  for (const path of [
    '../../secret.png',
    'file:///C:/secret.png',
    'C:/secret.png',
    '%2Fetc/secret.png',
    'https://evil.test/tracker.png',
  ]) {
    const text = prepareObsidianMarkdown(`![image](${path})`, 'ta', 'note.md')
    assert.equal(text, '![image]()')
  }
  assert.match(
    prepareObsidianMarkdown('![[图片.png]]', 'ta', 'note.md'),
    /asset\?kb=ta&path=%E5%9B%BE%E7%89%87.png/
  )
})

test('source/draft/note requests and note assets preserve explicit workspaces including General', () => {
  for (const workspace of ['project-a', '']) {
    const target = parseObsidianLink(
      `/obsidian?source=s&dt_workspace=${workspace}`,
      'http://localhost'
    )!
    assert.equal(target.workspace, workspace)
    assert.equal(previewEndpoint(target), `/api/obsidian/sources/s?dt_workspace=${workspace}`)
    assert.match(
      previewEndpoint({ draft: 'd', workspace }),
      new RegExp(`dt_workspace=${workspace}$`)
    )
    const text = prepareObsidianMarkdown('[[Note]] ![[image.png]]', 'ta', 'note.md', workspace)
    assert.match(text, new RegExp(`dt_workspace=${workspace}\\)`))
  }
})

test('ordinary Markdown notes and images resolve inside the source vault', () => {
  const text = prepareObsidianMarkdown(
    '[Other](./Other.md#Heading) [Unicode](<../学习.md#坐标 空间>) ![pic](<./diagram 1.png>) ![encoded](./diagram%202.png "caption") ![spaced](./diagram 3.png)',
    'ta',
    'folder/note.md',
    ''
  )
  assert.match(text, /note=folder%2FOther.md&heading=Heading&dt_workspace=/)
  assert.match(text, /note=%E5%AD%A6%E4%B9%A0.md&heading=%E5%9D%90%E6%A0%87%20%E7%A9%BA%E9%97%B4/)
  for (const n of [1, 2, 3]) assert.match(text, new RegExp(`path=folder%2Fdiagram%20${n}.png`))
  assert.match(text, /"caption"/)
  assert.equal(
    prepareObsidianMarkdown(
      '[remote](https://example.test/x.md) `![literal](<file a.png>)`',
      'ta',
      'note.md'
    ),
    '[remote](https://example.test/x.md) `![literal](<file a.png>)`'
  )
  assert.equal(prepareObsidianMarkdown('[escape](../outside.md)', 'ta', 'note.md'), '[escape]()')
})

test('source requests forward the cited heading for server validation', () => {
  assert.equal(
    previewEndpoint({ source: 's', heading: '坐标 空间', workspace: '' }),
    '/api/obsidian/sources/s?heading=%E5%9D%90%E6%A0%87%20%E7%A9%BA%E9%97%B4&dt_workspace='
  )
})
