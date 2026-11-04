"""Private Project Hub sync worker. Run with --check before enabling a timer."""
import argparse
import fcntl
import html
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import uuid
from datetime import datetime
from zoneinfo import ZoneInfo
from urllib.parse import quote

import requests
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import AuthorizedSession
from sync_core import STATUSES, split_marker, marked_notes, merge, validate

SCOPE = 'https://www.googleapis.com/auth/tasks'


def private_json(path, data):
    path = Path(path)
    fd, temporary = tempfile.mkstemp(prefix='.' + path.name + '.', dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as out:
            json.dump(data, out, indent=2)
            out.flush()
            os.fsync(out.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


class Text(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)

    def handle_starttag(self, tag, attrs):
        if tag == 'br':
            self.parts.append('\n')

    def handle_endtag(self, tag):
        if tag in ('p', 'div', 'li', 'h1', 'h2', 'h3'):
            self.parts.append('\n')


def plain(value):
    parser = Text()
    parser.feed(value or '')
    return ''.join(parser.parts).strip()


class API:
    def __init__(self, session, base):
        self.session, self.base = session, base.rstrip('/')

    def call(self, method, path, body=None, params=None):
        response = self.session.request(method, self.base + path, json=body,
                                        params=params, timeout=(10, 40))
        # Never log response bodies: they may contain private task data.
        if not response.ok:
            raise RuntimeError('API request failed with HTTP ' + str(response.status_code))
        return response.json(), response.headers


class Vikunja(API):
    def __init__(self, cfg):
        session = requests.Session()
        session.headers['Authorization'] = 'Bearer ' + Path(cfg['vikunja_token_file']).read_text().strip()
        super().__init__(session, cfg['vikunja_url'].rstrip('/') + '/api/v1')
        self.project, self.view = cfg['project_id'], cfg['kanban_view_id']
        self.list_view = cfg['list_view_id']
        self.zone = ZoneInfo(cfg.get('timezone', 'America/New_York'))
        buckets, _ = self.call('GET', f'/projects/{self.project}/views/{self.view}/buckets')
        self.buckets = {b['title']: b['id'] for b in buckets}
        if set(self.buckets) != set(STATUSES):
            raise ValueError('Kanban columns do not match configured statuses')

    def snapshot(self):
        tasks, page, expected = {}, 1, None
        while True:
            batch, headers = self.call('GET', f'/projects/{self.project}/views/{self.view}/tasks',
                                        params={'page': page, 'per_page': 50, 'expand': 'buckets'})
            counts = {b['id']: b['count'] for b in batch}
            if expected is None:
                expected = counts
            elif counts != expected:
                raise ValueError('Board changed during pagination; retry next run')
            previous = len(tasks)
            for bucket in batch:
                for task in bucket.get('tasks') or []:
                    tasks[str(task['id'])] = (task, bucket['title'])
            if len(tasks) == sum(expected.values()):
                break
            if len(tasks) == previous:
                raise ValueError('Incomplete Kanban pagination; refusing partial snapshot')
            page += 1
        result = {}
        for task, status in tasks.values():
            if status not in STATUSES or task.get('project_id') != self.project:
                raise ValueError('Task has no unambiguous configured bucket')
            if task.get('done'):
                status = 'Completed'
            elif status == 'Completed':
                status = 'Next'
            due = task.get('due_date', '')
            day = None if not due or due.startswith('0001-') else datetime.fromisoformat(due.replace('Z', '+00:00')).astimezone(self.zone).date().isoformat()
            notes, key = split_marker(plain(task.get('description')))
            result[str(task['id'])] = dict(raw=task, key=key, value=dict(
                title=task['title'], notes=notes, due=day, status=status))
        return result

    def write(self, ident, value, key, current=None):
        validate(value)
        body = dict(current['raw']) if current else {}
        old = current['value'] if current else {}
        body.update(title=value['title'], done=value['status'] == 'Completed')
        # First registration adds only the marker; preserve existing rich HTML.
        if current and not current.get('key') and old.get('notes') == value['notes']:
            body['description'] = (body.get('description') or '') + '<p>' + html.escape('[project-hub-sync:' + key + ']') + '</p>'
        elif old.get('notes') != value['notes'] or not current or current.get('key') != key:
            body['description'] = '<p>' + html.escape(marked_notes(value['notes'], key)).replace('\n', '<br>') + '</p>'
        if old.get('due') != value['due'] or not current:
            body['due_date'] = (value['due'] + 'T12:00:00' + self.zone_offset(value['due'])) if value['due'] else '0001-01-01T00:00:00Z'
        if ident:
            task, _ = self.call('POST', '/tasks/' + ident, body)
        else:
            task, _ = self.call('PUT', f'/projects/{self.project}/tasks', body)
        ident = str(task['id'])
        self.call('POST', f'/projects/{self.project}/views/{self.view}/buckets/{self.buckets[value["status"]]}/tasks', {'task_id': int(ident)})
        return ident

    def zone_offset(self, day):
        offset = datetime.fromisoformat(day + 'T12:00:00').replace(tzinfo=self.zone).strftime('%z')
        return offset[:3] + ':' + offset[3:]


class Google(API):
    def __init__(self, cfg):
        self.token_file = cfg['google_token_file']
        self.creds = Credentials.from_authorized_user_file(self.token_file, [SCOPE])
        super().__init__(AuthorizedSession(self.creds), 'https://tasks.googleapis.com/tasks/v1')
        self.lists = cfg['google_lists']
        if set(self.lists) != set(STATUSES) or len(set(self.lists.values())) != 5:
            raise ValueError('Exactly five distinct managed Google task lists are required')

    def snapshot(self):
        result = {}
        for status, list_id in self.lists.items():
            page = None
            while True:
                batch, _ = self.call('GET', f'/lists/{quote(list_id, safe="")}/tasks', params={
                    'maxResults': 100, 'showCompleted': 'true', 'showHidden': 'true',
                    'showDeleted': 'true', 'pageToken': page})
                for task in batch.get('items', []):
                    notes, key = split_marker(task.get('notes'))
                    mapped = 'Completed' if task.get('status') == 'completed' else ('Next' if status == 'Completed' else status)
                    result[task['id']] = dict(raw=task, key=key, list_id=list_id,
                        deleted=task.get('deleted', False), value=dict(title=task.get('title', ''),
                        notes=notes, due=(task.get('due') or '')[:10] or None, status=mapped))
                page = batch.get('nextPageToken')
                if not page:
                    break
        return result

    def write(self, ident, value, key, current=None):
        validate(value)
        target = self.lists[value['status']]
        body = dict(title=value['title'], notes=marked_notes(value['notes'], key),
                    due=value['due'] + 'T00:00:00Z' if value['due'] else None,
                    status='completed' if value['status'] == 'Completed' else 'needsAction')
        if ident:
            source = current['list_id']
            if source != target:
                task, _ = self.call('POST', f'/lists/{quote(source, safe="")}/tasks/{quote(ident, safe="")}/move',
                                    params={'destinationTasklist': target})
                ident = task['id']
            self.call('PATCH', f'/lists/{quote(target, safe="")}/tasks/{quote(ident, safe="")}', body)
        else:
            task, _ = self.call('POST', f'/lists/{quote(target, safe="")}/tasks', body)
            ident = task['id']
        return ident

    def close(self):
        if self.creds.refresh_token:
            private_json(self.token_file, json.loads(self.creds.to_json()))


class State:
    def __init__(self, path):
        self.db = sqlite3.connect(path)
        os.chmod(path, 0o600)
        self.db.execute('CREATE TABLE IF NOT EXISTS links (key TEXT PRIMARY KEY, vid TEXT, gid TEXT, baseline TEXT, issue TEXT)')
        self.db.commit()

    def rows(self):
        return list(self.db.execute('SELECT key,vid,gid,baseline,issue FROM links'))

    def save(self, key, vid, gid, base, issue=None):
        self.db.execute('INSERT OR REPLACE INTO links VALUES (?,?,?,?,?)',
                        (key, vid, gid, json.dumps(base) if base is not None else None, issue))
        self.db.commit()


def index_keys(snapshot):
    result = {}
    for ident, task in snapshot.items():
        key = task.get('key')
        if key and not task.get('deleted'):
            if key in result:
                raise ValueError('Duplicate sync marker: stop for review')
            result[key] = ident
    return result


def synchronize(v, g, state, check=False):
    # Finish both paginated reads before making any writes.
    vs, gs = v.snapshot(), g.snapshot()
    vk, gk = index_keys(vs), index_keys(gs)
    known = state.rows()
    state.detected_issues = set()
    seen_v, seen_g = set(), set()
    for key, vid, gid, baseline, issue in known:
        vid, gid = vk.get(key, vid), gk.get(key, gid)
        seen_v.add(vid)
        seen_g.add(gid)
        left, right = vs.get(vid), gs.get(gid)
        if (vid and not left) or (gid and (not right or right.get('deleted'))):
            state.detected_issues.add(key)
            if not check:
                state.save(key, vid, gid, json.loads(baseline) if baseline else None, 'Missing or deleted task: manual review required')
            continue
        if not left and not right:
            raise ValueError('Unrecoverable incomplete mapping')
        base = json.loads(baseline) if baseline else None
        if left and right:
            if base is None and left['value'] != right['value']:
                state.detected_issues.add(key)
                if not check:
                    state.save(key, vid, gid, None, 'Initial pairing differs: review required')
                continue
            target, conflicts = merge(base or left['value'], left['value'], right['value'])
            if conflicts:
                state.detected_issues.add(key)
                if not check:
                    state.save(key, vid, gid, base, 'Conflicting fields: ' + ', '.join(conflicts))
                continue
        else:
            target = (left or right)['value']
        validate(target)
        if check:
            continue
        # Keep baseline until both writes succeed. A partial update safely merges
        # with the previous baseline on retry; markers recover interrupted creates.
        if not left or left['value'] != target or left.get('key') != key:
            vid = v.write(vid, target, key, left)
            state.save(key, vid, gid, base)
        if not right or right['value'] != target or right.get('key') != key:
            gid = g.write(gid, target, key, right)
            state.save(key, vid, gid, base)
        state.save(key, vid, gid, target)
    for side, snapshot, seen in [('v', vs, seen_v), ('g', gs, seen_g)]:
        for ident, task in snapshot.items():
            if ident in seen or task.get('deleted'):
                continue
            # Unknown markers may be a missing state database; don't re-import.
            if task.get('key'):
                raise ValueError('Unregistered marker: restore bridge state before continuing')
            validate(task['value'])
            if not check:
                state.save(str(uuid.uuid4()), ident if side == 'v' else None,
                           ident if side == 'g' else None, None)
    return len(vs), len(gs)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', default='config.json')
    parser.add_argument('--check', action='store_true', help='Read and validate without task writes')
    args = parser.parse_args()
    os.umask(0o077)
    cfg = json.loads(Path(args.config).read_text())
    if any(type(cfg.get(k)) is not int or cfg[k] <= 0 for k in ('project_id','list_view_id','kanban_view_id')):
        raise ValueError('Replace project/view IDs with positive integers before running the worker')
    lock = open(cfg['state_file'] + '.lock', 'w')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    state = State(cfg['state_file'])
    google = Google(cfg)
    try:
        counts = synchronize(Vikunja(cfg), google, state, args.check)
        issues = len({row[0] for row in state.rows() if row[4]} | state.detected_issues)
        print(f'Checked {counts[0]} Vikunja and {counts[1]} Google tasks; review items: {issues}')
        if issues:
            raise SystemExit(2)
    finally:
        google.close()


if __name__ == '__main__':
    main()
