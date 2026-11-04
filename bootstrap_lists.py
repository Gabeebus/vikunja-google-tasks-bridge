"""Create only the five dedicated lists, checkpointing each returned ID."""
import argparse
import json
import os
from pathlib import Path
import tempfile
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import AuthorizedSession, Request
from bridge import API, SCOPE, private_json
from sync_core import STATUSES


def preflight(config_file):
    config_path = Path(config_file)
    cfg = json.loads(config_path.read_text())
    if any(type(cfg.get(k)) is not int or cfg[k] <= 0
           for k in ('project_id', 'list_view_id', 'kanban_view_id')):
        raise ValueError('Replace project/view IDs with positive integers before creating lists')
    paths = [config_path, Path(cfg['google_token_file']),
             Path(cfg['state_file']).with_name('google-lists.json')]
    for path in paths:
        if path.is_symlink():
            raise ValueError('Use a regular private file, not a symlink: ' + str(path))
        if path.exists() and path.stat().st_mode & 0o077:
            raise ValueError('Private file must have mode 600 or stricter: ' + str(path))
        try:
            # Actual create/remove checks catch read-only mounts, ACLs and a parent
            # directory that cannot support atomic replacement by project-sync.
            with tempfile.TemporaryFile(prefix='.bridge-preflight-', dir=path.parent):
                pass
        except OSError as exc:
            raise ValueError('Service account cannot write directory: ' + str(path.parent) +
                             '; use the private state/config.json setup in README') from exc
    if not paths[1].is_file():
        raise ValueError('Google authorization file is missing; authorize first')
    return cfg


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', default='state/config.json')
    parser.add_argument('--preflight', action='store_true',
                        help='Check local IDs and file permissions without contacting Google')
    args = parser.parse_args(argv)
    os.umask(0o077)
    cfg = preflight(args.config)
    if args.preflight:
        print('Local configuration and write permissions passed. Google was not contacted.')
        return
    creds = Credentials.from_authorized_user_file(cfg['google_token_file'], [SCOPE])
    creds.refresh(Request())
    private_json(cfg['google_token_file'], json.loads(creds.to_json()))
    api = API(AuthorizedSession(creds), 'https://tasks.googleapis.com/tasks/v1')
    manifest_path = Path(cfg['state_file']).with_name('google-lists.json')
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    if not isinstance(manifest, dict) or set(manifest) - set(STATUSES):
        raise ValueError('Invalid managed-list manifest; review before proceeding')
    names, page = {}, None
    while True:
        data, _ = api.call('GET', '/users/@me/lists', params={'maxResults': 100, 'pageToken': page})
        for item in data.get('items', []):
            names.setdefault(item['title'], []).append(item['id'])
        page = data.get('nextPageToken')
        if not page:
            break
    # Validate every collision before creating anything, even if a collision is
    # for a later status in the list. An interrupted create remains checkpointed.
    for status in STATUSES:
        title = 'Project Hub — ' + status
        if status in manifest:
            if manifest[status] not in names.get(title, []):
                raise ValueError('Managed list missing or renamed; review before proceeding')
        elif title in names:
            raise ValueError('Existing list name collision; review instead of reusing or duplicating')
    for status in STATUSES:
        if status in manifest:
            continue
        data, _ = api.call('POST', '/users/@me/lists', {'title': 'Project Hub — ' + status})
        manifest[status] = data['id']
        private_json(manifest_path, manifest)
    cfg['google_lists'] = manifest
    private_json(args.config, cfg)
    private_json(cfg['google_token_file'], json.loads(creds.to_json()))
    print('Offline token refresh verified; five dedicated Google lists configured.')


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError) as error:
        raise SystemExit('Setup stopped: ' + str(error))
