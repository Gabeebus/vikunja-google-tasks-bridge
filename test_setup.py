import json
import os
from pathlib import Path
import runpy
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
import bootstrap_lists
from bridge import private_json
from sync_core import STATUSES


class SetupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / 'state').mkdir(mode=0o700)
        (self.root / 'secrets').mkdir(mode=0o700)
        self.config = self.root / 'state/config.json'
        self.token = self.root / 'secrets/google-token.json'
        private_json(self.token, {'test_fixture': True})
        self.cfg = dict(project_id=1, list_view_id=2, kanban_view_id=3,
                        google_token_file=str(self.token), state_file=str(self.root / 'state/state.sqlite'))
        private_json(self.config, self.cfg)
        self.creds = Mock()
        self.creds.to_json.return_value = '{"test_fixture":true}'

    def tearDown(self):
        self.tmp.cleanup()

    def invoke(self, api, extra=()):
        with patch.object(bootstrap_lists.Credentials, 'from_authorized_user_file', return_value=self.creds), \
             patch.object(bootstrap_lists, 'AuthorizedSession'), patch.object(bootstrap_lists, 'API', return_value=api):
            bootstrap_lists.main(['--config', str(self.config), *extra])

    def test_bad_ids_stop_before_authentication_or_list_creation(self):
        self.cfg['project_id'] = 0
        private_json(self.config, self.cfg)
        with patch.object(bootstrap_lists.Credentials, 'from_authorized_user_file') as auth:
            with self.assertRaisesRegex(ValueError, 'positive integers'):
                bootstrap_lists.main(['--config', str(self.config)])
            auth.assert_not_called()

    @unittest.skipIf(os.geteuid() == 0, 'Run this permission regression as an unprivileged user')
    def test_root_owned_source_style_directory_fails_before_google_writes(self):
        source = self.root / 'source'
        source.mkdir()
        config = source / 'config.json'
        private_json(config, self.cfg)
        source.chmod(0o500)
        try:
            with patch.object(bootstrap_lists.Credentials, 'from_authorized_user_file') as auth:
                with self.assertRaisesRegex(ValueError, 'cannot write directory'):
                    bootstrap_lists.main(['--config', str(config)])
                auth.assert_not_called()
        finally:
            source.chmod(0o700)

    def test_preflight_is_local_and_rejects_public_token_permissions(self):
        api = Mock()
        self.invoke(api, ['--preflight'])
        api.call.assert_not_called()
        self.creds.refresh.assert_not_called()
        self.token.chmod(0o644)
        with self.assertRaisesRegex(ValueError, 'mode 600'):
            bootstrap_lists.preflight(self.config)

    def test_collision_for_last_status_creates_no_earlier_lists(self):
        api = Mock()
        api.call.return_value = ({'items': [{'title': 'Project Hub — Completed', 'id': 'existing'}]}, {})
        with self.assertRaisesRegex(ValueError, 'collision'):
            self.invoke(api)
        self.assertEqual([c.args[0] for c in api.call.call_args_list], ['GET'])

    def test_interrupted_list_creation_resumes_from_private_checkpoint(self):
        remote = []
        fail = [True]
        def call(method, path, body=None, **kwargs):
            if method == 'GET':
                return {'items': list(remote)}, {}
            if len(remote) == 2 and fail[0]:
                fail[0] = False
                raise ConnectionError('Interrupted before third create')
            item = {'id': str(len(remote) + 1), 'title': body['title']}
            remote.append(item)
            return item, {}
        api = Mock(); api.call.side_effect = call
        with self.assertRaises(ConnectionError):
            self.invoke(api)
        manifest = self.root / 'state/google-lists.json'
        self.assertEqual(len(json.loads(manifest.read_text())), 2)
        self.invoke(api)
        self.invoke(api)
        self.assertEqual(len(remote), 5)
        self.assertEqual(set(json.loads(self.config.read_text())['google_lists']), set(STATUSES))
        self.assertEqual(self.config.stat().st_mode & 0o777, 0o600)
        self.assertEqual(manifest.stat().st_mode & 0o777, 0o600)

    def test_failed_atomic_save_preserves_previous_config_and_cleans_temporary(self):
        original = self.config.read_text()
        with patch('bridge.os.replace', side_effect=OSError('Simulated disk error')):
            with self.assertRaises(OSError):
                private_json(self.config, {'replacement': True})
        self.assertEqual(self.config.read_text(), original)
        self.assertEqual([p.name for p in self.config.parent.iterdir()], ['config.json'])

    def test_existing_oauth_output_stops_before_opening_consent(self):
        script = Path(__file__).with_name('authorize.py')
        with patch.object(sys, 'argv', [str(script), str(self.root / 'client.json'), str(self.token)]), \
             patch('google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file') as flow:
            with self.assertRaisesRegex(SystemExit, 'Output already exists'):
                runpy.run_path(str(script), run_name='__main__')
            flow.assert_not_called()

    def test_oauth_timeout_is_readable_and_does_not_create_token(self):
        from google_auth_oauthlib.flow import WSGITimeoutError
        script = Path(__file__).with_name('authorize.py')
        output = self.root / 'fresh-google-token.json'
        with patch.object(sys, 'argv', [str(script), str(self.root / 'client.json'), str(output)]), \
             patch('google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file') as factory:
            factory.return_value.run_local_server.side_effect = WSGITimeoutError('callback expired')
            with self.assertRaisesRegex(SystemExit, 'timed out. No token was saved'):
                runpy.run_path(str(script), run_name='__main__')
        self.assertFalse(output.exists())


if __name__ == '__main__':
    unittest.main()
