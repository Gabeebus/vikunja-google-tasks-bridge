"""Pure merge rules. No network calls or credentials."""
import re

STATUSES = ('Backburner', 'Next', 'In progress', 'Waiting', 'Completed')
FIELDS = ('title', 'notes', 'due', 'status')
MARKER = re.compile(r'\n?\[project-hub-sync:([a-zA-Z0-9-]+)\]\s*$')


def split_marker(notes):
    notes = (notes or '').replace('\r\n', '\n').strip()
    match = MARKER.search(notes)
    return (notes[:match.start()].rstrip(), match[1]) if match else (notes, None)


def marked_notes(notes, key):
    return split_marker(notes)[0] + '\n[project-hub-sync:' + key + ']'


def merge(base, left, right):
    """Three-way, field-level merge. Conflicts never choose a silent winner."""
    result, conflicts = {}, []
    for field in FIELDS:
        b, l, r = base[field], left[field], right[field]
        if l == r or r == b:
            result[field] = l
        elif l == b:
            result[field] = r
        else:
            conflicts.append(field)
    return result, conflicts


def validate(task):
    if not task['title'] or len(task['title']) > 1024:
        raise ValueError('Title is empty or exceeds Google Tasks limit')
    if len(task['notes']) > 8000:
        raise ValueError('Notes exceed bridge limit; preserve original and review')
    if task['status'] not in STATUSES:
        raise ValueError('Unmapped status')
    if task['due'] and not re.fullmatch(r'\d{4}-\d{2}-\d{2}', task['due']):
        raise ValueError('Invalid date')
    return task
