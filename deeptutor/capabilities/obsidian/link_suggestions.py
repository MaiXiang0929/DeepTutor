"""Conservative lexical candidates for an Obsidian note's links."""

from pathlib import Path
import re

from deeptutor.capabilities.obsidian import vault as V


def _terms(text: str) -> set[str]:
    text = text.casefold()
    words = set(re.findall(r'[a-z0-9_]{3,}', text))
    for run in re.findall(r'[\u4e00-\u9fff]{2,}', text):
        words.update(run[i:i + 2] for i in range(len(run) - 1))
    return words


def suggest_links(root: Path, note: str, limit: int = 10) -> list[dict]:
    source = V.read_note(root, note)
    source_path = source['path']
    excluded = {source_path}
    for ref in V.outgoing_links(root, note):
        try:
            target = V.resolve_note(root, ref)
            if target:
                excluded.add(target.relative_to(root.resolve()).as_posix())
        except V.VaultError:
            continue
    terms = _terms(Path(source_path).stem + ' ' + source['body'])
    results = []
    for path in V.list_notes(root, limit=None):
        if path in excluded:
            continue
        candidate = V.read_note(root, path)
        common = terms & _terms(Path(path).stem + ' ' + candidate['body'])
        if len(common) < 2:
            continue
        results.append({'path': path, 'link': f'[[{path}]]',
                        'shared_terms': sorted(common)[:12], 'score': len(common)})
    results.sort(key=lambda item: (-item['score'], item['path']))
    return results[:max(0, min(limit, 30))]
