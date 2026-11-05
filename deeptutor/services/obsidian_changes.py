"""Account-scoped snapshots of the latest observed Vault changes."""

import difflib
import hashlib
import json
import re
import time

from deeptutor.capabilities.obsidian import vault as V
from deeptutor.services import obsidian_learning as learning

_LINK = re.compile(r'(?<!!)\[\[([^\]\n]+)\]\]')


def _links(text):
    return set(_LINK.findall(text or ''))


def _diff(before, after):
    left = (before or '').splitlines()
    right = (after or '').splitlines()
    return [{'kind': tag, 'before': left[i:j], 'after': right[k:end]}
            for tag, i, j, k, end in difflib.SequenceMatcher(None, left, right, autojunk=False).get_opcodes()]


def scan_changes(kb, now=None):
    root, binding = learning._binding(kb)
    now = time.time() if now is None else now
    key = hashlib.sha256(f'{learning._owner()}\0{binding}'.encode('utf8')).hexdigest()
    current = {}
    for path in V._iter_markdown(root):
        current[path.relative_to(root.resolve()).as_posix()] = path.read_text(encoding='utf8')
    with learning._db() as db:
        db.execute('BEGIN IMMEDIATE')
        record = db.execute('SELECT payload FROM records WHERE id=? AND owner=? AND kind=?', (key, learning._owner(), 'vault_changes')).fetchone()
        if record is None:
            state = {'snapshot': current, 'pending': None, 'latest': [], 'last_scan': now}
        else:
            state = json.loads(record[0])
            if current != state['snapshot']:
                if state['pending'] is None:
                    state['pending'] = {'before': state['snapshot'], 'updated': now, 'offline': now - state.get('last_scan', now) > 15}
                else:
                    state['pending']['updated'] = now
                state['snapshot'] = current
            pending = state['pending']
            if pending is not None and now - pending['updated'] >= 3:
                before = pending['before']
                changes = []
                for path in sorted(before.keys() | current.keys()):
                    old, new = before.get(path), current.get(path)
                    if old == new:
                        continue
                    changes.append({'path': path, 'kind': 'added' if old is None else 'deleted' if new is None else 'modified', 'before': old, 'after': new, 'diff': _diff(old, new), 'added_links': sorted(_links(new) - _links(old)), 'removed_links': sorted(_links(old) - _links(new))})
                if changes:
                    state['latest'] = changes
                    state['updated'] = now
                    state['offline'] = pending.get('offline', False)
                state['pending'] = None
        state['last_scan'] = now
        payload = json.dumps(state, ensure_ascii=False)
        db.execute('INSERT OR REPLACE INTO records VALUES (?, ?, ?, ?)', (key, learning._owner(), 'vault_changes', payload))
        return {'changes': state['latest'], 'updated': state.get('updated'), 'offline': state.get('offline', False), 'pending': state['pending'] is not None}
