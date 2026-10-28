"""Small text-only iLink client, using the published Tencent client protocol.

Compatibility reference checked 2026-10-28: Tencent/openclaw-weixin 2.4.10,
docs/protocol_zh_CN.md, src/api/api.ts and src/auth/login-qr.ts. This is an
independent adapter, not the Tencent plugin. There is no automatic login,
retry, persistence, or background work at import time.

For tests, ``request(method, url, headers, body, timeout)`` may be injected;
it must return ``(http_status, response_bytes)``. The default transport rejects
HTTP redirects. Provider response text and request credentials never appear in
exceptions. Callers must not log successful QR, update, or credential payloads.
"""
from __future__ import annotations

import base64
import json
import re
import secrets
import socket
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


DEFAULT_BASE_URL = 'https://ilinkai.weixin.qq.com'
CHANNEL_VERSION = '2.4.10'
CLIENT_VERSION = str((2 << 16) | (4 << 8) | 10)
MAX_RESPONSE_BYTES = 1_048_576
MAX_TEXT_BYTES = 12_000
API_TIMEOUT = 15
POLL_TIMEOUT = 35
QR_STATUSES = frozenset({
    'wait', 'scaned', 'confirmed', 'expired', 'need_verifycode',
    'verify_code_blocked', 'scaned_but_redirect', 'binded_redirect',
})


class ILinkError(Exception):
    """Safe application error; raw provider text is deliberately discarded."""

    def __init__(self, code, message, *, provider_code=None, retryable=False,
                 session_invalid=False):
        self.code = code
        self.message = message
        self.provider_code = provider_code
        self.retryable = retryable
        self.session_invalid = session_invalid
        super().__init__(message)


def _invalid(message='微信接口返回了无法识别的数据。'):
    return ILinkError('invalid_response', message)


def safe_wechat_url(value, *, base=False):
    """Validate HTTPS Weixin URLs before using a provider-controlled address.

    Ports, credentials, fragments, control characters, non-ASCII hostnames,
    trailing dots and non-Weixin hosts are rejected. API base URLs additionally
    cannot carry a query or a non-root path. No string-prefix hostname checks.
    """
    if (not isinstance(value, str) or len(value) > 8192 or
            any(ord(c) <= 32 or ord(c) == 127 for c in value) or '\\' in value):
        raise ILinkError('unsafe_url', '微信返回的地址不在允许范围内。')
    try:
        parsed = urlsplit(value)
        host = parsed.hostname or ''
        valid_host = bool(re.fullmatch(r'[a-z0-9.-]+', host)) and (
            host == 'weixin.qq.com' or host.endswith('.weixin.qq.com'))
        if (parsed.scheme != 'https' or not valid_host or parsed.username is not None
                or parsed.password is not None or ':' in parsed.netloc
                or parsed.fragment or (base and (parsed.path not in ('', '/') or parsed.query))):
            raise ValueError
        if any(not part or part.startswith('-') or part.endswith('-') for part in host.split('.')):
            raise ValueError
    except (TypeError, ValueError):
        raise ILinkError('unsafe_url', '微信返回的地址不在允许范围内。') from None
    return urlunsplit(('https', host, '' if base else parsed.path, parsed.query, ''))


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Never forward bearer tokens or QR query parameters through redirects.
        return None


def _http_request(method, url, headers, body, timeout):
    request = Request(url, data=body, headers=headers, method=method)
    opener = build_opener(_NoRedirect())
    try:
        with opener.open(request, timeout=timeout) as response:
            return response.status, response.read(MAX_RESPONSE_BYTES + 1)
    except HTTPError as error:
        # Neither error body nor URL is needed to classify HTTP failures.
        code = error.code
        error.close()
        return code, b''


def _bounded_string(value, limit, *, empty=False):
    return (isinstance(value, str) and (empty or bool(value)) and
            len(value) <= limit and all(ord(c) >= 32 and ord(c) != 127 for c in value))


def _check_business_error(payload):
    codes = []
    for key in ('ret', 'errcode'):
        if key not in payload:
            continue
        value = payload[key]
        if isinstance(value, bool) or not isinstance(value, int):
            raise _invalid()
        if value:
            codes.append(value)
    if -14 in codes:
        raise ILinkError('session_invalid', '微信连接已失效，请重新绑定。',
                         provider_code=-14, session_invalid=True)
    if codes:
        raise ILinkError('provider_error', '微信接口未接受本次请求。',
                         provider_code=codes[0])


class ILinkClient:
    def __init__(self, base_url=DEFAULT_BASE_URL, token='', request=None):
        self.base_url = safe_wechat_url(base_url, base=True)
        if not _bounded_string(token, 8192, empty=True) or not token.isascii():
            raise ILinkError('invalid_token', '微信凭证格式无效。')
        self.token = token
        self._request = request or _http_request
        self._qr_base_url = DEFAULT_BASE_URL

    def __repr__(self):
        return '<ILinkClient credentials=redacted>'

    def _call(self, method, path, body=None, *, authenticated=False,
              timeout=API_TIMEOUT, base_url=None):
        # Revalidate even if a caller has assigned a new public base_url.
        base_url = safe_wechat_url(base_url or self.base_url, base=True)
        headers = {'iLink-App-Id': 'bot', 'iLink-App-ClientVersion': CLIENT_VERSION}
        if method == 'POST':
            headers.update({
                'Content-Type': 'application/json',
                'AuthorizationType': 'ilink_bot_token',
                'X-WECHAT-UIN': base64.b64encode(str(secrets.randbits(32)).encode()).decode(),
            })
        if authenticated:
            if not _bounded_string(self.token, 8192) or not self.token.isascii():
                raise ILinkError('missing_token', '请先绑定微信。')
            headers['Authorization'] = 'Bearer ' + self.token
            body = dict(body or {}, base_info={
                'channel_version': CHANNEL_VERSION, 'bot_agent': 'ConfAtlas/1.0',
            })
        data = None if body is None else json.dumps(body, ensure_ascii=False, allow_nan=False).encode('utf-8')
        try:
            status, raw = self._request(method, base_url + path, headers, data, timeout)
        except (TimeoutError, socket.timeout):
            raise ILinkError('timeout', '微信接口暂未响应，请稍后重试。', retryable=True) from None
        except (URLError, OSError):
            raise ILinkError('network_error', '暂时无法连接微信接口。', retryable=True) from None
        # The injected request must obey the same raw response boundary.
        if isinstance(status, bool) or not isinstance(status, int):
            raise _invalid()
        if not 200 <= status < 300:
            raise ILinkError('http_error', '微信接口暂时不可用（HTTP %d）。' % status,
                             provider_code=status, retryable=status == 429 or status >= 500,
                             session_invalid=status == 401)
        if not isinstance(raw, bytes) or len(raw) > MAX_RESPONSE_BYTES:
            raise _invalid('微信接口响应超过大小限制或格式无效。')
        try:
            payload = json.loads(raw.decode('utf-8'), parse_constant=lambda _: None)
        except (UnicodeError, ValueError, RecursionError):
            raise _invalid() from None
        if not isinstance(payload, dict):
            raise _invalid()
        _check_business_error(payload)
        return payload

    def request_qr(self):
        """Get a QR challenge. Returned QR payload URL is NOT an image URL.

        Returns qrcode (private challenge), qrcode_img_content (raw payload),
        qrcode_url (validated Weixin HTTPS URL, or empty for unsupported payload).
        Unknown raw formats are never rendered or fetched by this module.
        """
        self._qr_base_url = DEFAULT_BASE_URL
        data = self._call('POST', '/ilink/bot/get_bot_qrcode?bot_type=3',
                          {'local_token_list': []}, base_url=DEFAULT_BASE_URL)
        qr, content = data.get('qrcode'), data.get('qrcode_img_content')
        if not _bounded_string(qr, 8192) or not _bounded_string(content, 8192):
            raise _invalid('微信未返回有效的绑定信息。')
        url = ''
        if content.lower().startswith(('https:', 'http:', '//')):
            url = safe_wechat_url(content)
        return {'qrcode': qr, 'qrcode_img_content': content, 'qrcode_url': url}

    def poll_qr(self, qrcode, verify_code=None):
        """One poll only; caller schedules retries and enforces challenge TTL.

        A validated scaned_but_redirect updates the next QR polling host. A
        confirmed response must include scanner ID, token and bot ID so that the
        caller can bind to exactly that scanner. Tokens are not auto-persisted.
        """
        if not _bounded_string(qrcode, 8192):
            raise ILinkError('invalid_qr', '微信绑定信息无效，请重新生成。')
        query = {'qrcode': qrcode}
        if verify_code is not None:
            if not isinstance(verify_code, str) or not re.fullmatch(r'[0-9]{1,12}', verify_code):
                raise ILinkError('invalid_verification', '请输入手机显示的数字验证码。')
            query['verify_code'] = verify_code
        data = self._call('GET', '/ilink/bot/get_qrcode_status?' + urlencode(query),
                          timeout=POLL_TIMEOUT, base_url=self._qr_base_url)
        status = data.get('status')
        if not isinstance(status, str) or status not in QR_STATUSES:
            raise _invalid('微信返回了未知的绑定状态。')
        result = {'status': status}
        if status == 'scaned_but_redirect':
            host = data.get('redirect_host')
            if not isinstance(host, str) or '://' in host:
                raise _invalid('微信未返回有效的后续绑定地址。')
            self._qr_base_url = safe_wechat_url('https://' + host, base=True)
            result['redirect_host'] = urlsplit(self._qr_base_url).hostname
        elif status == 'confirmed':
            for field in ('bot_token', 'ilink_bot_id', 'ilink_user_id'):
                if not _bounded_string(data.get(field), 8192 if field == 'bot_token' else 512):
                    raise _invalid('微信绑定缺少凭证或扫码者身份，请重新绑定。')
                if field == 'bot_token' and not data[field].isascii():
                    raise _invalid('微信凭证格式无效，请重新绑定。')
                result[field] = data[field]
            result['baseurl'] = safe_wechat_url(data.get('baseurl') or self._qr_base_url, base=True)
        return result

    def get_updates(self, cursor=''):
        if not _bounded_string(cursor, 65536, empty=True):
            raise ILinkError('invalid_cursor', '微信消息游标无效。')
        data = self._call('POST', '/ilink/bot/getupdates', {'get_updates_buf': cursor},
                          authenticated=True, timeout=POLL_TIMEOUT)
        msgs = data.get('msgs', [])
        next_cursor = data.get('get_updates_buf') or cursor
        if (not isinstance(msgs, list) or len(msgs) > 500 or
                any(not isinstance(msg, dict) for msg in msgs) or
                not _bounded_string(next_cursor, 65536, empty=True)):
            raise _invalid()
        return {'ret': 0, 'msgs': msgs, 'get_updates_buf': next_cursor}

    def send_text(self, to_user_id, context_token, text, client_id):
        """Attempt one text send. Caller owns deduplication/retry policy.

        An explicit ret:0 acknowledges provider acceptance, not phone delivery.
        Missing reply context is rejected before contacting the provider.
        """
        if not _bounded_string(context_token, 8192):
            raise ILinkError('missing_context', '请先在微信里向会投发送一条消息。')
        if not _bounded_string(to_user_id, 512) or not _bounded_string(client_id, 160):
            raise ILinkError('invalid_destination', '微信消息接收者或标识无效。')
        if (not isinstance(text, str) or not text.strip() or
                len(text.encode('utf-8')) > MAX_TEXT_BYTES):
            raise ILinkError('invalid_text', '微信消息为空或超过长度限制。')
        data = self._call('POST', '/ilink/bot/sendmessage', {'msg': {
            'from_user_id': '', 'to_user_id': to_user_id, 'client_id': client_id,
            'message_type': 2, 'message_state': 2, 'context_token': context_token,
            'item_list': [{'type': 1, 'text_item': {'text': text}}],
        }}, authenticated=True)
        if data.get('ret') != 0:
            raise ILinkError('send_unconfirmed', '微信未明确确认接收，请勿重复发送。')
        result = {'ret': 0, 'client_id': client_id}
        if _bounded_string(data.get('message_id'), 512):
            result['message_id'] = data['message_id']
        return result
