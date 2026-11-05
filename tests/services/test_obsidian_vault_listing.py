from deeptutor.services import obsidian_learning as learning


def test_listing_reads_live_vault_and_ignores_internal_files(tmp_path, monkeypatch):
    monkeypatch.setattr(learning, '_binding', lambda kb: (tmp_path, 'binding'))
    (tmp_path / '.obsidian').mkdir()
    (tmp_path / '.obsidian' / 'hidden.md').write_text('hidden', encoding='utf8')
    (tmp_path / '.agents').mkdir()
    (tmp_path / '.agents' / 'private.md').write_text('config', encoding='utf8')
    (tmp_path / '.hidden.md').write_text('hidden', encoding='utf8')
    (tmp_path / 'one.md').write_text('one', encoding='utf8')
    assert [item['path'] for item in learning.list_vault_notes('kb')['notes']] == ['one.md']
    (tmp_path / 'new.md').write_text('new', encoding='utf8')
    result = learning.list_vault_notes('kb')['notes']
    assert {item['path'] for item in result} == {'one.md', 'new.md'}
    assert all(isinstance(item['modified'], float) for item in result)
