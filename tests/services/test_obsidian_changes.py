from deeptutor.services import obsidian_learning as learning
from deeptutor.services.obsidian_changes import scan_changes


def test_baseline_then_batch_records_content_and_link_changes(tmp_path, monkeypatch):
    root = tmp_path / 'vault'
    root.mkdir()
    monkeypatch.setattr(learning, '_state_dir', lambda: tmp_path / 'state')
    monkeypatch.setattr(learning, '_owner', lambda: 'alice')
    monkeypatch.setattr(learning, '_binding', lambda kb: (root, 'binding'))
    note = root / 'note.md'
    note.write_text('before [[Old]]', encoding='utf8')
    assert scan_changes('kb', now=100)['changes'] == []
    note.write_text('after [[New]]', encoding='utf8')
    (root / 'other.md').write_text('new note', encoding='utf8')
    assert scan_changes('kb', now=110)['pending']
    result = scan_changes('kb', now=114)
    by_path = {c['path']: c for c in result['changes']}
    assert by_path['note.md']['before'] == 'before [[Old]]'
    assert by_path['note.md']['after'] == 'after [[New]]'
    assert by_path['note.md']['added_links'] == ['New']
    assert by_path['note.md']['removed_links'] == ['Old']
    assert by_path['other.md']['kind'] == 'added'


def test_deleted_note_and_owner_isolation(tmp_path, monkeypatch):
    root = tmp_path / 'vault'
    root.mkdir()
    monkeypatch.setattr(learning, '_state_dir', lambda: tmp_path / 'state')
    monkeypatch.setattr(learning, '_owner', lambda: 'alice')
    monkeypatch.setattr(learning, '_binding', lambda kb: (root, 'binding'))
    note = root / 'a.md'
    note.write_text('original', encoding='utf8')
    scan_changes('kb', now=10)
    note.unlink()
    scan_changes('kb', now=20)
    assert scan_changes('kb', now=24)['changes'][0]['kind'] == 'deleted'
    monkeypatch.setattr(learning, '_owner', lambda: 'bob')
    assert scan_changes('kb', now=30)['changes'] == []
