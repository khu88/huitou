"""HTTP-level account/security checks. All users and DBs are temporary."""
import http.client
import json
import sqlite3
import stat
import sys
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from server import COOKIE_NAME, DEFAULT_STATE, AccountStore, make_server, token_hash


PASSWORD = 'Temporary-Passphrase-42'
REMINDER = {
    'id': 'cvpr-main-abstract-1440', 'conferenceId': 'cvpr',
    'trackName': 'Main Conference', 'kind': 'abstract',
    'deadline': '2026-11-10T23:59:00-12:00', 'leadMinutes': 1440, 'enabled': True,
}


class Client:
    def __init__(self, server):
        self.server = server
        self.cookie = None
        self.csrf = None
        self.bearer = None

    def request(self, method, path, body=None, headers=None, use_csrf=True, raw=None):
        request_headers = {'Origin': f'http://127.0.0.1:{self.server.server_port}'}
        if self.cookie:
            request_headers['Cookie'] = self.cookie
        if self.bearer:
            request_headers['Authorization'] = 'Bearer ' + self.bearer
        if self.csrf and use_csrf:
            request_headers['X-CSRF-Token'] = self.csrf
        if body is not None:
            raw = json.dumps(body, ensure_ascii=False).encode()
            request_headers['Content-Type'] = 'application/json'
        if raw is not None:
            request_headers['Content-Length'] = str(len(raw))
        request_headers.update(headers or {})
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=10)
        connection.request(method, path, body=raw, headers=request_headers)
        response = connection.getresponse()
        payload = response.read()
        result = json.loads(payload) if response.getheader('Content-Type', '').startswith('application/json') else payload
        cookie = response.getheader('Set-Cookie')
        if cookie is not None:
            self.cookie = cookie.split(';', 1)[0]
        if isinstance(result, dict) and result.get('csrfToken'):
            self.csrf = result['csrfToken']
        output = response.status, result, dict(response.getheaders())
        connection.close()
        return output

    def register(self, username='owner', password=PASSWORD, display_name='研究者'):
        return self.request('POST', '/api/auth/register', {'username': username, 'password': password, 'displayName': display_name})

    def login(self, username='owner', password=PASSWORD):
        return self.request('POST', '/api/auth/login', {'username': username, 'password': password})


class AccountHTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='conf-atlas-auth-test-')
        self.root = Path(self.temp.name) / 'root'
        self.root.mkdir()
        (self.root / 'index.html').write_text('<h1>Test app</h1>')
        (self.root / 'data').mkdir()
        (self.root / 'data' / 'conferences.json').write_text('{"test": true}')
        (self.root / 'server.py').write_text('private source')
        self.database = self.root / '.local' / 'app.sqlite3'
        self.server = make_server(self.root, self.database, port=0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.client = Client(self.server)

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        self.temp.cleanup()


    def test_first_registration_is_regular_with_secure_password_and_cookie(self):
        status, result, headers = self.client.register()
        self.assertEqual(status, 201)
        self.assertEqual(result['user']['role'], 'user')
        self.assertEqual(result['state'], DEFAULT_STATE)
        self.assertEqual(set(result['user']), {'id', 'username', 'displayName', 'role', 'active', 'createdAt'})
        self.assertIn('HttpOnly', headers['Set-Cookie'])
        self.assertIn('SameSite=Strict', headers['Set-Cookie'])
        self.assertNotIn(PASSWORD, json.dumps(result))
        self.assertNotIn('sessionToken', result)
        self.assertEqual(stat.S_IMODE(self.database.stat().st_mode), 0o600)
        with self.server.store.connect() as db:
            user = db.execute('SELECT * FROM users').fetchone()
            session = db.execute('SELECT * FROM sessions').fetchone()
            self.assertNotEqual(user['password_hash'], PASSWORD)
            self.assertEqual(len(user['salt']), 32)
            raw_token = self.client.cookie.split('=', 1)[1]
            self.assertEqual(session['token_hash'], token_hash(raw_token))
            self.assertNotEqual(session['token_hash'], raw_token)
        self.assertEqual(self.client.request('GET', '/api/session')[1]['user']['username'], 'owner')

    def test_second_user_is_regular_and_has_distinct_salt(self):
        self.client.register('owner')
        other = Client(self.server)
        result = other.register('student')[1]
        self.assertEqual(result['user']['role'], 'user')
        with self.server.store.connect() as db:
            values = db.execute('SELECT salt, password_hash FROM users').fetchall()
            self.assertNotEqual(values[0]['salt'], values[1]['salt'])
            self.assertNotEqual(values[0]['password_hash'], values[1]['password_hash'])

    def test_native_token_auth_csrf_logout_and_route_separation(self):
        status, result, headers = self.client.request('POST', '/api/mobile/auth/register',
                                                    {'username': 'mobile_owner', 'password': PASSWORD})
        self.assertEqual(status, 201)
        self.assertNotIn('Set-Cookie', headers)
        self.assertIsNone(self.client.cookie)
        self.assertEqual(len(result['sessionToken']), 43)
        self.client.bearer = result['sessionToken']
        self.assertEqual(self.client.request('GET', '/api/session')[1]['user']['username'], 'mobile_owner')
        self.assertEqual(self.client.request('PUT', '/api/state', {'reminders': [REMINDER]}, use_csrf=False)[0], 403)
        self.assertEqual(self.client.request('PUT', '/api/state', {'reminders': [REMINDER]})[0], 200)
        old_token = self.client.bearer
        status, result, headers = self.client.request('POST', '/api/mobile/auth/login',
                                                    {'username': 'mobile_owner', 'password': PASSWORD})
        self.assertEqual(status, 200)
        self.assertNotIn('Set-Cookie', headers)
        self.assertNotEqual(old_token, result['sessionToken'])
        self.assertIsNone(self.server.store.session(old_token))
        self.client.bearer = result['sessionToken']
        self.assertEqual(self.client.request('POST', '/api/auth/logout', {})[0], 200)
        self.assertIsNone(self.client.request('GET', '/api/session')[1]['user'])

    def test_native_tokens_revoked_by_password_change(self):
        native = Client(self.server)
        status, result, _ = native.request('POST', '/api/mobile/auth/register',
                                           {'username': 'mobile_student', 'password': PASSWORD})
        self.assertEqual(status, 201)
        native.bearer = result['sessionToken']
        student_id = result['user']['id']
        self.assertEqual(native.request('POST', '/api/password',
                                        {'currentPassword': PASSWORD, 'newPassword': 'New-Mobile-Password-43'})[0], 200)
        self.assertIsNone(native.request('GET', '/api/session')[1]['user'])
        result = native.request('POST', '/api/mobile/auth/login',
                                {'username': 'mobile_student', 'password': 'New-Mobile-Password-43'})[1]
        native.bearer = result['sessionToken']
        self.assertEqual(native.request('GET', '/api/session')[1]['user']['id'], student_id)

    def test_native_invalid_header_does_not_fall_back_and_origin_stays_protected(self):
        self.client.register()
        for value in ['Bearer invalid', 'Basic dXNlcjpwYXNz', 'Bearer ', '']:
            self.assertIsNone(self.client.request('GET', '/api/session', headers={'Authorization': value})[1]['user'])
            self.assertEqual(self.client.request('PUT', '/api/state', {'favorites': ['cvpr']},
                                                 headers={'Authorization': value})[0], 401)
        self.assertEqual(self.client.request('POST', '/api/mobile/auth/login',
                                             {'username': 'owner', 'password': PASSWORD},
                                             headers={'Origin': 'https://attacker.example'})[0], 403)
        self.assertEqual(self.client.request('POST', '/api/mobile/auth/login',
                                             {'username': 'owner', 'password': PASSWORD},
                                             headers={'Host': 'api.example.com'})[0], 403)


    def test_optional_account_extension_is_absent_in_public_install(self):
        self.assertIsNone(self.server.store.extension)
        self.assertEqual(self.client.request('GET','/api/account-extension')[0],404)
        self.assertEqual(self.client.request('PATCH','/api/unknown-extension',{})[0],404)
        self.client.register()
        self.assertNotIn('accountExtension',self.client.request('GET','/api/session')[1])

    def test_invalid_registration_and_casefold_duplicates(self):
        self.assertEqual(self.client.register('ab')[0], 400)
        self.assertEqual(self.client.register('owner', password='short')[0], 400)
        self.assertEqual(self.client.register('owner', display_name='bad\nname')[0], 400)
        self.assertEqual(self.client.register('Owner')[0], 201)
        self.assertEqual(self.client.register('owner')[0], 409)

    def test_anonymous_and_csrf_protection(self):
        self.assertEqual(self.client.request('GET', '/api/session')[1], {'user': None, 'csrfToken': None, 'state': None})
        self.assertEqual(self.client.request('PUT', '/api/state', {'favorites': ['cvpr']})[0], 401)
        self.client.register()
        self.assertEqual(self.client.request('PUT', '/api/state', {'favorites': ['cvpr']}, use_csrf=False)[0], 403)
        self.assertEqual(self.client.request('PUT', '/api/state', {'favorites': ['cvpr']}, headers={'X-CSRF-Token': 'wrong'})[0], 403)
        self.assertEqual(self.client.request('PUT', '/api/state', {'favorites': ['cvpr']})[0], 200)

    def test_origin_host_and_json_gate(self):
        self.assertEqual(self.client.request('POST', '/api/auth/register', {}, headers={'Origin': 'https://attacker.example'})[0], 403)
        self.assertEqual(self.client.request('GET', '/', headers={'Host': 'attacker.example'})[0], 403)
        self.assertEqual(self.client.request('POST', '/api/auth/login', raw=b'username=owner', headers={'Content-Type': 'application/x-www-form-urlencoded'})[0], 415)
        self.assertEqual(self.client.request('POST', '/api/auth/login', raw=b'{broken', headers={'Content-Type': 'application/json'})[0], 400)
        self.assertEqual(self.client.request('POST', '/api/auth/login', {}, headers={'Sec-Fetch-Site': 'cross-site'})[0], 403)

    def test_state_profile_persistence_and_isolation(self):
        owner = self.client.register()[1]['user']
        data = {'favorites': ['cvpr', 'acl', 'cvpr'], 'settings': {'theme': 'dark', 'fontSize': 'large'}, 'relax': {'woodfish': 7}}
        status, result, _ = self.client.request('PUT', '/api/state', data)
        self.assertEqual(status, 200)
        self.assertEqual(result['state']['favorites'], ['cvpr', 'acl'])
        self.assertEqual(result['state']['settings']['timezone'], 'Asia/Singapore')
        self.assertEqual(result['state']['relax'], {'woodfish': 7, 'accepts': 0, 'amen': 0})
        self.assertEqual(self.client.request('PATCH', '/api/profile', {'displayName': '新昵称'})[1]['user']['displayName'], '新昵称')
        other = Client(self.server)
        self.assertEqual(other.register('student')[1]['state']['favorites'], [])
        fresh_store = AccountStore(self.database)
        with fresh_store.connect() as db:
            restored = fresh_store.state(db, owner['id'])
        self.assertEqual(restored['favorites'], ['cvpr', 'acl'])
        self.assertEqual(restored['relax']['woodfish'], 7)

    def test_state_validation(self):
        self.client.register()
        bad = [
            {'role': 'privileged'}, {'favorites': ['../../.local']}, {'favorites': 'cvpr'},
            {'settings': {'theme': 'invalid'}}, {'settings': {'sound': 'yes'}},
            {'settings': {'unknown': True}}, {'relax': {'woodfish': -1}},
            {'relax': {'accepts': True}}, {'relax': {'unknown': 1}},
        ]
        for body in bad:
            self.assertEqual(self.client.request('PUT', '/api/state', body)[0], 400, body)

    def test_reminders_persistence_isolation_and_partial_updates(self):
        owner = self.client.register()[1]['user']
        self.assertEqual(self.client.request('PUT', '/api/state', {'reminders': [REMINDER]}, use_csrf=False)[0], 403)
        status, payload, _ = self.client.request('PUT', '/api/state', {'favorites': ['cvpr'], 'reminders': [REMINDER]})
        self.assertEqual(status, 200)
        self.assertEqual(payload['state']['reminders'], [REMINDER])
        self.client.request('PUT', '/api/state', {'settings': {'theme': 'dark'}})
        self.client.request('POST', '/api/relax/increment', {'woodfish': 1})
        state = self.client.request('GET', '/api/session')[1]['state']
        self.assertEqual(state['reminders'], [REMINDER])
        other = Client(self.server)
        self.assertEqual(other.register('student')[1]['state']['reminders'], [])
        other.request('PUT', '/api/state', {'reminders': [{**REMINDER, 'enabled': False}]})
        restored_store = AccountStore(self.database)
        with restored_store.connect() as db:
            restored = restored_store.state(db, owner['id'])
        self.assertEqual(restored['reminders'], [REMINDER])
        self.assertEqual(restored['favorites'], ['cvpr'])
        self.assertEqual(restored['relax']['woodfish'], 1)
        self.client.request('PUT', '/api/state', {'reminders': []})
        self.assertEqual(self.client.request('GET', '/api/session')[1]['state']['reminders'], [])
        self.assertFalse(other.request('GET', '/api/session')[1]['state']['reminders'][0]['enabled'])

    def test_reminder_validation_rejects_invalid_updates_atomically(self):
        self.client.register()
        self.client.request('PUT', '/api/state', {'reminders': [REMINDER]})
        invalid = [
            {'id': ''}, {'id': '../local'}, {'id': 'r' * 161}, {'conferenceId': '../cvpr'},
            {'trackName': ''}, {'trackName': ' '}, {'trackName': 'Main\nTrack'}, {'trackName': 'x' * 201},
            {'kind': 'deadline'}, {'kind': []}, {'deadline': '2026-11-10'},
            {'deadline': '2026-11-10T23:59:00'}, {'deadline': '2026-02-30T23:59:00Z'},
            {'deadline': '2026-11-10T23:59:00+25:00'}, {'deadline': None},
            {'leadMinutes': True}, {'leadMinutes': -1}, {'leadMinutes': 1}, {'leadMinutes': 1.5},
            {'enabled': 1}, {'url': 'https://example.com'},
        ]
        bodies = [{'reminders': [{**REMINDER, **patch}]} for patch in invalid]
        bodies.extend([{'reminders': {}}, {'reminders': [None]}, {'reminders': [REMINDER, REMINDER]},
                       {'reminders': [{key: value for key, value in REMINDER.items() if key != 'enabled'}]}])
        for body in bodies:
            body['favorites'] = ['must-not-save']
            status, payload, _ = self.client.request('PUT', '/api/state', body)
            self.assertEqual(status, 400, body)
            self.assertEqual(payload['error']['code'], 'invalid_reminders')
        state = self.client.request('GET', '/api/session')[1]['state']
        self.assertEqual(state['reminders'], [REMINDER])
        self.assertEqual(state['favorites'], [])

    def test_reminder_list_limit_and_timezone_formats(self):
        self.client.register()
        reminders = [{**REMINDER, 'id': f'reminder-{i}', 'trackName': '学' * 200} for i in range(200)]
        reminders[0]['deadline'] = '2026-11-10T13:00:00Z'
        reminders[1]['deadline'] = '2026-11-10T13:00+00:00'
        self.assertEqual(self.client.request('PUT', '/api/state', {'reminders': reminders})[0], 200)
        reminders.append({**REMINDER, 'id': 'reminder-200'})
        self.assertEqual(self.client.request('PUT', '/api/state', {'reminders': reminders})[0], 400)
        self.assertEqual(len(self.client.request('GET', '/api/session')[1]['state']['reminders']), 200)

    def test_legacy_state_receives_new_defaults_without_losing_values(self):
        owner = self.client.register()[1]['user']
        legacy = {'favorites': ['cvpr'], 'settings': {'theme': 'dark'}, 'relax': {'woodfish': 18}}
        with self.server.store.connect() as db:
            db.execute('UPDATE user_state SET data=? WHERE user_id=?', (json.dumps(legacy), owner['id']))
        state = self.client.request('GET', '/api/session')[1]['state']
        self.assertEqual(state['reminders'], [])
        self.assertEqual(state['settings']['theme'], 'dark')
        self.assertEqual(state['settings']['fontSize'], 'standard')
        self.assertEqual(state['relax'], {'woodfish': 18, 'accepts': 0, 'amen': 0})
        self.assertEqual(state['favorites'], ['cvpr'])
        self.assertEqual(self.client.request('PUT', '/api/state', {'reminders': [REMINDER]})[0], 200)
        with self.server.store.connect() as db:
            stored = json.loads(db.execute('SELECT data FROM user_state WHERE user_id=?', (owner['id'],)).fetchone()[0])
        self.assertEqual(stored['reminders'], [REMINDER])
        self.assertEqual(stored['relax']['woodfish'], 18)

    def test_atomic_relax_increments_preserve_other_state(self):
        self.client.register()
        self.client.request('PUT', '/api/state', {'favorites': ['cvpr'], 'settings': {'theme': 'dark'}})
        self.assertEqual(self.client.request('POST', '/api/relax/increment', {'woodfish': 2, 'accepts': 1})[1]['relax'],
                         {'woodfish': 2, 'accepts': 1, 'amen': 0})
        cookie, csrf = self.client.cookie, self.client.csrf

        def tap(_):
            client = Client(self.server)
            client.cookie, client.csrf = cookie, csrf
            return client.request('POST', '/api/relax/increment', {'woodfish': 3, 'amen': 1})[0]

        with ThreadPoolExecutor(max_workers=8) as pool:
            statuses = list(pool.map(tap, range(16)))
        self.assertEqual(statuses, [200] * 16)
        state = self.client.request('GET', '/api/session')[1]['state']
        self.assertEqual(state['relax'], {'woodfish': 50, 'accepts': 1, 'amen': 16})
        self.assertEqual(state['favorites'], ['cvpr'])
        self.assertEqual(state['settings']['theme'], 'dark')

    def test_relax_increment_auth_csrf_and_bounds(self):
        self.assertEqual(self.client.request('POST', '/api/relax/increment', {'woodfish': 1})[0], 401)
        self.client.register()
        self.assertEqual(self.client.request('POST', '/api/relax/increment', {'woodfish': 1}, use_csrf=False)[0], 403)
        for body in [{}, {'wrong': 1}, {'woodfish': -1}, {'woodfish': True}, {'woodfish': 0.5}, {'woodfish': 1001}, {'woodfish': 600, 'amen': 401}]:
            self.assertEqual(self.client.request('POST', '/api/relax/increment', body)[0], 400, body)
        self.assertEqual(self.client.request('POST', '/api/relax/increment', {'woodfish': 600, 'amen': 400})[0], 200)
        self.client.request('PUT', '/api/state', {'relax': {'woodfish': 1_000_000_000}})
        self.assertEqual(self.client.request('POST', '/api/relax/increment', {'woodfish': 1})[0], 400)

    def test_logout_revokes_token_and_login_survives_reload(self):
        self.client.register()
        old_cookie = self.client.cookie
        self.assertEqual(self.client.request('POST', '/api/auth/logout', {})[0], 200)
        self.assertIsNone(self.client.request('GET', '/api/session')[1]['user'])
        replay = Client(self.server)
        replay.cookie = old_cookie
        self.assertIsNone(replay.request('GET', '/api/session')[1]['user'])
        self.assertEqual(self.client.login()[0], 200)
        reload_client = Client(self.server)
        reload_client.cookie = self.client.cookie
        self.assertEqual(reload_client.request('GET', '/api/session')[1]['user']['username'], 'owner')

    def test_password_change_revokes_all_sessions(self):
        self.client.register()
        other = Client(self.server)
        other.login()
        result = self.client.request('POST', '/api/password', {'currentPassword': PASSWORD, 'newPassword': 'New-Temporary-Passphrase-43'})
        self.assertEqual(result[0], 200)
        self.assertTrue(result[1]['requiresLogin'])
        self.assertIsNone(other.request('GET', '/api/session')[1]['user'])
        self.assertEqual(self.client.login(password=PASSWORD)[0], 401)
        self.assertEqual(self.client.login(password='New-Temporary-Passphrase-43')[0], 200)




    def test_account_delete_requires_session_csrf_and_correct_password(self):
        self.assertEqual(self.client.request('POST', '/api/account/delete', {'currentPassword': PASSWORD})[0], 401)
        user = self.client.register()[1]['user']
        self.assertEqual(self.client.request('POST', '/api/account/delete', {'currentPassword': PASSWORD}, use_csrf=False)[0], 403)
        self.assertEqual(self.client.request('POST', '/api/account/delete', {'currentPassword': PASSWORD}, headers={'Origin': 'https://attacker.example'})[0], 403)
        self.assertEqual(self.client.request('POST', '/api/account/delete', {'currentPassword': PASSWORD, 'userId': user['id']})[0], 400)
        self.assertEqual(self.client.request('POST', '/api/account/delete', {'currentPassword': ''})[0], 400)
        status, payload, _ = self.client.request('POST', '/api/account/delete', {'currentPassword': 'Wrong-Password-43'})
        self.assertEqual(status, 401)
        self.assertEqual(payload['error']['code'], 'wrong_password')
        self.assertEqual(self.client.request('GET', '/api/session')[1]['user']['id'], user['id'])

    def test_account_delete_removes_only_own_data_and_revokes_every_session(self):
        owner = self.client.register()[1]['user']
        self.client.request('PUT', '/api/state', {'favorites': ['cvpr'], 'reminders': [REMINDER], 'relax': {'amen': 4}})
        second_session = Client(self.server)
        second_session.login()
        native = Client(self.server)
        result = native.request('POST', '/api/mobile/auth/login', {'username': 'owner', 'password': PASSWORD})[1]
        native.bearer = result['sessionToken']
        other = Client(self.server)
        student = other.register('student')[1]['user']
        other.request('PUT', '/api/state', {'favorites': ['acl']})
        status, payload, headers = self.client.request('POST', '/api/account/delete', {'currentPassword': PASSWORD})
        self.assertEqual(status, 200)
        self.assertEqual(payload, {'ok': True, 'requiresLogin': True})
        self.assertIn('Max-Age=0', headers['Set-Cookie'])
        for client in [self.client, second_session, native]:
            self.assertIsNone(client.request('GET', '/api/session')[1]['user'])
        with self.server.store.connect() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM users WHERE id=?', (owner['id'],)).fetchone()[0], 0)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM user_state WHERE user_id=?', (owner['id'],)).fetchone()[0], 0)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM sessions WHERE user_id=?', (owner['id'],)).fetchone()[0], 0)
        self.assertEqual(other.request('GET', '/api/session')[1]['user']['id'], student['id'])
        self.assertEqual(other.request('GET', '/api/session')[1]['state']['favorites'], ['acl'])
        self.assertEqual(self.client.login()[0], 401)
        replacement = self.client.register()[1]
        self.assertNotEqual(replacement['user']['id'], owner['id'])
        self.assertEqual(replacement['user']['role'], 'user')
        self.assertEqual(replacement['state'], DEFAULT_STATE)


    def test_expired_session_is_not_authenticated(self):
        self.client.register()
        with self.server.store.connect() as db:
            db.execute('UPDATE sessions SET expires_at=0')
        status, result, headers = self.client.request('GET', '/api/session')
        self.assertEqual(status, 200)
        self.assertIsNone(result['user'])
        self.assertIn('Max-Age=0', headers['Set-Cookie'])

    def test_server_restart_preserves_account_state_and_session(self):
        self.client.register()
        cookie = self.client.cookie
        self.client.request('PUT', '/api/state', {'favorites': ['cvpr'], 'relax': {'amen': 9}, 'reminders': [REMINDER]})
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        self.server = make_server(self.root, self.database, port=0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        restored = Client(self.server)
        restored.cookie = cookie
        status, payload, _ = restored.request('GET', '/api/session')
        self.assertEqual(status, 200)
        self.assertEqual(payload['user']['username'], 'owner')
        self.assertEqual(payload['state']['favorites'], ['cvpr'])
        self.assertEqual(payload['state']['relax']['amen'], 9)
        self.assertEqual(payload['state']['reminders'], [REMINDER])
        self.assertEqual(restored.request('PUT', '/api/state', {'settings': {'theme': 'dark'}})[0], 200)

    def test_login_rate_limit(self):
        self.client.register()
        for _ in range(5):
            self.assertEqual(self.client.login(password='Wrong-Passphrase-42')[0], 401)
        status, result, headers = self.client.login(password=PASSWORD)
        self.assertEqual(status, 429)
        self.assertEqual(result['error']['code'], 'login_rate_limited')
        self.assertIn('Retry-After', headers)

    def test_static_allowlist_and_traversal_rejection(self):
        self.assertEqual(self.client.request('GET', '/')[0], 200)
        self.assertEqual(self.client.request('GET', '/data/conferences.json')[0], 200)
        for path in ['/.local/app.sqlite3', '/.local/app.sqlite3-wal', '/server.py', '/research/ccf-catalog.json', '/..%2F.local/app.sqlite3', '/%2e%2e/server.py']:
            self.assertEqual(self.client.request('GET', path)[0], 404, path)
        outside = Path(self.temp.name) / 'secret.js'
        outside.write_text('secret')
        (self.root / 'portal.js').symlink_to(outside)
        self.assertEqual(self.client.request('GET', '/portal.js')[0], 404)

    def test_web_assets_are_explicitly_served_without_exposing_siblings(self):
        (self.root / 'assets').mkdir()
        assets = {
            '/assets/woodfish.jpg': ('image/jpeg', b'jpeg-test'),
            '/assets/a-men-cat.jpg': ('image/jpeg', b'cat-test'),
            '/assets/wood-knock.wav': ('audio/wav', b'wave-test'),
            '/data/relax-content.js': ('text/javascript', b'window.RelaxContent = {};'),
            '/relax.js': ('text/javascript', b'// relax'),
            '/relax.css': ('text/css', b'/* relax */'),
            '/reminders.js': ('text/javascript', b'// reminders'),
            '/reminders.css': ('text/css', b'/* reminders */'),
        }
        for path, (mime, content) in assets.items():
            (self.root / path.lstrip('/')).write_bytes(content)
            status, payload, headers = self.client.request('GET', path)
            self.assertEqual(status, 200, path)
            self.assertEqual(payload, content)
            self.assertTrue(headers['Content-Type'].startswith(mime), path)
        (self.root / 'assets' / 'private.jpg').write_bytes(b'private')
        self.assertEqual(self.client.request('GET', '/assets/private.jpg')[0], 404)
        self.assertEqual(self.client.request('GET', '/assets/')[0], 404)
        (self.root / 'assets' / 'woodfish.jpg').unlink()
        (self.root / 'assets' / 'woodfish.jpg').symlink_to(self.root / 'server.py')
        self.assertEqual(self.client.request('GET', '/assets/woodfish.jpg')[0], 404)


if __name__ == '__main__':
    unittest.main(verbosity=2)
