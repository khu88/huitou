"""Bridge integration tests: isolated accounts, fake provider and controlled time."""
import json
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from server import make_server
from wechat_service import WeChatError
from wechat_transport import ILinkError
from test_server import Client

ROOT = Path(__file__).resolve().parents[1]


class FakeProvider:
    def __init__(self):
        self.sent, self.requests = [], []
        self.peer = 'scanner-one'
        self.bot = 'test-bot'
        self.failure = None
        self.qr_status = 'confirmed'
        self.updates = []

    def __call__(self, **kwargs):
        return self

    def request_qr(self):
        self.requests.append('qr')
        return {'qrcode': 'private-qr-challenge', 'qrcode_url': 'https://weixin.qq.com/test-qr'}

    def poll_qr(self, qrcode, verify_code=None):
        self.requests.append('poll')
        return {'status': self.qr_status, 'bot_token': 'SECRET-FAKE-TOKEN', 'ilink_bot_id': self.bot,
                'ilink_user_id': self.peer, 'baseurl': 'https://ilinkai.weixin.qq.com'}

    def send_text(self, peer, context, text, client_id):
        if not context:
            raise ILinkError('missing_context', '请先在微信发送消息。')
        self.sent.append({'peer': peer, 'context': context, 'text': text, 'client_id': client_id})
        if self.failure:
            raise self.failure
        return {'ret': 0}

    def get_updates(self, cursor=''):
        messages, self.updates = self.updates, []
        return {'ret': 0, 'msgs': messages, 'get_updates_buf': 'fake-cursor'}


class WeChatServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='conf-atlas-wechat-test-')
        self.root = Path(self.temp.name)
        (self.root / 'data').mkdir()
        self.catalog = json.loads((ROOT / 'data/conferences.json').read_text())
        self.write_catalog()
        self.server = make_server(self.root, self.root / '.local/test.sqlite3', port=0)
        self.bridge = self.server.wechat
        self.now = datetime(2026, 10, 28, 12, tzinfo=timezone.utc).timestamp()
        self.bridge.clock = lambda: self.now
        self.bridge.last_tick = self.now
        self.provider = FakeProvider()
        self.bridge.client_factory = self.provider
        self.bridge.start = lambda: None  # All clock/network work is explicitly driven below.
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.client = Client(self.server)
        status, payload, _ = self.client.register()
        self.assertEqual(status, 201)
        self.user = payload['user']['id']

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(5)
        self.temp.cleanup()

    def write_catalog(self):
        (self.root / 'data/conferences.json').write_text(json.dumps(self.catalog))

    def bind(self):
        self.assertEqual(self.client.request('POST', '/api/wechat/login', {})[0], 200)
        result = self.client.request('POST', '/api/wechat/login/poll', {})
        self.assertEqual(result[0], 200)
        self.bridge._claim()
        return self.bridge.binding(self.user)

    def message(self, text='收藏 AAAI', **overrides):
        return dict({'from_user_id': self.provider.peer, 'message_type': 1, 'message_state': 2,
                     'create_time_ms': self.now * 1000, 'message_id': 1, 'context_token': 'private-context',
                     'item_list': [{'type': 1, 'text_item': {'text': text}}]}, **overrides)

    def state(self):
        return self.client.request('GET', '/api/session')[1]['state']

    def due_reminder(self, delta=60, context=True):
        self.bind()
        due = self.now + delta
        deadline = datetime.fromtimestamp(due + 3600, timezone.utc).isoformat()
        conf = next(c for c in self.catalog['conferences'] if c['id'] == 'cvpr')
        conf['detail']['tracks'][0]['fullDeadline'] = deadline
        self.write_catalog()
        reminder = {'id': 'test-reminder', 'conferenceId': 'cvpr', 'trackName': conf['detail']['tracks'][0]['name'],
                    'kind': 'full', 'deadline': deadline, 'leadMinutes': 60, 'enabled': True}
        self.server.store.save_state(self.user, {'favorites': ['cvpr'], 'reminders': [reminder]})
        self.bridge.settings(self.user, {'pushEnabled': True})
        if context:
            with self.server.store.connect() as db:
                db.execute('UPDATE wechat_bindings SET context=? WHERE user_id=?', ('private-context', self.user))
        return reminder

    def test_routes_require_login_csrf_and_explicit_network_action(self):
        guest = Client(self.server)
        self.assertEqual(guest.request('GET', '/api/wechat/status')[0], 401)
        self.assertEqual(self.client.request('GET', '/api/wechat/status')[0], 200)
        self.assertEqual(self.provider.requests, [])
        self.assertEqual(self.client.request('POST', '/api/wechat/login', {}, use_csrf=False)[0], 403)
        self.assertEqual(self.client.request('POST', '/api/wechat/login', {'anything': True})[0], 400)
        self.assertEqual(self.provider.requests, [])
        self.assertEqual(self.client.request('GET', '/wechat_service.py')[0], 404)
        self.assertEqual(self.client.request('GET', '/.local/test.sqlite3')[0], 404)

    def test_qr_status_safe_and_bound_push_opt_in(self):
        status, payload, _ = self.client.request('POST', '/api/wechat/login', {})
        self.assertEqual(status, 200)
        self.assertTrue(payload['login']['qrSvg'].startswith('data:image/svg+xml;base64,'))
        self.assertNotIn('private-qr-challenge', json.dumps(payload))
        self.assertEqual(self.client.request('POST', '/api/wechat/login', {})[0], 200)
        self.assertEqual(self.provider.requests.count('qr'), 1)
        payload = self.client.request('POST', '/api/wechat/login/poll', {})[1]
        self.assertTrue(payload['binding']['enabled'])
        self.assertFalse(payload['binding']['pushEnabled'])
        self.assertFalse(payload['binding']['contextReady'])
        self.assertNotIn('SECRET', json.dumps(payload))
        self.assertNotIn('scanner-one', json.dumps(payload))
        self.assertEqual(self.provider.sent, [])

    def test_qr_expiry_and_cancel_do_not_bind(self):
        self.bridge.start_login(self.user)
        self.now += 301
        self.assertEqual(self.client.request('POST', '/api/wechat/login/poll', {})[0], 410)
        self.assertIsNone(self.bridge.binding(self.user))
        self.bridge.start_login(self.user)
        self.bridge.cancel_login(self.user)
        self.assertIsNone(self.bridge.status(self.user)['login'])

    def test_preview_mutates_only_current_account_without_network(self):
        other = Client(self.server)
        self.assertEqual(other.register('second')[0], 201)
        result = self.client.request('POST', '/api/wechat/chat', {'text': '收藏 AAAI'})
        self.assertEqual(result[0], 200)
        self.assertTrue(result[1]['preview'])
        self.assertIn('aaai', result[1]['state']['favorites'])
        self.assertEqual(other.request('GET', '/api/session')[1]['state']['favorites'], [])
        self.assertEqual(self.provider.requests, [])
        self.assertEqual(self.provider.sent, [])
        self.assertEqual(self.client.request('POST', '/api/wechat/chat', {'text': 'CVPR 截止'}, use_csrf=False)[0], 403)

    def test_same_wechat_cannot_bind_two_accounts(self):
        self.bind()
        other = Client(self.server)
        other.register('second')
        self.assertEqual(other.request('POST', '/api/wechat/login', {})[0], 200)
        self.assertEqual(other.request('POST', '/api/wechat/login/poll', {})[0], 409)
        self.assertIsNone(other.request('GET', '/api/wechat/status')[1]['binding'])

    def test_foreign_group_bot_historical_and_missing_context_messages_ignored(self):
        binding = self.bind()
        for change in ({'from_user_id': 'stranger'}, {'group_id': 'group'}, {'message_type': 2},
                       {'message_state': 1}, {'create_time_ms': (self.now - 3600) * 1000},
                       {'context_token': ''}):
            self.bridge.receive(binding, self.message(**change))
        self.assertEqual(self.provider.sent, [])
        self.assertEqual(self.state()['favorites'], [])

    def test_bound_command_and_duplicate_inbox_applied_once(self):
        binding = self.bind()
        self.bridge.receive(binding, self.message())
        self.bridge.receive(binding, self.message())
        self.assertIn('aaai', self.state()['favorites'])
        self.assertEqual(len(self.provider.sent), 1)
        self.assertEqual(self.provider.sent[0]['peer'], self.provider.peer)
        status = self.bridge.status(self.user)
        self.assertTrue(status['binding']['contextReady'])
        self.assertEqual(status['deliveries'][0]['status'], 'accepted')

    def test_optional_ingress_fields_and_item_message_id_dedup(self):
        binding = self.bind()
        msg = self.message()
        for key in ('message_type', 'message_state', 'create_time_ms', 'message_id'):
            msg.pop(key)
        msg['item_list'][0]['msg_id'] = 'item-message-id'
        self.bridge.receive(binding, msg)
        msg['context_token'] = 'changed-context'
        msg['update_time_ms'] = self.now * 1000 + 1000
        self.bridge.receive(binding, msg)
        self.assertEqual(len(self.provider.sent), 1)
        self.assertIn('aaai', self.state()['favorites'])

    def test_timeout_is_uncertain_without_automatic_retry(self):
        binding = self.bind()
        self.provider.failure = ILinkError('timeout', '微信接口暂未响应。', retryable=True)
        self.bridge.receive(binding, self.message())
        self.bridge.receive(binding, self.message())
        self.assertEqual(len(self.provider.sent), 1)
        self.assertEqual(self.bridge.status(self.user)['deliveries'][0]['status'], 'uncertain')

    def test_web_deltas_preserve_wechat_favorites_and_reminders(self):
        self.client.request('POST', '/api/wechat/chat', {'text': '收藏 AAAI'})
        self.client.request('POST', '/api/wechat/chat', {'text': '提醒 CVPR 全文 提前7天'})
        state_before = self.state()
        self.assertEqual(len(state_before['reminders']), 1)
        result = self.client.request('POST', '/api/state/sync', {'favorites': {'add': ['acl'], 'remove': []},
                                                              'reminders': {'upsert': [], 'remove': []}})
        self.assertEqual(result[0], 200)
        self.assertEqual(set(result[1]['state']['favorites']), {'aaai', 'cvpr', 'acl'})
        self.assertEqual(result[1]['state']['reminders'], state_before['reminders'])
        result = self.client.request('POST', '/api/state/sync', {'favorites': {'add': [], 'remove': ['cvpr']}})
        self.assertFalse(result[1]['state']['reminders'][0]['enabled'])
        self.assertEqual(self.client.request('POST', '/api/state/sync', {'favorites': {'add': [], 'remove': []}}, use_csrf=False)[0], 403)
        self.assertEqual(self.client.request('POST', '/api/state/sync', {'favorites': {'add': 'bad', 'remove': []}})[0], 400)

    def test_password_change_revokes_wechat_access(self):
        binding = self.bind()
        result = self.client.request('POST', '/api/password', {'currentPassword': 'Temporary-Passphrase-42',
                                                            'newPassword': 'Replacement-Password-42'})
        self.assertEqual(result[0], 200)
        self.assertIsNone(self.bridge.binding(self.user))
        self.bridge.receive(binding, self.message())
        self.assertEqual(self.provider.sent, [])

    def test_disabled_connection_and_disconnected_generation_do_not_execute(self):
        binding = self.bind()
        self.bridge.settings(self.user, {'enabled': False})
        self.bridge.receive(binding, self.message())
        self.bridge.disconnect(self.user)
        self.bridge.receive(binding, self.message(message_id=2))
        self.assertEqual(self.provider.sent, [])
        self.assertEqual(self.state()['favorites'], [])

    def test_due_push_once_and_durable_after_service_tick_replay(self):
        self.due_reminder()
        old = self.now
        self.now += 61
        self.bridge.deliver_due()
        self.bridge.last_tick = old
        self.bridge.deliver_due()
        self.assertEqual(len(self.provider.sent), 1)
        self.assertIn('会投 DDL 提醒', self.provider.sent[0]['text'])
        self.assertIn('https://openreview.net/', self.provider.sent[0]['text'])

    def test_invitation_stage_is_preserved_when_existing_reminder_is_delivered(self):
        reminder = self.due_reminder()
        self.assertNotIn('submissionStage', reminder)
        conf = next(c for c in self.catalog['conferences'] if c['id'] == 'cvpr')
        conf['detail']['tracks'][0]['submissionStage'] = 'invitation-only'
        self.write_catalog()
        self.now += 61
        self.bridge.deliver_due()
        self.assertEqual(len(self.provider.sent), 1)
        text = self.provider.sent[0]['text']
        self.assertIn('全文截止 · 仅限获邀', text)
        self.assertIn('仅限获邀稿件；此阶段不接受普通新稿。', text)
        self.assertTrue(self.state()['reminders'][0]['enabled'])

    def test_date_change_skipped_and_source_unknown_never_guessed(self):
        self.due_reminder()
        next(c for c in self.catalog['conferences'] if c['id'] == 'cvpr')['detail']['tracks'][0]['fullDeadline'] = None
        self.write_catalog()
        self.now += 61
        self.bridge.deliver_due()
        self.assertEqual(self.provider.sent, [])
        self.assertEqual(self.bridge.status(self.user)['deliveries'][0]['status'], 'skipped')

    def test_disabled_push_and_paused_reminders_not_delivered(self):
        self.due_reminder()
        self.bridge.settings(self.user, {'pushEnabled': False})
        self.now += 61
        self.bridge.deliver_due()
        self.assertEqual(self.provider.sent, [])
        # Turning on later must not backfill the older reminder.
        self.bridge.settings(self.user, {'pushEnabled': True})
        self.bridge.last_tick -= 62
        self.bridge.deliver_due()
        self.assertEqual(self.provider.sent, [])

    def test_sleep_restart_no_old_reminder_burst(self):
        self.due_reminder()
        self.now += 601
        self.bridge.deliver_due()
        self.assertEqual(self.provider.sent, [])

    def test_missing_context_records_failure_without_fake_delivery(self):
        self.due_reminder(context=False)
        self.now += 61
        self.bridge.deliver_due()
        self.assertEqual(self.provider.sent, [])
        self.assertEqual(self.bridge.status(self.user)['deliveries'][0]['status'], 'failed')

    def test_session_invalid_pauses_and_does_not_automatic_resend(self):
        self.due_reminder()
        self.provider.failure = ILinkError('session_invalid', '微信连接已失效，请重新绑定。', session_invalid=True)
        self.now += 61
        self.bridge.deliver_due()
        self.bridge.last_tick -= 62
        self.bridge.deliver_due()
        self.assertEqual(len(self.provider.sent), 1)
        self.assertFalse(self.bridge.status(self.user)['binding']['enabled'])
        self.assertEqual(self.bridge.status(self.user)['deliveries'][0]['status'], 'failed')

    def test_sqlite_lease_prevents_second_process_worker_claim(self):
        self.bind()
        from wechat_service import WeChatService
        second = WeChatService(self.server.store, self.root, self.bridge.validate_patch, self.provider, lambda: self.now)
        self.assertEqual(second._claim(), [])
        self.now += 91
        self.assertEqual(len(second._claim()), 1)
        self.bridge.receive(self.bridge.binding(self.user), self.message())
        self.assertEqual(self.provider.sent, [])
        second.stop()

    def test_delete_account_cascades_credentials_and_journals(self):
        binding = self.bind()
        self.bridge.receive(binding, self.message())
        result = self.client.request('POST', '/api/account/delete', {'currentPassword': 'Temporary-Passphrase-42'})
        self.assertEqual(result[0], 200)
        with self.server.store.connect() as db:
            for table in ('wechat_bindings', 'wechat_deliveries', 'wechat_inbox', 'wechat_commands'):
                self.assertEqual(db.execute('SELECT COUNT(*) FROM ' + table).fetchone()[0], 0)
        self.bridge.receive(binding, self.message(message_id=3))
        self.assertEqual(len(self.provider.sent), 1)

    def restart_bridge(self):
        """Simulate process replacement without replacing its account database."""
        self.bridge.stop()
        from wechat_service import WeChatService
        self.bridge = WeChatService(self.server.store, self.root, self.bridge.validate_patch,
                                   self.provider, lambda: self.now)
        self.server.wechat = self.bridge
        self.bridge._claim()
        return self.bridge.binding(self.user)

    def command_row(self):
        with self.server.store.connect() as db:
            return dict(db.execute('SELECT * FROM wechat_commands ORDER BY received_at,rowid LIMIT 1').fetchone())

    def test_received_command_survives_cursor_commit_and_process_restart(self):
        binding = self.bind()
        self.provider.updates = [self.message()]
        recover = self.bridge.recover_commands
        calls = []

        def stop_after_cursor(previous):
            calls.append(1)
            if len(calls) == 2:
                self.bridge.closed.set()  # interruption after cursor save, before processing
                return
            recover(previous)

        with patch.object(self.bridge, 'recover_commands', side_effect=stop_after_cursor):
            self.bridge._poll(binding)
        self.assertEqual(self.bridge.binding(self.user)['cursor'], 'fake-cursor')
        self.assertEqual(self.command_row()['state'], 'queued')
        self.assertEqual(self.state()['favorites'], [])
        self.assertEqual(self.provider.sent, [])
        self.assertEqual(self.bridge.status(self.user)['pendingCommands'], 1)
        self.assertNotIn('收藏 AAAI', json.dumps(self.bridge.status(self.user), ensure_ascii=False))
        restarted = self.restart_bridge()
        self.bridge.recover_commands(restarted)
        self.assertIn('aaai', self.state()['favorites'])
        self.assertEqual(len(self.provider.sent), 1)
        self.assertEqual(self.command_row()['state'], 'accepted')
        self.assertEqual(self.command_row()['command_text'], '')
        self.assertEqual(self.command_row()['reply_text'], '')

    def test_poll_retains_cursor_when_access_changes_during_fetch(self):
        for boundary in ('paused', 'inactive', 'expired', 'rebound', 'new_owner', 'stopped'):
            with self.subTest(boundary=boundary):
                self.bridge.closed.clear()
                with self.server.store.connect() as db:
                    db.execute('UPDATE users SET active=1 WHERE id=?', (self.user,))
                self.bridge.disconnect(self.user)
                binding = self.bind()
                message = self.message()

                def updates(cursor=''):
                    if boundary == 'paused':
                        self.bridge.settings(self.user, {'enabled': False})
                    elif boundary == 'inactive':
                        with self.server.store.connect() as db:
                            db.execute('UPDATE users SET active=0 WHERE id=?', (self.user,))
                    elif boundary == 'expired':
                        self.now += 91
                    elif boundary == 'rebound':
                        self.bridge.disconnect(self.user)
                        self.bind()
                    elif boundary == 'new_owner':
                        with self.server.store.connect() as db:
                            db.execute('UPDATE wechat_bindings SET worker_owner=?', ('another-process',))
                    else:
                        self.bridge.closed.set()
                    return {'msgs': [message], 'get_updates_buf': 'must-not-advance'}

                with patch.object(self.provider, 'get_updates', side_effect=updates):
                    self.bridge._poll(binding)
                with self.server.store.connect() as db:
                    self.assertEqual(db.execute('SELECT cursor FROM wechat_bindings').fetchone()[0], '')
                    self.assertEqual(db.execute('SELECT COUNT(*) FROM wechat_commands').fetchone()[0], 0)
                self.assertEqual(self.provider.sent, [])

    def test_poll_rechecks_access_after_persisting_batch(self):
        for boundary in ('paused', 'inactive', 'expired'):
            with self.subTest(boundary=boundary):
                with self.server.store.connect() as db:
                    db.execute('UPDATE users SET active=1 WHERE id=?', (self.user,))
                self.bridge.disconnect(self.user)
                binding = self.bind()
                self.provider.updates = [self.message()]
                receive = self.bridge.receive

                def receive_then_suspend(*args, **kwargs):
                    result = receive(*args, **kwargs)
                    if boundary == 'paused':
                        self.bridge.settings(self.user, {'enabled': False})
                    elif boundary == 'inactive':
                        with self.server.store.connect() as db:
                            db.execute('UPDATE users SET active=0 WHERE id=?', (self.user,))
                    else:
                        self.now += 91
                    return result

                with patch.object(self.bridge, 'receive', side_effect=receive_then_suspend):
                    self.bridge._poll(binding)
                with self.server.store.connect() as db:
                    self.assertEqual(db.execute('SELECT cursor FROM wechat_bindings').fetchone()[0], '')
                self.assertEqual(self.command_row()['state'], 'queued')
                self.assertEqual(self.provider.sent, [])

    def test_poll_retains_cursor_if_connection_resumes_after_deferred_receive(self):
        binding = self.bind()
        self.provider.updates = [self.message()]
        receive = self.bridge.receive

        def paused_receive(*args, **kwargs):
            self.bridge.settings(self.user, {'enabled': False})
            result = receive(*args, **kwargs)
            self.bridge.settings(self.user, {'enabled': True})
            return result

        with patch.object(self.bridge, 'receive', side_effect=paused_receive):
            self.bridge._poll(binding)
        self.assertEqual(self.bridge.binding(self.user)['cursor'], '')
        self.assertEqual(self.bridge.status(self.user)['pendingCommands'], 0)

    def test_poll_allows_renewed_lease_before_cursor_commit(self):
        binding = self.bind()
        message = self.message()
        recover = self.bridge.recover_commands
        calls = []

        def renew_before_return(cursor=''):
            self.now += 80
            self.bridge._claim()
            return {'msgs': [message], 'get_updates_buf': 'renewed-cursor'}

        def stop_after_cursor(previous):
            calls.append(1)
            if len(calls) == 2:
                self.bridge.closed.set()
                return
            recover(previous)

        with patch.object(self.provider, 'get_updates', side_effect=renew_before_return), \
                patch.object(self.bridge, 'recover_commands', side_effect=stop_after_cursor):
            self.bridge._poll(binding)
        self.assertEqual(self.bridge.binding(self.user)['cursor'], 'renewed-cursor')
        self.assertEqual(self.command_row()['state'], 'queued')

    def test_old_poll_cannot_overwrite_cursor_advanced_by_replacement_worker(self):
        binding = self.bind()
        message = self.message()

        def updates(cursor=''):
            # A long-running old request finishes after lease handoff and
            # reacquisition; its original cursor must not replace newer state.
            with self.server.store.connect() as db:
                db.execute('UPDATE wechat_bindings SET cursor=?', ('newer-cursor',))
            return {'msgs': [message], 'get_updates_buf': 'older-cursor'}

        with patch.object(self.provider, 'get_updates', side_effect=updates):
            self.bridge._poll(binding)
        self.assertEqual(self.bridge.binding(self.user)['cursor'], 'newer-cursor')
        self.assertEqual(self.command_row()['state'], 'queued')

    def test_pending_command_recovery_follows_renewal_and_lease_handoff(self):
        binding = self.bind()
        self.bridge.receive(binding, self.message(), process=False)
        from wechat_service import WeChatService
        second = WeChatService(self.server.store, self.root, self.bridge.validate_patch, self.provider, lambda: self.now)
        self.now += 80
        self.bridge._claim()
        self.now += 20
        self.assertEqual(second._claim(), [])  # The original lease was renewed.
        self.now += 71
        replacement = second._claim()[0]
        self.bridge.recover_commands(binding)
        self.assertEqual(self.command_row()['state'], 'queued')
        self.assertEqual(self.state()['favorites'], [])
        second.recover_commands(replacement)
        self.assertEqual(self.command_row()['state'], 'accepted')
        self.assertEqual(self.state()['favorites'], ['aaai'])
        self.assertEqual(len(self.provider.sent), 1)
        second.stop()

    def test_poll_stops_before_fetch_if_recovery_pauses_invalid_session(self):
        binding = self.bind()
        self.bridge.receive(binding, self.message(), process=False)
        self.provider.failure = ILinkError('session_invalid', '微信连接已失效，请重新绑定。', session_invalid=True)
        with patch.object(self.provider, 'get_updates') as updates:
            self.bridge._poll(binding)
            updates.assert_not_called()
        self.assertFalse(self.bridge.binding(self.user)['enabled'])
        self.assertEqual(self.command_row()['state'], 'failed')
        self.assertEqual(self.command_row()['command_text'], '')

    def test_prepared_response_resumes_without_repeating_committed_mutation(self):
        binding = self.bind()
        with patch.object(self.bridge, '_send', side_effect=RuntimeError('simulated crash before send')):
            with self.assertRaises(RuntimeError):
                self.bridge.receive(binding, self.message())
        self.assertEqual(self.command_row()['state'], 'prepared')
        self.assertIn('aaai', self.state()['favorites'])
        # A later webpage edit must not be undone by repeating the old command.
        self.server.store.sync_lists(self.user, {'favorites': {'add': ['cvpr'], 'remove': ['aaai']}})
        self.now += 180
        restarted = self.restart_bridge()
        self.bridge.recover_commands(restarted)
        self.assertEqual(self.state()['favorites'], ['cvpr'])
        self.assertEqual(len(self.provider.sent), 1)
        self.assertTrue(self.provider.sent[0]['text'].startswith('补回上次处理结果'))

    def test_inflight_send_on_restart_is_uncertain_and_not_repeated(self):
        binding = self.bind()
        with patch.object(self.bridge, '_send', side_effect=RuntimeError('simulated crash')):
            with self.assertRaises(RuntimeError):
                self.bridge.receive(binding, self.message())
        row = self.command_row()
        key = 'chat:' + binding['generation'] + ':' + row['message_key']
        with self.server.store.connect() as db:
            db.execute('INSERT INTO wechat_deliveries VALUES (?,?,?,?,?,?)',
                       (self.user, key, 'reply', 'sending', 'pending network result', self.now))
        restarted = self.restart_bridge()
        self.bridge.recover_commands(restarted)
        self.assertEqual(self.provider.sent, [])
        self.assertEqual(self.command_row()['state'], 'uncertain')
        self.assertEqual(self.bridge.status(self.user)['deliveries'][0]['status'], 'uncertain')
        self.assertEqual(self.command_row()['reply_text'], '')

    def test_completed_delivery_before_queue_cleanup_does_not_resend(self):
        binding = self.bind()
        send = self.bridge._send

        def crash_after_send(*args):
            send(*args)
            raise RuntimeError('crash after accepted delivery')

        with patch.object(self.bridge, '_send', side_effect=crash_after_send):
            with self.assertRaises(RuntimeError):
                self.bridge.receive(binding, self.message())
        self.assertEqual(len(self.provider.sent), 1)
        restarted = self.restart_bridge()
        self.bridge.recover_commands(restarted)
        self.assertEqual(len(self.provider.sent), 1)
        self.assertEqual(self.command_row()['state'], 'accepted')

    def test_old_queued_mutation_requires_resend_but_read_query_can_resume(self):
        binding = self.bind()
        self.bridge.receive(binding, self.message(), process=False)
        self.bridge.receive(binding, self.message('CVPR 截止', message_id=2), process=False)
        self.now += 86401
        restarted = self.restart_bridge()
        self.bridge.recover_commands(restarted)
        self.assertEqual(self.state()['favorites'], [])
        self.assertEqual(len(self.provider.sent), 2)
        self.assertIn('未执行', self.provider.sent[0]['text'])
        self.assertIn('CVPR', self.provider.sent[1]['text'])

    def test_pending_work_stays_private_and_paused_binding_cannot_resume(self):
        binding = self.bind()
        self.bridge.receive(binding, self.message(), process=False)
        self.bridge.settings(self.user, {'enabled': False})
        restarted = self.restart_bridge()
        self.bridge.recover_commands(restarted)
        self.assertEqual(self.provider.sent, [])
        self.assertEqual(self.command_row()['state'], 'queued')
        self.bridge.disconnect(self.user)
        with self.server.store.connect() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM wechat_commands').fetchone()[0], 0)

    def test_catalog_failure_keeps_received_command_for_later_recovery(self):
        binding = self.bind()
        self.bridge.receive(binding, self.message(), process=False)
        (self.root / 'data/conferences.json').write_text('{}')
        with self.assertRaises(WeChatError):
            self.bridge.recover_commands(binding)
        self.assertEqual(self.command_row()['state'], 'queued')
        self.assertEqual(self.state()['favorites'], [])
        self.write_catalog()
        self.bridge.recover_commands(binding)
        self.assertIn('aaai', self.state()['favorites'])
        self.assertEqual(len(self.provider.sent), 1)

    def test_real_background_threads_process_chat_and_deadline_with_fake_network(self):
        self.due_reminder()
        self.bridge.stop()  # Release this test driver's lease before starting real loops.
        from wechat_service import WeChatService
        running = WeChatService(self.server.store, self.root, self.bridge.validate_patch,
                               self.provider, lambda: self.now)
        self.provider.updates = [self.message('收藏 AAAI')]
        running.start()
        try:
            until = time.monotonic() + 6
            while len(self.provider.sent) < 1 and time.monotonic() < until:
                time.sleep(.05)
            self.assertEqual(len(self.provider.sent), 1)
            self.assertIn('aaai', self.state()['favorites'])
            self.now += 61
            until = time.monotonic() + 6
            while len(self.provider.sent) < 2 and time.monotonic() < until:
                time.sleep(.05)
            self.assertEqual(len(self.provider.sent), 2)
            self.assertIn('会投 DDL 提醒', self.provider.sent[1]['text'])
        finally:
            running.stop()


if __name__ == '__main__':
    unittest.main()
