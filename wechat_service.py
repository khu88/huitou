"""Account-scoped WeChat bridge. No network activity until an explicit QR login.

The transport is injectable; tests use fake peers and temporary SQLite databases.
The durable journal prevents automatic resends after an uncertain network result.
"""
from __future__ import annotations

import hashlib
import json
import secrets
import sqlite3
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from wechat_commands import execute, invitation_notice, reminder_due, reminder_problem
from wechat_transport import ILinkClient, ILinkError


class WeChatError(Exception):
    def __init__(self, status, code, message):
        self.status, self.code, self.message = status, code, message
        super().__init__(message)


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


class WeChatService:
    def __init__(self, store, root, validate_patch, client_factory=ILinkClient, clock=time.time):
        self.store, self.root, self.validate_patch = store, Path(root), validate_patch
        self.client_factory, self.clock = client_factory, clock
        self.owner = secrets.token_hex(16)
        self.logins, self.locks, self.workers = {}, {}, {}
        self.guard = threading.RLock()
        self.closed = threading.Event()
        self.thread = None
        self.scheduler = None
        self.last_tick = clock()
        with store.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS wechat_bindings (
                    user_id TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
                    generation TEXT NOT NULL UNIQUE, bot_id TEXT NOT NULL UNIQUE,
                    peer_id TEXT NOT NULL UNIQUE, token TEXT NOT NULL, base_url TEXT NOT NULL,
                    cursor TEXT NOT NULL DEFAULT '', context TEXT NOT NULL DEFAULT '',
                    enabled INTEGER NOT NULL DEFAULT 1, push_enabled INTEGER NOT NULL DEFAULT 0,
                    connected_at REAL NOT NULL, push_since REAL NOT NULL DEFAULT 0,
                    last_seen REAL, last_error TEXT NOT NULL DEFAULT '',
                    worker_owner TEXT NOT NULL DEFAULT '', worker_until REAL NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS wechat_inbox (
                    generation TEXT NOT NULL REFERENCES wechat_bindings(generation) ON DELETE CASCADE,
                    message_key TEXT NOT NULL, created_at REAL NOT NULL,
                    PRIMARY KEY(generation, message_key)
                );
                CREATE TABLE IF NOT EXISTS wechat_deliveries (
                    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    delivery_key TEXT NOT NULL PRIMARY KEY, kind TEXT NOT NULL,
                    status TEXT NOT NULL, detail TEXT NOT NULL, created_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS wechat_commands (
                    generation TEXT NOT NULL REFERENCES wechat_bindings(generation) ON DELETE CASCADE,
                    message_key TEXT NOT NULL, command_text TEXT NOT NULL, reply_text TEXT NOT NULL DEFAULT '',
                    state TEXT NOT NULL DEFAULT 'queued', received_at REAL NOT NULL,
                    message_at REAL NOT NULL, prepared_at REAL,
                    PRIMARY KEY(generation, message_key)
                );
            ''')

    def lock(self, user_id):
        with self.guard:
            return self.locks.setdefault(user_id, threading.RLock())

    def catalog(self):
        try:
            value = json.loads((self.root / 'data' / 'conferences.json').read_text())
            if not isinstance(value.get('conferences'), list):
                raise ValueError()
            return value
        except (OSError, ValueError, TypeError):
            raise WeChatError(503, 'catalog_unavailable', '会议目录暂不可用，请检查本地数据文件。')

    @staticmethod
    def active(db, user_id):
        return db.execute('SELECT id FROM users WHERE id=? AND active=1', (user_id,)).fetchone() is not None

    def binding(self, user_id):
        with self.store.connect() as db:
            row = db.execute('SELECT b.* FROM wechat_bindings b JOIN users u ON b.user_id=u.id '
                             'WHERE b.user_id=? AND u.active=1', (user_id,)).fetchone()
            return dict(row) if row else None

    def status(self, user_id):
        binding = self.binding(user_id)
        with self.lock(user_id):
            login = self.logins.get(user_id)
            if login and login['expiresAt'] <= self.clock():
                self.logins.pop(user_id, None)
                login = None
            public_login = {key: login[key] for key in ('status', 'expiresAt', 'qrUrl', 'qrSvg')} if login else None
        with self.store.connect() as db:
            deliveries = [dict(row) for row in db.execute(
                'SELECT kind,status,detail,created_at AS createdAt FROM wechat_deliveries '
                'WHERE user_id=? ORDER BY created_at DESC LIMIT 20', (user_id,))]
            pending = db.execute('SELECT COUNT(*) FROM wechat_commands c JOIN wechat_bindings b '
                                 'ON b.generation=c.generation WHERE b.user_id=? AND c.state IN (?,?)',
                                 (user_id, 'queued', 'prepared')).fetchone()[0]
        return {
            'binding': ({'enabled': bool(binding['enabled']), 'pushEnabled': bool(binding['push_enabled']),
                         'connectedAt': binding['connected_at'], 'lastSeen': binding['last_seen'],
                         'lastError': binding['last_error'], 'contextReady': bool(binding['context'])} if binding else None),
            'login': public_login, 'deliveries': deliveries, 'pendingCommands': pending,
        }

    def start_login(self, user_id):
        with self.lock(user_id):
            if self.binding(user_id):
                raise WeChatError(409, 'already_bound', '此账号已绑定；更换微信前请先解除绑定。')
            previous = self.logins.get(user_id)
            if previous and previous['expiresAt'] > self.clock():
                return self.status(user_id)
            client = self.client_factory()
            result = client.request_qr()
            url = result.get('qrcode_url', '')
            svg = ''
            if url:
                from qr_svg import data_uri
                try:
                    svg = data_uri(url)
                except ValueError:
                    pass  # A valid provider link remains available for long payloads.
            self.logins[user_id] = {'client': client, 'qrcode': result['qrcode'], 'qrUrl': url,
                                   'qrSvg': svg, 'status': 'wait', 'expiresAt': self.clock() + 300}
        return self.status(user_id)

    def poll_login(self, user_id, verify_code=None):
        if verify_code is not None and (not isinstance(verify_code, str) or not verify_code.isascii()
                                        or not verify_code.isdigit() or not 4 <= len(verify_code) <= 12):
            raise WeChatError(400, 'invalid_verify_code', '请输入手机显示的数字验证码。')
        with self.lock(user_id):
            login = self.logins.get(user_id)
            if not login or login['expiresAt'] <= self.clock():
                self.logins.pop(user_id, None)
                raise WeChatError(410, 'qr_expired', '二维码已过期，请重新获取。')
            result = login['client'].poll_qr(login['qrcode'], verify_code=verify_code)
            login['status'] = result['status']
            if result['status'] == 'confirmed':
                try:
                    with self.store.connect() as db:
                        db.execute('BEGIN IMMEDIATE')
                        if not self.active(db, user_id):
                            raise WeChatError(401, 'authentication_required', '请重新登录后绑定。')
                        db.execute('''INSERT INTO wechat_bindings
                            (user_id,generation,bot_id,peer_id,token,base_url,connected_at)
                            VALUES (?,?,?,?,?,?,?)''', (user_id, secrets.token_hex(16), result['ilink_bot_id'],
                            result['ilink_user_id'], result['bot_token'], result['baseurl'], self.clock()))
                except sqlite3.IntegrityError:
                    self.logins.pop(user_id, None)
                    raise WeChatError(409, 'wechat_already_bound', '此微信或助手已绑定另一个本地账号，请先在原账号解除绑定。')
                self.logins.pop(user_id, None)
            elif result['status'] in ('expired', 'verify_code_blocked', 'binded_redirect'):
                login['expiresAt'] = min(login['expiresAt'], self.clock() + 10)
        return self.status(user_id)

    def cancel_login(self, user_id):
        with self.lock(user_id):
            self.logins.pop(user_id, None)
        return self.status(user_id)

    def disconnect(self, user_id):
        with self.lock(user_id):
            self.logins.pop(user_id, None)
            with self.store.connect() as db:
                db.execute('DELETE FROM wechat_bindings WHERE user_id=?', (user_id,))
        return self.status(user_id)

    def settings(self, user_id, body):
        if not body or not set(body) <= {'enabled', 'pushEnabled'} or any(type(v) is not bool for v in body.values()):
            raise WeChatError(400, 'invalid_wechat_settings', '只接受 enabled / pushEnabled 布尔值。')
        with self.lock(user_id), self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT * FROM wechat_bindings WHERE user_id=?', (user_id,)).fetchone()
            if not row:
                raise WeChatError(409, 'wechat_not_bound', '请先扫码绑定微信。')
            if 'enabled' in body:
                db.execute('UPDATE wechat_bindings SET enabled=? WHERE user_id=?', (int(body['enabled']), user_id))
            if 'pushEnabled' in body:
                db.execute('UPDATE wechat_bindings SET push_enabled=?,push_since=? WHERE user_id=?',
                           (int(body['pushEnabled']), self.clock() if body['pushEnabled'] else 0, user_id))
        return self.status(user_id)

    def chat(self, user_id, text):
        if not isinstance(text, str) or not text.strip() or len(text) > 2000:
            raise WeChatError(400, 'invalid_chat', '请输入 1–2000 个字符。')
        catalog = self.catalog()
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if not self.active(db, user_id):
                raise WeChatError(401, 'authentication_required', '请先登录。')
            result, state = self._execute(db, user_id, text, catalog)
        return {'text': result['text'], 'state': state, 'preview': True}

    def _execute(self, db, user_id, text, catalog):
        state = self.store.state(db, user_id)
        result = execute(text, catalog, state, now=datetime.fromtimestamp(self.clock(), timezone.utc))
        if result['patch']:
            state = self.validate_patch(result['patch'], state)
            db.execute('INSERT INTO user_state VALUES (?,?) ON CONFLICT(user_id) DO UPDATE SET data=excluded.data',
                       (user_id, json.dumps(state, ensure_ascii=False)))
        return result, state

    def _error(self, user_id, generation, message, disable=False):
        with self.store.connect() as db:
            db.execute('UPDATE wechat_bindings SET last_error=?,enabled=CASE WHEN ? THEN 0 ELSE enabled END '
                       'WHERE user_id=? AND generation=?', (message, int(disable), user_id, generation))

    def _live(self, row, previous):
        return row and row['generation'] == previous['generation'] and row['enabled'] and not self.closed.is_set()

    def _owned(self, row):
        return row and row['worker_owner'] == self.owner and row['worker_until'] > self.clock()

    def receive(self, previous, message, *, process=True):
        """Durably receive an authorized command before advancing its cursor.

        Processing may be delayed across a restart; received text stays private
        in SQLite until the reply has a terminal outcome. Existing inbox rows
        from older versions remain deduplicated and are never re-executed.
        False means access changed before receipt: the caller must retain its
        cursor. Ignored or already-received provider messages return None.
        """
        if not isinstance(message, dict) or message.get('from_user_id') != previous['peer_id']:
            return
        # Tencent's ingress does not require these optional fields. Refuse
        # explicit bot/partial messages, but allow NEW and absent final state.
        if (message.get('group_id') or message.get('message_type') not in (None, 1)
                or message.get('message_state') not in (None, 0, 2)):
            return
        created = message.get('create_time_ms')
        if created is not None and (type(created) not in (int, float)
                                   or not previous['connected_at'] - 5 <= created / 1000 <= self.clock() + 300):
            return
        context = message.get('context_token')
        if (not isinstance(context, str) or not context or len(context) > 8192
                or any(ord(c) < 32 or ord(c) == 127 for c in context)):
            return
        items = message.get('item_list', [])
        if not isinstance(items, list):
            return
        if any(isinstance(item, dict) and item.get('is_completed') is False for item in items):
            return
        identity = message.get('message_id') or next((item.get('msg_id') for item in items
                    if isinstance(item, dict) and item.get('msg_id')), None)
        if created is None and not identity:
            return
        texts = [item.get('text_item', {}).get('text', '') for item in items
                 if isinstance(item, dict) and item.get('type') == 1 and isinstance(item.get('text_item'), dict)]
        text = '\n'.join(t for t in texts if isinstance(t, str)).strip()
        # Unsupported media gets a useful reply, without processing any files.
        text = text if 0 < len(text) <= 2000 else '帮助'
        # Exclude mutable update/context metadata from fallback identity.
        identity = str(identity or json.dumps([message['from_user_id'], created, text], ensure_ascii=False))
        key = digest(identity)
        user_id = previous['user_id']
        with self.lock(user_id):
            live = self.binding(user_id)
            if not self._live(live, previous) or not self._owned(live):
                return False
            with self.store.connect() as db:
                db.execute('BEGIN IMMEDIATE')
                if not self.active(db, user_id):
                    return False
                row = db.execute('SELECT * FROM wechat_bindings WHERE user_id=?', (user_id,)).fetchone()
                if not self._live(row, previous) or not self._owned(row):
                    return False
                existing = db.execute('SELECT 1 FROM wechat_inbox WHERE generation=? AND message_key=?',
                                      (previous['generation'], key)).fetchone()
                if existing:
                    return
                if db.execute('SELECT COUNT(*) FROM wechat_inbox WHERE generation=? AND created_at>?',
                              (previous['generation'], self.clock() - 60)).fetchone()[0] >= 30:
                    # Do not advance the provider cursor past a deferred command.
                    raise WeChatError(429, 'wechat_busy', '微信指令较多，稍后继续处理。')
                if db.execute('SELECT COUNT(*) FROM wechat_commands WHERE generation=? '
                              'AND state IN (?,?)', (previous['generation'], 'queued', 'prepared')).fetchone()[0] >= 100:
                    raise WeChatError(429, 'wechat_queue_full', '待处理指令较多，完成后继续接收。')
                db.execute('INSERT INTO wechat_inbox VALUES (?,?,?)',
                           (previous['generation'], key, self.clock()))
                db.execute('''INSERT INTO wechat_commands
                              (generation,message_key,command_text,received_at,message_at)
                              VALUES (?,?,?,?,?)''', (previous['generation'], key, text,
                              self.clock(), created / 1000 if created is not None else self.clock()))
                db.execute('UPDATE wechat_bindings SET context=?,last_seen=?,last_error=? WHERE user_id=?',
                           (context, self.clock(), '', user_id))
            if process:
                self.recover_commands(previous)

    def recover_commands(self, previous, limit=30):
        """Continue received/prepared work; never repeat an uncertain send.

        State mutations and the response body are committed together. A crash
        after that transaction resumes the stored response, not the mutation.
        The outbound claim still precedes the network call, so a crash in that
        interval is intentionally treated as uncertain and never auto-retried.
        """
        user_id = previous['user_id']
        with self.lock(user_id):
            live = self.binding(user_id)
            if not self._live(live, previous) or not self._owned(live):
                return
            with self.store.connect() as db:
                pending = [dict(row) for row in db.execute(
                    'SELECT * FROM wechat_commands WHERE generation=? AND state IN (?,?) '
                    'ORDER BY received_at,rowid LIMIT ?', (live['generation'], 'queued', 'prepared', limit))]
            for command in pending:
                with self.store.connect() as db:
                    db.execute('BEGIN IMMEDIATE')
                    current = db.execute('SELECT * FROM wechat_bindings WHERE user_id=?', (user_id,)).fetchone()
                    if not self.active(db, user_id) or not self._live(current, live) or not self._owned(current):
                        return
                    row = db.execute('SELECT * FROM wechat_commands WHERE generation=? AND message_key=?',
                                     (live['generation'], command['message_key'])).fetchone()
                    if not row or row['state'] not in ('queued', 'prepared'):
                        continue
                    command = dict(row)
                    if command['state'] == 'queued':
                        state = self.store.state(db, user_id)
                        result = execute(command['command_text'], self.catalog(), state,
                                         now=datetime.fromtimestamp(self.clock(), timezone.utc))
                        # A delayed user mutation must not silently change a newer
                        # account state days later. Queries may still be answered.
                        stale = self.clock() - min(command['received_at'], command['message_at']) > 86400
                        if result['patch'] and stale:
                            reply = ('上次未完成的指令已超过24小时，本次未执行其中的收藏或提醒修改。'
                                     '请重新发送该指令，确认现在仍需要此操作。')
                        else:
                            if result['patch']:
                                state = self.validate_patch(result['patch'], state)
                                db.execute('INSERT INTO user_state VALUES (?,?) ON CONFLICT(user_id) '
                                           'DO UPDATE SET data=excluded.data',
                                           (user_id, json.dumps(state, ensure_ascii=False)))
                            reply = result['text']
                        command.update(reply_text=reply, state='prepared', prepared_at=self.clock())
                        db.execute("UPDATE wechat_commands SET reply_text=?,state='prepared',prepared_at=? "
                                   'WHERE generation=? AND message_key=?', (reply, self.clock(),
                                   live['generation'], command['message_key']))
                reply = command['reply_text']
                if self.clock() - command['prepared_at'] > 120:
                    prepared = datetime.fromtimestamp(command['prepared_at'], timezone.utc).isoformat(timespec='seconds')
                    reply = f'补回上次处理结果（生成于 {prepared}；当前日期请重新查询）：\n{reply}'
                key = 'chat:' + live['generation'] + ':' + command['message_key']
                outcome = self._send(live, key, 'reply', reply, '会话查询回复')
                if outcome is None:
                    return
                with self.store.connect() as db:
                    # Clear sensitive command/reply bodies after terminal status.
                    db.execute("UPDATE wechat_commands SET state=?,command_text='',reply_text='' "
                               'WHERE generation=? AND message_key=?', (outcome, live['generation'], command['message_key']))

    def _send(self, binding, key, kind, text, detail):
        """Reserve before sending. Unknown outcomes never cause automatic retries."""
        user_id = binding['user_id']
        with self.lock(user_id):
            with self.store.connect() as db:
                db.execute('BEGIN IMMEDIATE')
                row = db.execute('SELECT * FROM wechat_bindings WHERE user_id=?', (user_id,)).fetchone()
                if (not self.active(db, user_id) or not self._live(row, binding) or not self._owned(row)
                        or (kind == 'ddl' and not row['push_enabled'])):
                    return
                live = dict(row)
                fresh = db.execute('INSERT OR IGNORE INTO wechat_deliveries VALUES (?,?,?,?,?,?)',
                    (user_id, key, kind, 'sending', detail, self.clock())).rowcount
            if not fresh:
                with self.store.connect() as db:
                    row = db.execute('SELECT status FROM wechat_deliveries WHERE delivery_key=?', (key,)).fetchone()
                    if row and row['status'] == 'sending':
                        db.execute("UPDATE wechat_deliveries SET status='uncertain',detail=? WHERE delivery_key=?",
                                   ('上次发送在中断时结果未知，未自动重发。', key))
                        return 'uncertain'
                    return row['status'] if row else None
            status, message = 'accepted', detail
            try:
                client = self.client_factory(base_url=live['base_url'], token=live['token'])
                client.send_text(live['peer_id'], live['context'], text, 'ca-' + digest(key)[:40])
            except ILinkError as error:
                status = 'uncertain' if error.retryable or error.code in ('send_unconfirmed', 'invalid_response') else 'failed'
                message = error.message
                self._error(user_id, live['generation'], message, disable=error.session_invalid)
            except Exception:
                status, message = 'uncertain', '发送结果未知，未自动重试。可在微信发送“我的提醒”核对。'
                self._error(user_id, live['generation'], message)
            with self.store.connect() as db:
                db.execute('UPDATE wechat_deliveries SET status=?,detail=? WHERE delivery_key=?', (status, message, key))
            return status

    def deliver_due(self, now=None):
        now = self.clock() if now is None else now
        lower = max(self.last_tick, now - 120)
        self.last_tick = now
        catalog = self.catalog()
        conferences = {c['id']: c for c in catalog['conferences']}
        with self.store.connect() as db:
            bindings = [dict(row) for row in db.execute('SELECT b.* FROM wechat_bindings b JOIN users u ON u.id=b.user_id '
                       'WHERE b.enabled=1 AND b.push_enabled=1 AND u.active=1 AND b.worker_owner=?', (self.owner,))]
        for previous in bindings:
            user_id = previous['user_id']
            with self.lock(user_id):
                live = self.binding(user_id)
                if not self._live(live, previous) or not self._owned(live) or not live['push_enabled']:
                    continue
                with self.store.connect() as db:
                    state = self.store.state(db, user_id)
                for reminder in state['reminders']:
                    due = reminder_due(reminder)
                    if not reminder.get('enabled') or reminder.get('conferenceId') not in state['favorites'] or not due:
                        continue
                    if not max(lower, live['connected_at'], live['push_since']) < due.timestamp() <= now:
                        continue
                    key = 'ddl:' + live['generation'] + ':' + digest(json.dumps([
                        reminder['id'], reminder['deadline'], reminder['leadMinutes']], ensure_ascii=False))
                    problem = reminder_problem(reminder, catalog)
                    if problem:
                        with self.store.connect() as db:
                            db.execute('INSERT OR IGNORE INTO wechat_deliveries VALUES (?,?,?,?,?,?)',
                                       (user_id, key, 'ddl', 'skipped', problem, now))
                        continue
                    conf = conferences[reminder['conferenceId']]
                    kind = '摘要' if reminder['kind'] == 'abstract' else '全文'
                    track = next(t for t in conf['detail']['tracks'] if t['name'] == reminder['trackName'])
                    notice = invitation_notice(track)
                    title = f"{conf['acronym']} · {reminder['trackName']} · {kind}截止" + (' · 仅限获邀' if notice else '')
                    text = (f"会投 DDL 提醒\n{title}\n" + (notice + '\n' if notice else '') +
                            f"截止：{reminder['deadline']}（来源时区）\n"
                            f"提前 {reminder['leadMinutes']} 分钟\n"
                            f"投稿：{track.get('submissionUrl') or conf.get('officialUrl') or '待补充'}\n"
                            f"目录快照：{catalog.get('asOf', '未知')}；提交前请复核官方日期。\n"
                            '发送“我的提醒”查看设置；“暂停全部提醒”停止所有截止提醒。')
                    self._send(live, key, 'ddl', text, title)

    def _claim(self):
        now = self.clock()
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('UPDATE wechat_bindings SET worker_owner=?,worker_until=? WHERE enabled=1 '
                       'AND (worker_owner=? OR worker_until<?) AND user_id IN (SELECT id FROM users WHERE active=1)',
                       (self.owner, now + 90, self.owner, now))
            return [dict(row) for row in db.execute('SELECT b.* FROM wechat_bindings b JOIN users u ON u.id=b.user_id '
                        'WHERE b.worker_owner=? AND b.enabled=1 AND u.active=1', (self.owner,))]

    def _poll(self, initial):
        user_id, generation = initial['user_id'], initial['generation']
        backoff = 1
        while not self.closed.is_set():
            live = self.binding(user_id)
            if not self._live(live, initial) or not self._owned(live):
                return
            try:
                self.recover_commands(live)
                # Recovery can discover an invalid session and pause binding.
                # Recheck before starting another provider request.
                live = self.binding(user_id)
                if not self._live(live, initial) or not self._owned(live):
                    return
                client = self.client_factory(base_url=live['base_url'], token=live['token'])
                result = client.get_updates(live['cursor'])
                for message in result.get('msgs', []):
                    if self.closed.is_set():
                        return
                    if self.receive(live, message, process=False) is False:
                        return  # A valid command was deferred; retain the cursor.
                cursor = result.get('get_updates_buf')
                if isinstance(cursor, str) and cursor and len(cursor) <= 65536:
                    with self.lock(user_id), self.store.connect() as db:
                        db.execute('BEGIN IMMEDIATE')
                        current = db.execute('SELECT * FROM wechat_bindings WHERE user_id=?', (user_id,)).fetchone()
                        if (not self.active(db, user_id) or not self._live(current, initial)
                                or not self._owned(current) or current['cursor'] != live['cursor']):
                            return
                        db.execute('UPDATE wechat_bindings SET cursor=? WHERE user_id=? AND generation=? AND worker_owner=?',
                                   (cursor, user_id, generation, self.owner))
                self.recover_commands(live)
                backoff = 1
            except ILinkError as error:
                self._error(user_id, generation, error.message, disable=error.session_invalid)
                if error.session_invalid:
                    return
                backoff = min(backoff * 2, 60)
            except Exception:
                try:
                    self._error(user_id, generation, '微信处理暂时失败，正在退避重连。')
                except sqlite3.Error:
                    return
                backoff = min(backoff * 2, 60)
            self.closed.wait(backoff)

    def _run(self):
        while not self.closed.is_set():
            try:
                for user_id in list(self.logins):
                    lock = self.lock(user_id)
                    if not lock.acquire(blocking=False):
                        continue
                    try:
                        pending = self.logins.get(user_id)
                        if pending and pending['expiresAt'] <= self.clock():
                            self.logins.pop(user_id, None)
                    finally:
                        lock.release()
                for binding in self._claim():
                    user_id = binding['user_id']
                    old = self.workers.get(user_id)
                    if not old or not old.is_alive():
                        thread = threading.Thread(target=self._poll, args=(binding,), daemon=True)
                        self.workers[user_id] = thread
                        thread.start()
            except (WeChatError, sqlite3.Error, OSError):
                pass  # No credentials, queries or peer identities in process logs.
            self.closed.wait(2)

    def _schedule(self):
        while not self.closed.is_set():
            try:
                self.deliver_due()
            except (WeChatError, sqlite3.Error, OSError):
                pass
            self.closed.wait(2)

    def start(self):
        if not self.thread:
            self.last_tick = self.clock()
            self.thread = threading.Thread(target=self._run, daemon=True)
            self.scheduler = threading.Thread(target=self._schedule, daemon=True)
            self.thread.start()
            self.scheduler.start()

    def stop(self):
        self.closed.set()
        if self.thread:
            self.thread.join(timeout=3)
        if self.scheduler:
            self.scheduler.join(timeout=3)
        with self.store.connect() as db:
            db.execute("UPDATE wechat_bindings SET worker_owner='',worker_until=0 WHERE worker_owner=?", (self.owner,))
