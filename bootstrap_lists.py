"""Create only the five dedicated lists, checkpointing each returned ID."""
import argparse
import json
from pathlib import Path
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import AuthorizedSession, Request
from bridge import API, SCOPE, private_json
from sync_core import STATUSES

parser = argparse.ArgumentParser()
parser.add_argument('--config', default='config.json')
args = parser.parse_args()
cfg = json.loads(Path(args.config).read_text())
creds = Credentials.from_authorized_user_file(cfg['google_token_file'], [SCOPE])
creds.refresh(Request())
private_json(cfg['google_token_file'], json.loads(creds.to_json()))
api = API(AuthorizedSession(creds), 'https://tasks.googleapis.com/tasks/v1')
manifest_path = Path(cfg['state_file']).with_name('google-lists.json')
manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
names, page = {}, None
while True:
    data, _ = api.call('GET', '/users/@me/lists', params={'maxResults': 100, 'pageToken': page})
    for item in data.get('items', []):
        names.setdefault(item['title'], []).append(item['id'])
    page = data.get('nextPageToken')
    if not page:
        break
for status in STATUSES:
    title = 'Project Hub — ' + status
    if status in manifest:
        if manifest[status] not in names.get(title, []):
            raise ValueError('Managed list missing or renamed; review before proceeding')
        continue
    if title in names:
        raise ValueError('Existing list name collision; review instead of reusing or duplicating')
    data, _ = api.call('POST', '/users/@me/lists', {'title': title})
    manifest[status] = data['id']
    private_json(manifest_path, manifest)
cfg['google_lists'] = manifest
private_json(args.config, cfg)
private_json(cfg['google_token_file'], json.loads(creds.to_json()))
print('Offline token refresh verified; five dedicated Google lists configured.')
