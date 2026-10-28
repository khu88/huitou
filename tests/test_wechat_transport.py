"""Protocol/security contract tests; never contact WeChat or load real tokens."""
import base64
import json
import sys
import unittest
from pathlib import Path
from urllib.error import URLError
from urllib.parse import parse_qs, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from wechat_transport import (
    CLIENT_VERSION, DEFAULT_BASE_URL, ILinkClient, ILinkError,
    MAX_RESPONSE_BYTES, MAX_TEXT_BYTES, _NoRedirect, safe_wechat_url,
)


class FakeHTTP:
    def __init__(self, payload=None, status=200, error=None, raw=None):
        self.payload = payload if payload is not None else {'ret': 0}
        self.status, self.error, self.raw = status, error, raw
        self.calls = []

    def __call__(self, method, url, headers, body, timeout):
        self.calls.append({'method': method, 'url': url, 'headers': headers,
                           'body': json.loads(body) if body is not None else None,
                           'timeout': timeout})
        if self.error:
            raise self.error
        return self.status, self.raw if self.raw is not None else json.dumps(self.payload).encode()


class ILinkTransportTests(unittest.TestCase):
    def test_base_allowlist_has_domain_boundary_and_no_url_credentials(self):
        self.assertEqual(safe_wechat_url('https://ilinkai.weixin.qq.com/', base=True), DEFAULT_BASE_URL)
        self.assertEqual(safe_wechat_url('https://liteapp.weixin.qq.com/a?b=c'),
                         'https://liteapp.weixin.qq.com/a?b=c')
        invalid = [
            'http://ilinkai.weixin.qq.com', 'https://weixin.qq.com.evil.example',
            'https://evilweixin.qq.com', 'https://ilinkai.weixin.qq.com:443',
            'https://x@ilinkai.weixin.qq.com', 'https://127.0.0.1',
            'https://[::1]', 'https://ilinkai.weixin.qq.com./',
            'https://ilinkai.weixin.qq.com#secret', 'https://ilinkai.weixin.qq.com\n/',
            'https://a\\@ilinkai.weixin.qq.com', 'https://.weixin.qq.com',
            'https://-a.weixin.qq.com', 'https://a..weixin.qq.com',
        ]
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(ILinkError):
                safe_wechat_url(value)
        for value in ['https://ilinkai.weixin.qq.com/api', 'https://ilinkai.weixin.qq.com?x=1']:
            with self.subTest(value=value), self.assertRaises(ILinkError):
                ILinkClient(base_url=value)

    def test_qr_request_has_public_headers_no_token_or_base_info(self):
        fake = FakeHTTP({'qrcode': 'challenge', 'qrcode_img_content': 'https://liteapp.weixin.qq.com/q?secret=1'})
        client = ILinkClient(token='private-token', request=fake)
        result = client.request_qr()
        request = fake.calls[0]
        self.assertEqual(result['qrcode_url'], result['qrcode_img_content'])
        self.assertEqual(request['url'], DEFAULT_BASE_URL + '/ilink/bot/get_bot_qrcode?bot_type=3')
        self.assertEqual(request['body'], {'local_token_list': []})
        self.assertEqual(request['headers']['iLink-App-ClientVersion'], CLIENT_VERSION)
        self.assertEqual(request['headers']['AuthorizationType'], 'ilink_bot_token')
        self.assertNotIn('Authorization', request['headers'])
        uin = int(base64.b64decode(request['headers']['X-WECHAT-UIN']))
        self.assertTrue(0 <= uin < 2**32)
        self.assertNotIn('private-token', repr(client))

    def test_qr_unknown_format_is_data_not_image_or_url(self):
        result = ILinkClient(request=FakeHTTP({'qrcode': 'q', 'qrcode_img_content': 'opaque QR payload'})).request_qr()
        self.assertEqual(result['qrcode_url'], '')
        self.assertEqual(result['qrcode_img_content'], 'opaque QR payload')
        with self.assertRaises(ILinkError):
            ILinkClient(request=FakeHTTP({'qrcode': 'q', 'qrcode_img_content': 'https://evil.example/qr'})).request_qr()

    def test_qr_status_encodes_query_without_authentication_headers(self):
        fake = FakeHTTP({'status': 'scaned'})
        self.assertEqual(ILinkClient(token='private', request=fake).poll_qr('q+?&=', '1234'), {'status': 'scaned'})
        call = fake.calls[0]
        self.assertEqual(call['method'], 'GET')
        self.assertEqual(parse_qs(urlsplit(call['url']).query), {'qrcode': ['q+?&='], 'verify_code': ['1234']})
        self.assertEqual(set(call['headers']), {'iLink-App-Id', 'iLink-App-ClientVersion'})
        self.assertIsNone(call['body'])
        self.assertEqual(call['timeout'], 35)

    def test_qr_redirect_validates_and_updates_only_poll_host(self):
        fake = FakeHTTP({'status': 'scaned_but_redirect', 'redirect_host': 'region.weixin.qq.com'})
        client = ILinkClient(token='private', request=fake)
        client.poll_qr('q')
        fake.payload = {'status': 'wait'}
        client.poll_qr('q')
        self.assertTrue(fake.calls[-1]['url'].startswith('https://region.weixin.qq.com/'))
        self.assertEqual(client.base_url, DEFAULT_BASE_URL)
        for host in ['evil.example', 'weixin.qq.com:8443', 'user@weixin.qq.com', 'https://weixin.qq.com']:
            fake.payload = {'status': 'scaned_but_redirect', 'redirect_host': host}
            with self.subTest(host=host), self.assertRaises(ILinkError):
                client.poll_qr('q')

    def test_confirmed_requires_exact_scanner_and_validated_base(self):
        valid = {'status': 'confirmed', 'bot_token': 'secret', 'ilink_bot_id': 'bot',
                 'ilink_user_id': 'scanner', 'baseurl': 'https://region.weixin.qq.com'}
        result = ILinkClient(request=FakeHTTP(valid)).poll_qr('q')
        self.assertEqual(result, valid)
        for field in ['bot_token', 'ilink_bot_id', 'ilink_user_id']:
            bad = dict(valid)
            del bad[field]
            with self.subTest(field=field), self.assertRaises(ILinkError):
                ILinkClient(request=FakeHTTP(bad)).poll_qr('q')
        bad = dict(valid, baseurl='https://attacker.example')
        with self.assertRaises(ILinkError):
            ILinkClient(request=FakeHTTP(bad)).poll_qr('q')

    def test_all_known_qr_states_and_unknown_state(self):
        for state in ['wait', 'scaned', 'expired', 'need_verifycode', 'verify_code_blocked', 'binded_redirect']:
            with self.subTest(state=state):
                result = ILinkClient(request=FakeHTTP({'status': state})).poll_qr('q')
                self.assertEqual(result, {'status': state})
        with self.assertRaises(ILinkError):
            ILinkClient(request=FakeHTTP({'status': 'unexpected'})).poll_qr('q')

    def test_updates_carry_auth_metadata_and_preserve_cursor_if_empty(self):
        fake = FakeHTTP({'ret': 0, 'msgs': [{'from_user_id': 'u'}], 'get_updates_buf': ''})
        result = ILinkClient(token='token', request=fake).get_updates('old-cursor')
        self.assertEqual(result['get_updates_buf'], 'old-cursor')
        self.assertEqual(len(result['msgs']), 1)
        call = fake.calls[0]
        self.assertEqual(call['headers']['Authorization'], 'Bearer token')
        self.assertEqual(call['body']['get_updates_buf'], 'old-cursor')
        self.assertEqual(call['body']['base_info'], {'channel_version': '2.4.10', 'bot_agent': 'ConfAtlas/1.0'})
        self.assertNotIn('sync_buf', call['body'])
        self.assertEqual(call['timeout'], 35)

    def test_updates_reject_malformed_messages_and_cursor(self):
        for payload in [{'msgs': 'bad'}, {'msgs': [False]}, {'msgs': [{}] * 501}, {'get_updates_buf': 42}]:
            with self.subTest(payload=str(payload)[:40]), self.assertRaises(ILinkError):
                ILinkClient(token='token', request=FakeHTTP(payload)).get_updates()

    def test_send_payload_and_acknowledgement(self):
        fake = FakeHTTP({'ret': 0, 'message_id': 'message-1'})
        result = ILinkClient(token='token', request=fake).send_text('scanner', 'context', '提醒\nCVPR', 'unique-1')
        self.assertEqual(result, {'ret': 0, 'client_id': 'unique-1', 'message_id': 'message-1'})
        msg = fake.calls[0]['body']['msg']
        self.assertEqual(msg, {'from_user_id': '', 'to_user_id': 'scanner', 'client_id': 'unique-1',
                               'message_type': 2, 'message_state': 2, 'context_token': 'context',
                               'item_list': [{'type': 1, 'text_item': {'text': '提醒\nCVPR'}}]})
        self.assertEqual(fake.calls[0]['timeout'], 15)

    def test_send_requires_context_and_bounded_text_before_network(self):
        fake = FakeHTTP()
        client = ILinkClient(token='token', request=fake)
        with self.assertRaises(ILinkError) as error:
            client.send_text('scanner', '', 'text', 'id')
        self.assertEqual(error.exception.code, 'missing_context')
        for text in ['', ' ', '字' * (MAX_TEXT_BYTES // 3 + 1)]:
            with self.subTest(size=len(text)), self.assertRaises(ILinkError):
                client.send_text('scanner', 'ctx', text, 'id')
        self.assertEqual(fake.calls, [])

    def test_missing_send_ret_is_not_success(self):
        with self.assertRaises(ILinkError) as error:
            ILinkClient(token='t', request=FakeHTTP({})).send_text('s', 'c', 't', 'id')
        self.assertEqual(error.exception.code, 'send_unconfirmed')

    def test_session_invalid_checks_either_provider_code(self):
        for payload in [{'ret': -14}, {'ret': 0, 'errcode': -14}, {'ret': 7, 'errcode': -14}]:
            payload['errmsg'] = 'secret-token secret-context'
            with self.subTest(payload=payload), self.assertRaises(ILinkError) as error:
                ILinkClient(token='t', request=FakeHTTP(payload)).get_updates()
            self.assertTrue(error.exception.session_invalid)
            self.assertEqual(error.exception.provider_code, -14)
            self.assertNotIn('secret', str(error.exception))

    def test_provider_and_network_errors_never_echo_body_or_url(self):
        variants = [
            (FakeHTTP({'ret': 9, 'errmsg': 'secret-token'}), 'provider_error'),
            (FakeHTTP(status=500, raw=b'secret-token'), 'http_error'),
            (FakeHTTP(error=URLError('secret-token')), 'network_error'),
            (FakeHTTP(error=TimeoutError('secret-token')), 'timeout'),
        ]
        for fake, code in variants:
            with self.subTest(code=code), self.assertRaises(ILinkError) as error:
                ILinkClient(token='secret-token', request=fake).get_updates()
            self.assertEqual(error.exception.code, code)
            self.assertNotIn('secret', str(error.exception))

    def test_no_automatic_retry_or_http_redirect(self):
        fake = FakeHTTP(status=302, raw=b'secret-token')
        with self.assertRaises(ILinkError):
            ILinkClient(token='token', request=fake).get_updates()
        self.assertEqual(len(fake.calls), 1)
        self.assertIsNone(_NoRedirect().redirect_request(None, None, 302, '', {}, 'https://evil.example'))

    def test_response_size_type_and_json_are_bounded(self):
        for raw in [b'x' * (MAX_RESPONSE_BYTES + 1), b'not-json', b'[]', b'\xff', b'{"ret":true}']:
            with self.subTest(size=len(raw)), self.assertRaises(ILinkError):
                ILinkClient(token='token', request=FakeHTTP(raw=raw)).get_updates()

    def test_empty_or_control_token_never_sends(self):
        fake = FakeHTTP()
        with self.assertRaises(ILinkError):
            ILinkClient(request=fake).get_updates()
        for token in ['bad\r\nheader', '凭证']:
            with self.subTest(token=token), self.assertRaises(ILinkError):
                ILinkClient(token=token, request=fake)
        self.assertEqual(fake.calls, [])


if __name__ == '__main__':
    unittest.main()
