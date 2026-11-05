import json

import pytest

from deeptutor.capabilities.obsidian.link_suggestions import suggest_links
from deeptutor.capabilities.obsidian.tools import ObsidianSuggestLinksTool


def test_suggestions_exclude_existing_and_use_disambiguated_paths(tmp_path):
    (tmp_path / '新.md').write_text('# 光照\n微表面模型与粗糙度 [[已有]]', encoding='utf-8')
    (tmp_path / '已有.md').write_text('微表面模型', encoding='utf-8')
    (tmp_path / 'a').mkdir()
    (tmp_path / 'b').mkdir()
    (tmp_path / 'a' / '模型.md').write_text('微表面模型与粗糙度', encoding='utf-8')
    (tmp_path / 'b' / '模型.md').write_text('无关内容', encoding='utf-8')
    results = suggest_links(tmp_path, '新')
    assert [r['path'] for r in results] == ['a/模型.md']
    assert results[0]['link'] == '[[a/模型.md]]'


@pytest.mark.asyncio
async def test_tool_returns_candidates_without_writing(tmp_path):
    (tmp_path / 'new.md').write_text('rendering lighting surface', encoding='utf-8')
    (tmp_path / 'old.md').write_text('rendering lighting surface', encoding='utf-8')
    result = await ObsidianSuggestLinksTool().execute(_vault_path=str(tmp_path), note='new')
    assert result.success
    assert json.loads(result.content)['candidates'][0]['path'] == 'old.md'
    assert (tmp_path / 'new.md').read_text(encoding='utf-8') == 'rendering lighting surface'
