"""Durable anonymous shared counters.

Every test owns a temporary SQLite database; no real account or network provider.
"""
import tempfile
import threading
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from server import APIError, AccountStore, make_server
from test_server import Client, PASSWORD


class CommunityStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='conf-community-test-')
        self.path = Path(self.temp.name) / 'accounts.sqlite3'
        self.store = AccountStore(self.path)

    def tearDown(self):
        self.temp.cleanup()

    def tap(self, stream, total, address='127.0.0.1'):
        return self.store.increment_community_woodfish(
            {'streamId': stream, 'total': total, 'instanceId': self.store.community_stats()['instanceId']}, address)

    def test_duplicate_reordered_concurrent_streams_are_atomic(self):
        streams = [str(uuid.uuid4()) for _ in range(3)]
        jobs = [(stream, total) for stream in streams for total in list(range(1, 31)) + [17, 30, 8]]
        with ThreadPoolExecutor(max_workers=12) as pool:
            list(pool.map(lambda args: self.tap(*args), jobs))
        self.assertEqual(self.store.community_stats()['woodfishTotal'], 90)
        for stream in streams:
            result = self.tap(stream, 10)
            self.assertEqual(result['acceptedTotal'], 30)
            self.assertEqual(result['woodfishTotal'], 90)

    def test_restart_preserves_counter_instance_and_dedup(self):
        stream = str(uuid.uuid4())
        before = self.tap(stream, 7)
        self.store = AccountStore(self.path)
        after = self.tap(stream, 7)
        self.assertEqual(before, after)
        self.assertEqual(self.tap(stream, 9)['woodfishTotal'], 9)
        other = AccountStore(Path(self.temp.name) / 'other.sqlite3')
        self.assertNotEqual(other.community_stats()['instanceId'], after['instanceId'])

    def test_old_instance_pending_taps_rejected_before_any_write(self):
        old_instance = self.store.community_stats()['instanceId']
        replacement = AccountStore(Path(self.temp.name) / 'replacement.sqlite3')
        body = {'streamId': str(uuid.uuid4()), 'total': 4, 'instanceId': old_instance}
        with self.assertRaises(APIError) as error:
            replacement.increment_community_woodfish(body, '127.0.0.1')
        self.assertEqual(error.exception.status, 409)
        self.assertEqual(error.exception.code, 'community_instance_changed')
        self.assertEqual(replacement.community_stats()['woodfishTotal'], 0)
        with replacement.connect() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM community_streams').fetchone()[0], 0)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM community_rate_limits').fetchone()[0], 0)

    def test_private_relax_counts_never_imported_or_double_counted(self):
        user = self.store.register('researcher', None, PASSWORD)[0]['user']['id']
        self.store.increment_relax(user, {'woodfish': 7})
        self.store.save_state(user, {'relax': {'woodfish': 800}})
        self.assertEqual(self.store.community_stats()['woodfishTotal'], 0)
        self.tap(str(uuid.uuid4()), 3)
        self.store.increment_relax(user, {'woodfish': 1})
        self.assertEqual(self.store.community_stats()['woodfishTotal'], 3)
        self.store.delete_account(user, PASSWORD)
        self.assertEqual(self.store.community_stats()['woodfishTotal'], 3)

    def test_invalid_inputs_and_large_delta_do_not_change_totals(self):
        stream = str(uuid.uuid4())
        cases = [None, {}, {'streamId': stream, 'total': True},
                 {'streamId': stream, 'total': 1.5}, {'streamId': stream, 'total': -1},
                 {'streamId': stream, 'total': 1_000_000_001},
                 {'streamId': 'AAAAAAAA-AAAA-AAAA-AAAA-AAAAAAAAAAAA', 'total': 1},
                 {'streamId': 'anonymous', 'total': 1},
                 {'streamId': stream, 'total': 1, 'userId': 'someone'},
                 {'streamId': stream, 'total': 1001}]
        for body in cases:
            if isinstance(body, dict):
                body = {**body, 'instanceId': self.store.community_stats()['instanceId']}
            with self.subTest(body=body), self.assertRaises(APIError) as error:
                self.store.increment_community_woodfish(body, '127.0.0.1')
            self.assertEqual(error.exception.status, 400)
        self.assertEqual(self.store.community_stats()['woodfishTotal'], 0)
        with self.store.connect() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM community_streams').fetchone()[0], 0)
        for instance in [None, '', 'not-a-uuid', True]:
            body = {'streamId': stream, 'total': 1, 'instanceId': instance}
            with self.assertRaises(APIError) as error:
                self.store.increment_community_woodfish(body, '127.0.0.1')
            self.assertEqual(error.exception.status, 400)
        with self.assertRaises(APIError) as error:
            self.store.increment_community_woodfish({'streamId': stream, 'total': 1}, '127.0.0.1')
        self.assertEqual(error.exception.status, 400)

    def test_total_bound_failure_rolls_back_new_stream_and_quota(self):
        with self.store.connect() as db:
            db.execute('UPDATE community_totals SET woodfish_total=9007199254740991 WHERE id=1')
        with self.assertRaises(APIError) as error:
            self.tap(str(uuid.uuid4()), 1)
        self.assertEqual(error.exception.code, 'community_limit')
        with self.store.connect() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM community_streams').fetchone()[0], 0)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM community_rate_limits').fetchone()[0], 0)
        self.assertEqual(self.store.community_stats()['woodfishTotal'], 9007199254740991)

    def test_rate_limit_allows_idempotent_retry_and_recovers(self):
        stream = str(uuid.uuid4())
        with patch('server.time.time', return_value=100):
            self.assertEqual(self.tap(stream, 1000)['acceptedTotal'], 1000)
            self.assertEqual(self.tap(stream, 1000)['woodfishTotal'], 1000)
            with self.assertRaises(APIError) as error:
                self.tap(stream, 1001)
            self.assertEqual(error.exception.status, 429)
        with patch('server.time.time', return_value=161):
            self.assertEqual(self.tap(stream, 1001)['woodfishTotal'], 1001)

    def test_new_stream_quota_prevents_bloat_without_raw_addresses(self):
        with patch('server.COMMUNITY_STREAMS_PER_HOUR', 2), patch('server.time.time', return_value=100):
            # Merely querying a zero stream does not allocate rows or quota.
            self.tap(str(uuid.uuid4()), 0, 'private-address')
            first = str(uuid.uuid4())
            self.tap(first, 1, 'private-address')
            self.tap(str(uuid.uuid4()), 1, 'private-address')
            with self.assertRaises(APIError) as error:
                self.tap(str(uuid.uuid4()), 1, 'private-address')
            self.assertEqual(error.exception.code, 'community_streams_limited')
            self.assertEqual(self.tap(first, 2, 'private-address')['woodfishTotal'], 3)
            with self.store.connect() as db:
                rows = [dict(row) for row in db.execute('SELECT * FROM community_rate_limits')]
                self.assertNotIn('private-address', str(rows))
                self.assertEqual(db.execute('SELECT COUNT(*) FROM community_streams').fetchone()[0], 2)
        with patch('server.time.time', return_value=3701):
            self.assertEqual(self.tap(str(uuid.uuid4()), 1, 'private-address')['woodfishTotal'], 4)




class CommunityHTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='conf-community-http-')
        self.root = Path(self.temp.name)
        (self.root / 'index.html').write_text('<p>QA</p>')
        self.server = make_server(self.root, self.root / 'test.sqlite3', port=0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.client = Client(self.server)

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        self.temp.cleanup()

    def test_guest_stats_expose_only_shared_counter_fields(self):
        status, result, headers = self.client.request('GET', '/api/community/stats')
        self.assertEqual(status, 200)
        self.assertEqual(set(result), {'woodfishTotal', 'startedAt', 'scope', 'instanceId'})
        self.assertEqual(result['scope'], 'instance')
        self.assertEqual(headers['Cache-Control'], 'no-store')
        self.assertEqual(self.client.request('GET', '/api/account-extension')[0], 404)
        body = {'streamId': str(uuid.uuid4()), 'total': 4, 'instanceId': result['instanceId']}
        status, result, _ = self.client.request('POST', '/api/community/woodfish', body, use_csrf=False)
        self.assertEqual((status, result['woodfishTotal'], result['acceptedTotal']), (200, 4, 4))
        self.client.register()
        self.assertEqual(self.client.request('GET', '/api/account-extension')[0], 404)
        self.assertNotIn('accountExtension', self.client.request('GET', '/api/session')[1])

    def test_anonymous_write_keeps_origin_host_and_content_type_guards(self):
        body = {'streamId': str(uuid.uuid4()), 'total': 4,
                'instanceId': self.server.store.community_stats()['instanceId']}
        for headers in [{'Origin': 'https://attacker.example'}, {'Host': 'attacker.example'},
                        {'Sec-Fetch-Site': 'cross-site'}]:
            self.assertEqual(self.client.request('POST', '/api/community/woodfish', body, headers=headers)[0], 403)
        self.assertEqual(self.client.request('POST', '/api/community/woodfish', body,
                                            headers={'Content-Type': 'text/plain'})[0], 415)
        self.assertEqual(self.server.store.community_stats()['woodfishTotal'], 0)
        # Guest aggregation does not loosen the protected personal state route.
        self.assertEqual(self.client.request('POST', '/api/relax/increment', {'woodfish': 1})[0], 401)

    def test_database_replacement_between_get_and_post_returns_conflict(self):
        instance = self.client.request('GET', '/api/community/stats')[1]['instanceId']
        self.server.store = AccountStore(self.root / 'replacement.sqlite3')
        body = {'streamId': str(uuid.uuid4()), 'total': 3, 'instanceId': instance}
        status, result, _ = self.client.request('POST', '/api/community/woodfish', body)
        self.assertEqual(status, 409)
        self.assertEqual(result['error']['code'], 'community_instance_changed')
        self.assertEqual(self.client.request('GET', '/api/community/stats')[1]['woodfishTotal'], 0)
        with self.server.store.connect() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM community_streams').fetchone()[0], 0)


if __name__ == '__main__':
    unittest.main()
