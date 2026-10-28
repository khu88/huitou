"""Local-only conference app server with SQLite accounts and cookie sessions.

Only Python's standard library is required. This is intentionally a loopback
service; exposing it remotely requires an HTTPS deployment and a separate review.
"""
from __future__ import annotations

import hashlib
import importlib.util
import hmac
import json
import os
import re
import secrets
import sqlite3
import time
import unicodedata
import uuid
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit
from wechat_service import WeChatService, WeChatError
from wechat_transport import ILinkError


PASSWORD_ITERATIONS = 600_000
SESSION_SECONDS = 7 * 24 * 60 * 60
LOGIN_WINDOW = 5 * 60
LOGIN_LIMIT = 5
BODY_LIMIT = 262_144
COMMUNITY_STREAMS_PER_HOUR = 100
COMMUNITY_TAPS_PER_MINUTE = 1000
COOKIE_NAME = 'conf_atlas_session'
DEFAULT_STATE = {
    'favorites': [],
    'reminders': [],
    'settings': {
        'theme': 'system', 'fontSize': 'standard', 'timezone': 'Asia/Singapore',
        'sound': False, 'reducedMotion': False,
    },
    'relax': {'woodfish': 0, 'accepts': 0, 'amen': 0},
}
STATIC_FILES = {
    '/': 'index.html', '/index.html': 'index.html', '/styles.css': 'styles.css',
    '/app.js': 'app.js', '/portal.js': 'portal.js', '/portal.css': 'portal.css',
    '/reminders.js': 'reminders.js', '/reminders.css': 'reminders.css',
    '/wechat.js': 'wechat.js', '/wechat.css': 'wechat.css',
    '/services.js': 'services.js', '/services.css': 'services.css',
    '/relax.js': 'relax.js', '/relax.css': 'relax.css',
    '/community.js': 'community.js', '/site-config.js': 'site-config.js',
    '/data/conferences.json': 'data/conferences.json',
    '/data/relax-content.js': 'data/relax-content.js',
    '/assets/woodfish.jpg': 'assets/woodfish.jpg',
    '/assets/a-men-cat.jpg': 'assets/a-men-cat.jpg',
    '/assets/wood-knock.wav': 'assets/wood-knock.wav',
    '/dist/index.html': 'dist/index.html',
}
CONTENT_TYPES = {'.html': 'text/html; charset=utf-8', '.css': 'text/css; charset=utf-8',
                 '.js': 'text/javascript; charset=utf-8', '.json': 'application/json; charset=utf-8',
                 '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.png': 'image/png',
                 '.svg': 'image/svg+xml', '.wav': 'audio/wav'}


class APIError(Exception):
    def __init__(self, status, code, message):
        self.status, self.code, self.message = status, code, message
        super().__init__(message)


def iso_now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def token_hash(token):
    return hashlib.sha256(token.encode('utf-8')).hexdigest()


def password_hash(password, salt, iterations=PASSWORD_ITERATIONS):
    return hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), bytes.fromhex(salt), iterations).hex()


def normalized_username(value):
    if not isinstance(value, str):
        raise APIError(400, 'invalid_username', '用户名须为 3–32 个字母、数字、下划线、点或短横线。')
    value = unicodedata.normalize('NFC', value.strip())
    if not 3 <= len(value) <= 32 or not all(c.isalnum() or c in '_.-' for c in value):
        raise APIError(400, 'invalid_username', '用户名须为 3–32 个字母、数字、下划线、点或短横线。')
    return value, value.casefold()


def validate_password(value):
    if not isinstance(value, str) or not 10 <= len(value) <= 128:
        raise APIError(400, 'invalid_password', '密码长度须为 10–128 个字符。')
    if not value.strip():
        raise APIError(400, 'invalid_password', '密码不能全部为空白字符。')
    return value


def validate_display_name(value):
    if not isinstance(value, str):
        raise APIError(400, 'invalid_display_name', '昵称须为 1–40 个字符。')
    value = unicodedata.normalize('NFC', value.strip())
    if not 1 <= len(value) <= 40 or any(unicodedata.category(c).startswith('C') for c in value):
        raise APIError(400, 'invalid_display_name', '昵称须为 1–40 个字符，不能包含控制字符。')
    return value


def public_user(row):
    return {'id': row['id'], 'username': row['username'], 'displayName': row['display_name'],
            'role': row['role'], 'active': bool(row['active']), 'createdAt': row['created_at']}


def validate_reminders(values):
    if not isinstance(values, list) or len(values) > 200:
        raise APIError(400, 'invalid_reminders', '提醒须为列表，最多 200 条。')
    result, seen = [], set()
    fields = {'id', 'conferenceId', 'trackName', 'kind', 'deadline', 'leadMinutes', 'enabled'}
    for reminder in values:
        if not isinstance(reminder, dict) or set(reminder) != fields:
            raise APIError(400, 'invalid_reminders', '提醒字段不完整或包含无效字段。')
        identifier = reminder['id']
        conference_id = reminder['conferenceId']
        if not isinstance(identifier, str) or not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_.:-]{0,159}', identifier):
            raise APIError(400, 'invalid_reminders', '提醒 ID 无效。')
        if identifier in seen:
            raise APIError(400, 'invalid_reminders', '提醒 ID 不能重复。')
        if not isinstance(conference_id, str) or not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_-]{0,99}', conference_id):
            raise APIError(400, 'invalid_reminders', '提醒会议 ID 无效。')
        track = reminder['trackName']
        if not isinstance(track, str) or not track.strip() or len(track) > 200 or any(
            unicodedata.category(c).startswith('C') for c in track
        ):
            raise APIError(400, 'invalid_reminders', '提醒 Track 名称须为 1–200 个字符，不含控制字符。')
        if reminder['kind'] not in ('abstract', 'full'):
            raise APIError(400, 'invalid_reminders', '提醒类型须为 abstract 或 full。')
        deadline = reminder['deadline']
        # Validate the snapshot, not the current conference directory: a saved
        # configuration can outlive a source update. The UI reconciles changes.
        if not isinstance(deadline, str) or not re.fullmatch(
            r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2}(?:\.\d{1,6})?)?(?:Z|[+-]\d{2}:\d{2})', deadline
        ):
            raise APIError(400, 'invalid_reminders', '提醒截止时间必须包含日期、时间及明确时区。')
        try:
            parsed = datetime.fromisoformat(deadline.replace('Z', '+00:00'))
            if parsed.utcoffset() is None:
                raise ValueError('missing timezone')
        except (ValueError, OverflowError):
            raise APIError(400, 'invalid_reminders', '提醒截止时间无效。')
        if type(reminder['leadMinutes']) is not int or reminder['leadMinutes'] not in {0, 5, 60, 180, 1440, 4320, 10080}:
            raise APIError(400, 'invalid_reminders', '提醒提前时间无效。')
        if type(reminder['enabled']) is not bool:
            raise APIError(400, 'invalid_reminders', '提醒启用状态必须为布尔值。')
        seen.add(identifier)
        result.append(deepcopy(reminder))
    return result


def validate_state_patch(body, current):
    if not isinstance(body, dict) or not set(body) <= {'favorites', 'reminders', 'settings', 'relax'}:
        raise APIError(400, 'invalid_state', '用户数据字段无效。')
    result = deepcopy(current)
    if 'favorites' in body:
        values = body['favorites']
        if not isinstance(values, list) or len(values) > 1000 or any(
            not isinstance(v, str) or not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_-]{0,99}', v)
            for v in values
        ):
            raise APIError(400, 'invalid_favorites', '收藏须为会议 ID 列表，最多 1000 条。')
        result['favorites'] = list(dict.fromkeys(values))
    if 'reminders' in body:
        result['reminders'] = validate_reminders(body['reminders'])
    if 'settings' in body:
        settings = body['settings']
        if not isinstance(settings, dict) or not set(settings) <= set(DEFAULT_STATE['settings']):
            raise APIError(400, 'invalid_settings', '设置字段无效。')
        choices = {'theme': {'system', 'light', 'dark'}, 'fontSize': {'standard', 'large', 'extra'},
                   'timezone': {'Asia/Singapore', 'UTC', 'America/Los_Angeles'}}
        for key, value in settings.items():
            if key in choices and (not isinstance(value, str) or value not in choices[key]):
                raise APIError(400, 'invalid_settings', f'{key} 设置值无效。')
            if key in {'sound', 'reducedMotion'} and type(value) is not bool:
                raise APIError(400, 'invalid_settings', f'{key} 必须为布尔值。')
        result['settings'].update(settings)
    if 'relax' in body:
        values = body['relax']
        if not isinstance(values, dict) or not set(values) <= set(DEFAULT_STATE['relax']):
            raise APIError(400, 'invalid_relax', '解压记录字段无效。')
        if any(type(v) is not int or not 0 <= v <= 1_000_000_000 for v in values.values()):
            raise APIError(400, 'invalid_relax', '解压次数须为 0–1000000000 的整数。')
        result['relax'].update(values)
    return result


def load_local_extension(root, store):
    """Load an optional, locally installed account extension; never from a URL."""
    root = Path(root).resolve()
    source = root / '.local' / 'management' / 'backend.py'
    if not source.is_file():
        return None
    if source.resolve() != source:
        raise ValueError('Local extension must not be a symlink.')
    spec = importlib.util.spec_from_file_location('conf_atlas_local_extension_' + uuid.uuid4().hex, source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.create_extension(store)


class AccountStore:
    def __init__(self, path, extension_root=None):
        self.extension = None
        self.path = Path(path)
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        # Restrictive defaults apply only to newly created app-owned files; do
        # not change permissions of an existing user directory or database.
        try:
            descriptor = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            pass
        else:
            os.close(descriptor)
        with self.connect() as db:
            db.executescript('''
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY, username TEXT NOT NULL, username_key TEXT NOT NULL UNIQUE,
                    display_name TEXT NOT NULL, salt TEXT NOT NULL, password_hash TEXT NOT NULL,
                    iterations INTEGER NOT NULL, role TEXT NOT NULL DEFAULT 'user',
                    active INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS sessions (
                    token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id),
                    csrf_token TEXT NOT NULL, expires_at INTEGER NOT NULL, created_at INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS session_user ON sessions(user_id);
                CREATE TABLE IF NOT EXISTS user_state (
                    user_id TEXT PRIMARY KEY REFERENCES users(id), data TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS login_attempts (
                    bucket TEXT PRIMARY KEY, attempts INTEGER NOT NULL, window_start INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS community_totals (
                    id INTEGER PRIMARY KEY CHECK(id=1), woodfish_total INTEGER NOT NULL,
                    started_at TEXT NOT NULL, address_salt TEXT NOT NULL,
                    instance_id TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS community_streams (
                    stream_id TEXT PRIMARY KEY, total INTEGER NOT NULL,
                    window_start INTEGER NOT NULL, window_count INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS community_rate_limits (
                    bucket TEXT PRIMARY KEY, window_start INTEGER NOT NULL, count INTEGER NOT NULL
                );
            ''')
            if 'instance_id' not in {row['name'] for row in db.execute('PRAGMA table_info(community_totals)')}:
                db.execute("ALTER TABLE community_totals ADD COLUMN instance_id TEXT NOT NULL DEFAULT ''")
            # Existing rows and any older extra columns are preserved.
            db.execute('BEGIN IMMEDIATE')
            if not db.execute('SELECT 1 FROM community_totals WHERE id=1').fetchone():
                values = {'id': 1, 'woodfish_total': 0, 'started_at': iso_now(),
                          'address_salt': secrets.token_hex(32), 'instance_id': str(uuid.uuid4())}
                for column in db.execute('PRAGMA table_info(community_totals)'):
                    if column['name'] not in values and column['notnull'] and column['dflt_value'] is None:
                        values[column['name']] = 0 if 'INT' in column['type'].upper() else ''
                columns = ','.join('"' + name.replace('"', '""') + '"' for name in values)
                db.execute('INSERT INTO community_totals (' + columns + ') VALUES (' + ','.join('?' for _ in values) + ')', tuple(values.values()))
            db.execute("UPDATE community_totals SET instance_id=? WHERE id=1 AND instance_id=''", (str(uuid.uuid4()),))
        if extension_root is not None:
            self.extension = load_local_extension(extension_root, self)

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute('PRAGMA foreign_keys=ON')
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def new_session(self, db, user_id):
        now = int(time.time())
        token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        db.execute('DELETE FROM sessions WHERE expires_at <= ?', (now,))
        db.execute('INSERT INTO sessions VALUES (?, ?, ?, ?, ?)',
                   (token_hash(token), user_id, csrf, now + SESSION_SECONDS, now))
        return token, csrf

    def state(self, db, user_id):
        row = db.execute('SELECT data FROM user_state WHERE user_id=?', (user_id,)).fetchone()
        state = deepcopy(DEFAULT_STATE)
        if row:
            stored = json.loads(row['data'])
            for key in state:
                if key in stored:
                    if isinstance(state[key], dict):
                        state[key].update(stored[key])
                    else:
                        state[key] = stored[key]
        return state

    def session(self, token):
        if not token or not re.fullmatch(r'[A-Za-z0-9_-]{43}', token):
            return None
        with self.connect() as db:
            row = db.execute('''SELECT u.*, s.csrf_token, s.expires_at, s.token_hash AS session_hash
                                FROM sessions s JOIN users u ON s.user_id=u.id
                                WHERE s.token_hash=? AND s.expires_at>? AND u.active=1''',
                             (token_hash(token), int(time.time()))).fetchone()
            if not row:
                return None
            return {'user': public_user(row), 'csrfToken': row['csrf_token'],
                    'state': self.state(db, row['id']), '_hash': row['session_hash']}

    def register(self, username, display_name, password):
        username, key = normalized_username(username)
        password = validate_password(password)
        display_name = validate_display_name(display_name if display_name is not None else username)
        salt = secrets.token_hex(16)
        digest = password_hash(password, salt)
        user_id, now = uuid.uuid4().hex, iso_now()
        try:
            with self.connect() as db:
                db.execute('BEGIN IMMEDIATE')
                # Public registration always creates an ordinary account.
                role = 'user'
                db.execute('INSERT INTO users VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)',
                           (user_id, username, key, display_name, salt, digest, PASSWORD_ITERATIONS, role, now, now))
                db.execute('INSERT INTO user_state VALUES (?, ?)', (user_id, json.dumps(DEFAULT_STATE)))
                if self.extension is not None:
                    self.extension.account_registered(db, user_id)
                token, csrf = self.new_session(db, user_id)
                user = public_user(db.execute('SELECT * FROM users WHERE id=?', (user_id,)).fetchone())
            return {'user': user, 'csrfToken': csrf, 'state': deepcopy(DEFAULT_STATE)}, token
        except sqlite3.IntegrityError as exc:
            raise APIError(409, 'username_taken', '该用户名已存在。') from exc

    def reserve_login_attempt(self, key, address):
        now = int(time.time())
        buckets = [('account:' + token_hash(key), LOGIN_LIMIT), ('address:' + token_hash(address), 40)]
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('DELETE FROM login_attempts WHERE window_start<=?', (now - LOGIN_WINDOW,))
            for bucket, limit in buckets:
                row = db.execute('SELECT * FROM login_attempts WHERE bucket=?', (bucket,)).fetchone()
                if row and row['attempts'] >= limit:
                    raise APIError(429, 'login_rate_limited', '尝试次数过多，请 5 分钟后重试。')
            for bucket, _ in buckets:
                db.execute('''INSERT INTO login_attempts VALUES (?, 1, ?)
                              ON CONFLICT(bucket) DO UPDATE SET attempts=attempts+1''', (bucket, now))

    def login(self, username, password, address):
        _, key = normalized_username(username)
        if not isinstance(password, str) or not 1 <= len(password) <= 128:
            raise APIError(400, 'invalid_credentials', '请填写有效的用户名和密码。')
        self.reserve_login_attempt(key, address)
        with self.connect() as db:
            row = db.execute('SELECT * FROM users WHERE username_key=?', (key,)).fetchone()
        # Hash even a missing username, avoiding a cheap account-existence timing path.
        expected = row['password_hash'] if row else '0' * 64
        actual = password_hash(password, row['salt'] if row else '0' * 32,
                               row['iterations'] if row else PASSWORD_ITERATIONS)
        if not hmac.compare_digest(actual, expected) or not row or not row['active']:
            raise APIError(401, 'invalid_credentials', '用户名或密码不正确，或账号已停用。')
        with self.connect() as db:
            # Recheck active in the same transaction that creates the session.
            db.execute('BEGIN IMMEDIATE')
            current = db.execute('SELECT * FROM users WHERE id=?', (row['id'],)).fetchone()
            if not current or not current['active'] or current['password_hash'] != row['password_hash']:
                raise APIError(401, 'invalid_credentials', '账号状态已变化，请重新登录。')
            db.execute('DELETE FROM login_attempts WHERE bucket=?', ('account:' + token_hash(key),))
            token, csrf = self.new_session(db, row['id'])
            result = {'user': public_user(current), 'csrfToken': csrf, 'state': self.state(db, row['id'])}
        return result, token

    def update_profile(self, user_id, name):
        name = validate_display_name(name)
        with self.connect() as db:
            db.execute('UPDATE users SET display_name=?, updated_at=? WHERE id=?', (name, iso_now(), user_id))
            return public_user(db.execute('SELECT * FROM users WHERE id=?', (user_id,)).fetchone())

    def change_password(self, user_id, current, replacement):
        replacement = validate_password(replacement)
        if not isinstance(current, str) or not 1 <= len(current) <= 128:
            raise APIError(400, 'invalid_password', '请填写当前密码。')
        with self.connect() as db:
            row = db.execute('SELECT * FROM users WHERE id=?', (user_id,)).fetchone()
        if not row:
            raise APIError(401, 'authentication_required', '请先登录。')
        if not hmac.compare_digest(password_hash(current, row['salt'], row['iterations']), row['password_hash']):
            raise APIError(401, 'wrong_password', '当前密码不正确。')
        salt = secrets.token_hex(16)
        digest = password_hash(replacement, salt)
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            # Prevent two concurrent password changes from authenticating against stale credentials.
            updated = db.execute('''UPDATE users SET salt=?, password_hash=?, iterations=?, updated_at=?
                                    WHERE id=? AND password_hash=?''',
                                 (salt, digest, PASSWORD_ITERATIONS, iso_now(), user_id, row['password_hash']))
            if updated.rowcount != 1:
                raise APIError(409, 'password_changed', '密码已在另一个会话修改，请重新登录。')
            db.execute('DELETE FROM sessions WHERE user_id=?', (user_id,))

            # Changing a password also revokes linked local chat access.
            # Standalone AccountStore clients may predate the optional bridge.
            if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='wechat_bindings'").fetchone():
                db.execute('DELETE FROM wechat_bindings WHERE user_id=?', (user_id,))

    def delete_account(self, user_id, current_password):
        if not isinstance(current_password, str) or not 1 <= len(current_password) <= 128:
            raise APIError(400, 'invalid_password', '请填写当前密码。')
        with self.connect() as db:
            row = db.execute('SELECT * FROM users WHERE id=?', (user_id,)).fetchone()
        if not row:
            raise APIError(401, 'authentication_required', '请先登录。')
        actual = password_hash(current_password, row['salt'], row['iterations'])
        if not hmac.compare_digest(actual, row['password_hash']):
            raise APIError(401, 'wrong_password', '当前密码不正确，账号未注销。')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            current = db.execute('SELECT * FROM users WHERE id=?', (user_id,)).fetchone()
            if not current or not current['active'] or current['password_hash'] != row['password_hash']:
                raise APIError(409, 'account_changed', '账号状态已变化，请重新登录后再操作。')
            db.execute('DELETE FROM sessions WHERE user_id=?', (user_id,))
            db.execute('DELETE FROM user_state WHERE user_id=?', (user_id,))
            db.execute('DELETE FROM login_attempts WHERE bucket=?', ('account:' + token_hash(current['username_key']),))
            db.execute('DELETE FROM users WHERE id=?', (user_id,))


    def save_state(self, user_id, body):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            state = validate_state_patch(body, self.state(db, user_id))
            db.execute('INSERT INTO user_state VALUES (?, ?) ON CONFLICT(user_id) DO UPDATE SET data=excluded.data',
                       (user_id, json.dumps(state, ensure_ascii=False)))
            return state

    def increment_relax(self, user_id, deltas):
        if not isinstance(deltas, dict) or not deltas or not set(deltas) <= set(DEFAULT_STATE['relax']):
            raise APIError(400, 'invalid_relax_delta', '请提供 woodfish、accepts 或 amen 的增量。')
        if any(type(value) is not int or value < 0 for value in deltas.values()) or sum(deltas.values()) > 1000:
            raise APIError(400, 'invalid_relax_delta', '解压增量须为非负整数，每次请求总增量不得超过 1000。')
        with self.connect() as db:
            # Serialize read/modify/write so simultaneous tabs cannot lose taps.
            db.execute('BEGIN IMMEDIATE')
            state = self.state(db, user_id)
            for key, delta in deltas.items():
                value = state['relax'][key] + delta
                if value > 1_000_000_000:
                    raise APIError(400, 'relax_limit', '该解压计数已达到上限。')
                state['relax'][key] = value
            db.execute('INSERT INTO user_state VALUES (?, ?) ON CONFLICT(user_id) DO UPDATE SET data=excluded.data',
                       (user_id, json.dumps(state, ensure_ascii=False)))
            return state['relax']

    @staticmethod
    def _community_stats(db):
        row = db.execute('SELECT woodfish_total, started_at, instance_id FROM community_totals WHERE id=1').fetchone()
        return {'woodfishTotal': row['woodfish_total'], 'startedAt': row['started_at'],
                'scope': 'instance', 'instanceId': row['instance_id']}

    def community_stats(self):
        with self.connect() as db:
            return self._community_stats(db)

    def increment_community_woodfish(self, body, address):
        """Add only a stream's new high-water delta; retries are idempotent.

        Streams are anonymous random client identifiers, not accounts or people.
        They survive account deletion solely as unlinked anti-duplicate totals.
        """
        if (not isinstance(body, dict) or set(body) != {'streamId', 'total', 'instanceId'}
                or not isinstance(body.get('streamId'), str)
                or not re.fullmatch(r'[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}', body['streamId'])
                or not isinstance(body.get('instanceId'), str)
                or not re.fullmatch(r'[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}', body['instanceId'])
                or type(body.get('total')) is not int or not 0 <= body['total'] <= 1_000_000_000):
            raise APIError(400, 'invalid_community_taps', '请提供有效的匿名计数标识与非负整数累计次数。')
        stream_id, total, now = body['streamId'], body['total'], int(time.time())
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            instance = db.execute('SELECT instance_id FROM community_totals WHERE id=1').fetchone()[0]
            if body['instanceId'] != instance:
                # The database can be replaced between the client's stats GET
                # and this POST. Never apply an old instance's queued taps here.
                raise APIError(409, 'community_instance_changed', '统计服务已更换，请刷新连接；旧服务的待同步敲击未写入当前服务。')
            row = db.execute('SELECT * FROM community_streams WHERE stream_id=?', (stream_id,)).fetchone()
            previous = row['total'] if row else 0
            delta = max(0, total - previous)
            if delta > 1000:
                raise APIError(400, 'community_batch_too_large', '每次同步的新增敲击不得超过 1000 次。')
            # Zero totals and old/repeated requests need no row creation or quota.
            if not delta:
                return {**self._community_stats(db), 'acceptedTotal': previous}
            window_start = row['window_start'] if row else now
            window_count = row['window_count'] if row else 0
            if now - window_start >= 60:
                window_start, window_count = now, 0
            if window_count + delta > COMMUNITY_TAPS_PER_MINUTE:
                raise APIError(429, 'community_rate_limited', '敲击同步过于频繁，请稍后自动重试。')
            if not row:
                salt = db.execute('SELECT address_salt FROM community_totals WHERE id=1').fetchone()[0]
                bucket = hmac.new(bytes.fromhex(salt), str(address).encode('utf-8'), hashlib.sha256).hexdigest()
                db.execute('DELETE FROM community_rate_limits WHERE window_start<=?', (now - 3600,))
                limit = db.execute('SELECT count FROM community_rate_limits WHERE bucket=?', (bucket,)).fetchone()
                if limit and limit['count'] >= COMMUNITY_STREAMS_PER_HOUR:
                    raise APIError(429, 'community_streams_limited', '新建计数会话过于频繁，请稍后重试。')
                db.execute('''INSERT INTO community_rate_limits VALUES (?, ?, 1)
                              ON CONFLICT(bucket) DO UPDATE SET count=count+1''', (bucket, now))
            current_total = db.execute('SELECT woodfish_total FROM community_totals WHERE id=1').fetchone()[0]
            if current_total + delta > 9_007_199_254_740_991:
                raise APIError(409, 'community_limit', '累计计数已达到安全整数上限。')
            db.execute('''INSERT INTO community_streams VALUES (?, ?, ?, ?)
                          ON CONFLICT(stream_id) DO UPDATE SET total=excluded.total,
                          window_start=excluded.window_start, window_count=excluded.window_count''',
                       (stream_id, total, window_start, window_count + delta))
            db.execute('UPDATE community_totals SET woodfish_total=woodfish_total+? WHERE id=1', (delta,))
            return {**self._community_stats(db), 'acceptedTotal': total}


    def sync_lists(self, user_id, body):
        """Merge explicit list changes against current state from all entry points."""
        if not body or not set(body) <= {'favorites', 'reminders'}:
            raise APIError(400, 'invalid_sync', '仅接受收藏和提醒的增量。')
        favorites = body.get('favorites', {'add': [], 'remove': []})
        reminders = body.get('reminders', {'upsert': [], 'remove': []})
        if (not isinstance(favorites, dict) or set(favorites) != {'add', 'remove'}
                or not isinstance(reminders, dict) or set(reminders) != {'upsert', 'remove'}):
            raise APIError(400, 'invalid_sync', '收藏或提醒增量字段无效。')
        add = validate_state_patch({'favorites': favorites['add']}, DEFAULT_STATE)['favorites']
        remove = validate_state_patch({'favorites': favorites['remove']}, DEFAULT_STATE)['favorites']
        upsert = validate_reminders(reminders['upsert'])
        remove_ids = reminders['remove']
        if (not isinstance(remove_ids, list) or len(remove_ids) > 200 or any(not isinstance(v, str)
                or not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_.:-]{0,159}', v) for v in remove_ids)):
            raise APIError(400, 'invalid_sync', '移除提醒 ID 无效。')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            state = self.state(db, user_id)
            new_favorites = list(dict.fromkeys([v for v in state['favorites'] if v not in remove] + add))
            merged = {r['id']: r for r in state['reminders'] if r['id'] not in remove_ids}
            merged.update({r['id']: r for r in upsert})
            values = [{**r, 'enabled': False} if r['conferenceId'] in remove else r for r in merged.values()]
            state = validate_state_patch({'favorites': new_favorites, 'reminders': values}, state)
            db.execute('INSERT INTO user_state VALUES (?,?) ON CONFLICT(user_id) DO UPDATE SET data=excluded.data',
                       (user_id, json.dumps(state, ensure_ascii=False)))
            return state




class ConferenceHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    # Multiple tabs may flush counts/settings together. The stdlib default
    # backlog of five can reject otherwise valid short bursts on loopback.
    request_queue_size = 32

    def __init__(self, address, root, database):
        if address[0] != '127.0.0.1':
            raise ValueError('This server must bind to 127.0.0.1 only.')
        self.root = Path(root).resolve()
        self.store = AccountStore(database, extension_root=self.root)
        self.wechat = WeChatService(self.store, self.root, validate_state_patch)
        super().__init__(address, ConferenceHandler)

    def serve_forever(self, poll_interval=0.5):
        self.wechat.start()
        return super().serve_forever(poll_interval)

    def server_close(self):
        self.wechat.stop()
        super().server_close()


class ConferenceHandler(BaseHTTPRequestHandler):
    server_version = 'ConfAtlasLocal/2'

    def log_message(self, format, *args):
        # Never log request bodies, credentials, cookies, or user information.
        pass

    def security_headers(self):
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('X-Frame-Options', 'DENY')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; media-src 'self' blob: data:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")

    def send_json(self, status, payload, cookie=None):
        content = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.security_headers()
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Length', str(len(content)))
        if cookie is not None:
            value = f'{COOKIE_NAME}={cookie}; Path=/; HttpOnly; SameSite=Strict; Max-Age={SESSION_SECONDS if cookie else 0}'
            self.send_header('Set-Cookie', value)
        if status == 429:
            self.send_header('Retry-After', str(LOGIN_WINDOW))
        self.end_headers()
        if self.command != 'HEAD':
            self.wfile.write(content)

    def check_request_origin(self):
        port = self.server.server_port
        allowed = {f'127.0.0.1:{port}', f'localhost:{port}'}
        host = self.headers.get('Host', '').lower()
        if host not in allowed:
            raise APIError(403, 'invalid_host', '仅允许通过本机回环地址访问。')
        origin = self.headers.get('Origin')
        if origin:
            parts = urlsplit(origin)
            if parts.scheme != 'http' or parts.netloc.lower() != host:
                raise APIError(403, 'cross_origin', '不允许跨站请求。')
        if self.headers.get('Sec-Fetch-Site') == 'cross-site':
            raise APIError(403, 'cross_origin', '不允许跨站请求。')

    def read_json(self):
        if self.headers.get('Content-Type', '').split(';', 1)[0].strip().lower() != 'application/json':
            raise APIError(415, 'json_required', '请求必须使用 application/json。')
        if self.headers.get('Transfer-Encoding'):
            raise APIError(400, 'unsupported_encoding', '不支持分块请求。')
        try:
            length = int(self.headers.get('Content-Length', '0'))
        except ValueError as exc:
            raise APIError(400, 'invalid_length', '请求长度无效。') from exc
        if length <= 0 or length > BODY_LIMIT:
            raise APIError(413, 'body_too_large', '请求数据为空或超过大小限制。')
        try:
            body = json.loads(self.rfile.read(length).decode('utf-8'))
        except (ValueError, UnicodeDecodeError, RecursionError) as exc:
            raise APIError(400, 'invalid_json', 'JSON 格式无效。') from exc
        if not isinstance(body, dict):
            raise APIError(400, 'invalid_json', '请求必须为 JSON 对象。')
        return body

    def current_session(self, required=False, csrf=False):
        authorization = self.headers.get('Authorization')
        if authorization is not None:
            # Native clients store their bearer token in the OS credential
            # vault. A malformed bearer header must not fall back to cookies.
            match = re.fullmatch(r'(?i:Bearer) ([A-Za-z0-9_-]{43})', authorization)
            token = match.group(1) if match else None
        else:
            cookie = SimpleCookie()
            try:
                cookie.load(self.headers.get('Cookie', ''))
                token = cookie[COOKIE_NAME].value if COOKIE_NAME in cookie else None
            except Exception:
                token = None
        session = self.server.store.session(token)
        if required and not session:
            raise APIError(401, 'authentication_required', '请先登录。')
        if csrf and session and not hmac.compare_digest(self.headers.get('X-CSRF-Token', '').encode('utf-8'), session['csrfToken'].encode('utf-8')):
            raise APIError(403, 'csrf_invalid', '会话校验失败，请刷新后重试。')
        return session

    def clean_session(self, session):
        result = {key: value for key, value in session.items() if not key.startswith('_')}
        if self.server.store.extension is not None:
            result = self.server.store.extension.decorate_session(result)
        return result

    def dispatch(self):
        try:
            self.check_request_origin()
            path = unquote(urlsplit(self.path).path)
            if not path.startswith('/api/'):
                return self.serve_static(path)
            extension = self.server.store.extension
            if extension is not None and extension.handle_request(self, path):
                return
            if self.command == 'GET' and path == '/api/session':
                session = self.current_session()
                return self.send_json(200, self.clean_session(session) if session else {'user': None, 'csrfToken': None, 'state': None}, cookie=None if session else '')
            if self.command == 'GET' and path == '/api/community/stats':
                return self.send_json(200, self.server.store.community_stats())
            if self.command == 'GET' and path == '/api/wechat/status':
                session = self.current_session(required=True)
                return self.send_json(200, self.server.wechat.status(session['user']['id']))
            if self.command not in {'POST', 'PUT', 'PATCH'}:
                raise APIError(404, 'not_found', '接口不存在。')
            body = self.read_json()
            if self.command == 'POST' and path == '/api/community/woodfish':
                return self.send_json(200, self.server.store.increment_community_woodfish(body, self.client_address[0]))
            if self.command == 'POST' and path in {
                '/api/auth/register', '/api/auth/login',
                '/api/mobile/auth/register', '/api/mobile/auth/login',
            }:
                if path.endswith('/register'):
                    result, token = self.server.store.register(body.get('username'), body.get('displayName'), body.get('password'))
                    status = 201
                else:
                    result, token = self.server.store.login(body.get('username'), body.get('password'), self.client_address[0])
                    status = 200
                # Replace and revoke the old session on this browser when switching accounts.
                previous = self.current_session()
                if previous:
                    with self.server.store.connect() as db:
                        db.execute('DELETE FROM sessions WHERE token_hash=?', (previous['_hash'],))
                if path.startswith('/api/mobile/auth/'):
                    # Only the explicitly native routes expose a token. The
                    # ordinary browser response keeps it HttpOnly-cookie-only.
                    return self.send_json(status, {**self.clean_session(result), 'sessionToken': token})
                return self.send_json(status, self.clean_session(result), cookie=token)
            supported = {'/api/auth/logout', '/api/profile', '/api/password', '/api/account/delete',
                         '/api/state', '/api/state/sync', '/api/relax/increment'}
            if path not in supported and not path.startswith('/api/wechat/'):
                raise APIError(404, 'not_found', '接口不存在。')
            session = self.current_session(required=True, csrf=True)
            user_id = session['user']['id']
            if path.startswith('/api/wechat/'):
                bridge = self.server.wechat
                if self.command == 'POST' and path == '/api/wechat/chat':
                    if set(body) != {'text'}:
                        raise APIError(400, 'invalid_chat', '只接受 text 字段。')
                    return self.send_json(200, bridge.chat(user_id, body['text']))
                if self.command == 'PATCH' and path == '/api/wechat/settings':
                    return self.send_json(200, bridge.settings(user_id, body))
                if self.command == 'POST' and path == '/api/wechat/login/poll':
                    if not set(body) <= {'verifyCode'}:
                        raise APIError(400, 'invalid_login_poll', '只接受 verifyCode 字段。')
                    return self.send_json(200, bridge.poll_login(user_id, body.get('verifyCode')))
                actions = {'/api/wechat/login': bridge.start_login,
                           '/api/wechat/login/cancel': bridge.cancel_login,
                           '/api/wechat/disconnect': bridge.disconnect}
                if self.command == 'POST' and path in actions:
                    if body:
                        raise APIError(400, 'invalid_wechat_action', '此操作不接受额外字段。')
                    return self.send_json(200, actions[path](user_id))
                raise APIError(404, 'not_found', '接口不存在。')
            if self.command == 'POST' and path == '/api/auth/logout':
                with self.server.store.connect() as db:
                    db.execute('DELETE FROM sessions WHERE token_hash=?', (session['_hash'],))
                return self.send_json(200, {'ok': True}, cookie='')
            if self.command == 'PATCH' and path == '/api/profile':
                if set(body) != {'displayName'}:
                    raise APIError(400, 'invalid_profile', '仅支持修改昵称 displayName。')
                user = self.server.store.update_profile(user_id, body.get('displayName'))
                return self.send_json(200, {'user': user})
            if self.command == 'POST' and path == '/api/password':
                self.server.store.change_password(user_id, body.get('currentPassword'), body.get('newPassword'))
                self.server.wechat.cancel_login(user_id)
                return self.send_json(200, {'ok': True, 'requiresLogin': True}, cookie='')
            if self.command == 'POST' and path == '/api/account/delete':
                if set(body) != {'currentPassword'}:
                    raise APIError(400, 'invalid_account_delete', '注销仅接受当前密码 currentPassword。')
                self.server.store.delete_account(user_id, body['currentPassword'])
                self.server.wechat.cancel_login(user_id)
                return self.send_json(200, {'ok': True, 'requiresLogin': True}, cookie='')
            if self.command == 'PUT' and path == '/api/state':
                return self.send_json(200, {'state': self.server.store.save_state(user_id, body)})
            if self.command == 'POST' and path == '/api/state/sync':
                return self.send_json(200, {'state': self.server.store.sync_lists(user_id, body)})
            if self.command == 'POST' and path == '/api/relax/increment':
                return self.send_json(200, {'relax': self.server.store.increment_relax(user_id, body)})
            raise APIError(404, 'not_found', '接口不存在。')
        except (APIError, WeChatError) as exc:
            self.send_json(exc.status, {'error': {'code': exc.code, 'message': exc.message}})
        except ILinkError as exc:
            self.send_json(502, {'error': {'code': exc.code, 'message': exc.message}})
        except (sqlite3.Error, OSError, ValueError, TypeError):
            self.send_json(500, {'error': {'code': 'server_error', 'message': '本地服务暂时无法处理请求。'}})

    def serve_static(self, path):
        if self.command not in {'GET', 'HEAD'}:
            raise APIError(405, 'method_not_allowed', '此资源只允许读取。')
        relative = STATIC_FILES.get(path)
        if not relative:
            raise APIError(404, 'not_found', '文件不存在。')
        file = self.server.root / relative
        if file.resolve() != file or not file.is_relative_to(self.server.root) or not file.is_file():
            raise APIError(404, 'not_found', '文件不存在。')
        content = file.read_bytes()
        self.send_response(200)
        self.security_headers()
        self.send_header('Content-Type', CONTENT_TYPES.get(file.suffix, 'application/octet-stream'))
        self.send_header('Cache-Control', 'no-cache')
        self.send_header('Content-Length', str(len(content)))
        self.end_headers()
        if self.command != 'HEAD':
            self.wfile.write(content)

    do_GET = dispatch
    do_HEAD = dispatch
    do_POST = dispatch
    do_PUT = dispatch
    do_PATCH = dispatch
    do_DELETE = dispatch
    do_OPTIONS = dispatch


def make_server(root, database=None, port=8765):
    root = Path(root).resolve()
    return ConferenceHTTPServer(('127.0.0.1', port), root, database or root / '.local' / 'app.sqlite3')


if __name__ == '__main__':
    print('Start the local web application with: python3 serve.py')
