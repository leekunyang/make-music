import datetime as dt
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import core


class WatchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.config = root / 'release-watch.json'
        core.save_json(self.config, {
            'artist': 'Said the Sky', 'timezone': 'Asia/Taipei',
            'recipient_email': 'listener@example.com',
            'spotify_artist_id': 'a' * 22, 'schedule_created': False
        })
        self.local = root / '.local'
        self.patches = [patch.object(core, 'CONFIG', self.config), patch.object(core, 'LOCAL', self.local)]
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)

    def album(self, ident, day, precision='day'):
        return {'id': ident, 'release_date': day, 'release_date_precision': precision,
                'name': 'Track ' + ident, 'album_type': 'single',
                'external_urls': {'spotify': 'https://open.spotify.com/album/' + ident}}

    def result(self):
        return {'artist': 'Said the Sky', 'since': '2026-10-11', 'through': '2026-10-12',
                'releases': [{'id': 'track', 'release_title': 'New Track',
                              'release_date': '2026-10-12', 'spotify_url': 'https://open.spotify.com/album/track'}]}

    def test_pagination_deduplication_and_date_precision(self):
        core.save_json(self.local / 'secrets.json', {'spotify_client_id': 'test', 'spotify_client_secret': 'test'})
        responses = [
            {'access_token': 'test'}, {'name': 'Said the Sky'},
            {'items': [self.album('first', '2026-10-12'), self.album('old', '2026-09-01')],
             'next': 'https://api.spotify.com/v1/artists/' + 'a' * 22 + '/albums?offset=50'},
            {'items': [self.album('first', '2026-10-12'), self.album('second', '2026-10-11'),
                       self.album('vague', '2026', 'year')], 'next': None}
        ]
        with patch.object(core, 'request_json', side_effect=responses) as api:
            result = core.check_releases('2026-10-11', '2026-10-12')
        self.assertEqual(api.call_count, 4)
        self.assertEqual({item['id'] for item in result['releases']}, {'first', 'second'})
        self.assertEqual(result['skipped_imprecise_dates'], 1)

    def test_date_window_is_yesterday_through_today(self):
        with patch.object(core, 'today', return_value=dt.date(2026, 10, 12)):
            self.assertEqual(core.date_window(core.settings()), (dt.date(2026, 10, 11), dt.date(2026, 10, 12)))
        with self.assertRaises(core.WatchError):
            core.date_window(core.settings(), '2026-10-13', '2026-10-12')

    def test_successful_notification_is_not_sent_twice(self):
        core.save_json(self.local / 'gmail-token.json', {'test': True})
        with patch.object(core, 'check_releases', return_value=self.result()), patch.object(core, 'gmail_send', return_value={'id': 'mail1'}) as send:
            self.assertEqual(core.notify()['status'], 'sent')
            self.assertEqual(core.notify()['status'], 'no_new_releases')
            self.assertEqual(send.call_count, 1)
        self.assertNotIn('pending_send', core.read_json(self.local / 'state.json'))

    def test_ambiguous_send_does_not_retry_automatically(self):
        core.save_json(self.local / 'gmail-token.json', {'test': True})
        with patch.object(core, 'check_releases', return_value=self.result()), patch.object(core, 'gmail_send', side_effect=core.WatchError('timeout')) as send:
            with self.assertRaises(core.WatchError):
                core.notify()
            with self.assertRaisesRegex(core.WatchError, '上次寄信結果未確認'):
                core.notify()
            self.assertEqual(send.call_count, 1)

    def test_no_releases_sends_no_mail(self):
        result = self.result()
        result['releases'] = []
        with patch.object(core, 'check_releases', return_value=result), patch.object(core, 'gmail_send') as send:
            self.assertEqual(core.notify()['sent'], 0)
            send.assert_not_called()

    def test_missing_gmail_does_not_create_pending_intent(self):
        with patch.object(core, 'check_releases', return_value=self.result()):
            with self.assertRaisesRegex(core.WatchError, 'Gmail 尚未授權'):
                core.notify()
        self.assertFalse((self.local / 'state.json').exists())

    def test_mail_content_and_recipient(self):
        preview = core.notification_preview(self.result())
        self.assertEqual(preview['to'], 'listener@example.com')
        self.assertIn('New Track', preview['body'])
        self.assertIn('https://open.spotify.com/album/track', preview['body'])

    def test_stdio_handshake_tools_and_unknown_tool(self):
        messages = [
            {'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {
                'protocolVersion': '2025-03-26', 'capabilities': {}, 'clientInfo': {'name': 'test', 'version': '1'}}},
            {'jsonrpc': '2.0', 'method': 'notifications/initialized'},
            {'jsonrpc': '2.0', 'id': 2, 'method': 'tools/list'},
            {'jsonrpc': '2.0', 'id': 3, 'method': 'tools/call', 'params': {'name': 'get_watch_status'}},
            {'jsonrpc': '2.0', 'id': 4, 'method': 'tools/call', 'params': {'name': 'unknown'}}
        ]
        response = subprocess.run([sys.executable, str(core.ROOT / 'server.py')],
            input='\n'.join(json.dumps(item) for item in messages) + '\n', text=True, capture_output=True, check=True)
        rows = [json.loads(line) for line in response.stdout.splitlines()]
        self.assertEqual(len(rows), 4)
        self.assertEqual(rows[0]['result']['protocolVersion'], '2025-03-26')
        self.assertEqual(len(rows[1]['result']['tools']), 4)
        self.assertFalse(rows[2]['result']['isError'])
        self.assertEqual(rows[3]['error']['code'], -32602)


if __name__ == '__main__':
    unittest.main()
