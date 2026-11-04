"""Run on the Mac. The owner completes Google's consent in the browser."""
import argparse
import os
import tempfile
from pathlib import Path
from google_auth_oauthlib.flow import InstalledAppFlow, WSGITimeoutError

SCOPE = 'https://www.googleapis.com/auth/tasks'

parser = argparse.ArgumentParser()
parser.add_argument('client_file')
parser.add_argument('token_file')
args = parser.parse_args()
os.umask(0o077)
path = Path(args.token_file)
if path.exists() or path.is_symlink():
    raise SystemExit('Output already exists; choose a new private token file before authorizing.')
try:
    with tempfile.TemporaryFile(prefix='.oauth-write-check-', dir=path.parent):
        pass
except OSError:
    raise SystemExit('Output directory must exist and be writable before authorizing.')
flow = InstalledAppFlow.from_client_secrets_file(args.client_file, [SCOPE], autogenerate_code_verifier=True)
try:
    creds = flow.run_local_server(host='127.0.0.1', port=0, open_browser=True,
        access_type='offline', prompt='consent', timeout_seconds=900,
        authorization_prompt_message='Complete Google Tasks consent in your browser.',
        success_message='Project Hub authorization received. You can close this tab.')
except WSGITimeoutError:
    raise SystemExit('Google authorization timed out. No token was saved. Finish signing in, then rerun this command to open a fresh consent request.') from None

if not creds.refresh_token:
    raise SystemExit('No offline token returned; recurring sync is not configured.')
with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'w') as out:
    out.write(creds.to_json())
print('Google Tasks token saved privately. Sync is not enabled yet.')
