# Local account API

Run `python3 serve.py --port 8765`. The service binds only to `127.0.0.1` and stores account data in `.local/app.sqlite3`. No dependency installation is required. `--database /absolute/path.sqlite3` (alias `--db`) can select a separate development/test database. New app-owned database files are created with mode `0600`; existing file/directory permissions are not modified.

Every registration is an ordinary user, including the first account. The public application does not ship management functionality. An optional owner-controlled local extension may add capabilities to authorized sessions; its implementation, commands and records are not distributed in this repository.

This is an account-backed local application, not an online identity service: there is no email verification, password recovery, HTTPS endpoint, or remote deployment in this version.

All mutation requests use JSON (`Content-Type: application/json`). Same-origin browser requests are required. Authenticated mutation requests additionally send the `X-CSRF-Token` returned by the session endpoint. Send `{}` for logout. Password hashes and salts are never returned. Browser auth routes keep session tokens in HttpOnly cookies; the explicitly named native mobile auth routes return the session token in JSON for OS credential-vault storage.

Errors use an appropriate HTTP status and `{ "error": { "code": "...", "message": "..." } }`.

## Session shape

Successful registration/login and `GET /api/session` return:

```json
{
  "user": {
    "id": "32-character-hex-id",
    "username": "researcher",
    "displayName": "研究者",
    "role": "user",
    "active": true,
    "createdAt": "2026-10-28T00:00:00+00:00"
  },
  "csrfToken": "opaque-per-session-value",
  "state": {
    "favorites": [],
    "reminders": [],
    "settings": {
      "theme": "system",
      "fontSize": "standard",
      "timezone": "Asia/Singapore",
      "sound": false,
      "reducedMotion": false
    },
    "relax": { "woodfish": 0, "accepts": 0, "amen": 0 }
  }
}
```

An unauthenticated `GET /api/session` returns HTTP 200 with `{"user":null,"csrfToken":null,"state":null}`. All other protected endpoints return HTTP 401 when the session is absent, expired, revoked, or disabled.

## Endpoints

| Method / path | Input | Result |
|---|---|---|
| `POST /api/auth/register` | `{username, displayName?, password}` | HTTP 201, session shape; sets cookie |
| `POST /api/auth/login` | `{username, password}` | HTTP 200, session shape; sets cookie |
| `POST /api/mobile/auth/register` | `{username, displayName?, password}` | HTTP 201, session shape plus `sessionToken`; does not set a cookie |
| `POST /api/mobile/auth/login` | `{username, password}` | HTTP 200, session shape plus `sessionToken`; does not set a cookie |
| `GET /api/session` | — | Session shape |
| `POST /api/auth/logout` | `{}` | `{ok:true}`; revokes current session and clears cookie |
| `PATCH /api/profile` | `{displayName}` | `{user}` |
| `POST /api/password` | `{currentPassword,newPassword}` | `{ok:true,requiresLogin:true}`; revokes **all** sessions |
| `POST /api/account/delete` | `{currentPassword}` | `{ok:true,requiresLogin:true}`; deletes own account/state, revokes **all** sessions and clears cookie |
| `PUT /api/state` | Any subset of `{favorites,reminders,settings,relax}` | `{state}` after merge |
| `POST /api/relax/increment` | Any nonempty subset of `{woodfish:delta,accepts:delta,amen:delta}` | `{relax}` after atomic accumulation |
| `GET /api/community/stats` | — | `{woodfishTotal,startedAt,scope:"instance",instanceId}`; public, no personal data |
| `POST /api/community/woodfish` | `{streamId,total,instanceId}` | Public stats plus `acceptedTotal`; anonymous cumulative tap reporting |

Registration/login replaces and revokes the old session associated with the current browser cookie. Other browsers' sessions remain active unless the password is changed or the account is disabled.

## Shared woodfish totals

The public counter is independent of `/api/relax/increment` and personal state. It starts at zero when the feature is enabled, without importing older guest/account counts. A random UUID stream reports its cumulative total, and an immediate SQLite transaction adds only the amount above its stored high-water mark. Duplicate/out-of-order requests therefore do not add twice. The counter and unlinked stream high-water marks survive account deletion and service restarts. Neither public response exposes user identities or registration numbers.

`streamId` and `instanceId` are lowercase, hyphenated UUID strings. `total` is a nonnegative integer up to 1,000,000,000; a request can add at most 1,000. The database instance must match inside the write transaction, so replacing the database cannot silently import an old instance's pending taps. The browser creates an independent stream per page, rotating at 1,000 taps, and keeps an outbox plus separate acknowledgement keys in local storage. Public requests omit login cookies; old private counters are not uploaded. Lost responses can be retried; clearing browser storage can lose unsent taps.

The service limits each stream to 1,000 new taps per minute and each salted address bucket to 100 new nonzero streams per hour. Duplicate/zero writes do not consume the new-stream allowance. The public mutation requires JSON and passes the same Host/Origin validation, but needs no account or CSRF token because it cannot modify personal state. It is an entertainment counter with basic throttling, not a unique-person or fraud-proof metric.

Each deployment/database counts separately; sharing across future website/App clients requires one common backend, which has not been publicly deployed. The public API contains no account-count or user-list endpoint.

## Compatibility routes

The previously implemented native authentication routes remain available for compatibility; the maintained application is now the webpage. They share the same account, password, throttling and session store. Clients send `Authorization: Bearer <sessionToken>` and still require `X-CSRF-Token` on authenticated mutations. Bearer authentication does not bypass Host/Origin checks, and an invalid Authorization header never falls back to cookies. Only the two explicitly named `/api/mobile/auth/` routes return raw tokens; browser routes use HttpOnly cookies. Logout, password changes, account disabling and account deletion revoke these sessions as well.

## Account deletion

`POST /api/account/delete` accepts exactly `{currentPassword}` and always acts on the authenticated user, never a supplied target ID. A valid session, matching CSRF token, same-origin request and correct current password are all required. A wrong password returns HTTP 401 with `wrong_password`; this is **not** a session invalidation signal. Clients must preserve the current signed-in state in this case.

Deletion removes the user's row, saved favorites/settings/reminders/relax counts, account-specific login-attempt bucket and all sessions in one transaction. Other accounts and browser-local guest data are unchanged. The username can be registered again afterward, receiving a new user ID, empty state and ordinary-user role. There is no public endpoint for deleting other accounts.

The frontend must clearly describe the irreversible account/state deletion and request the current password before submitting. Successful deletion clears the cookie and should return to guest state. This is logical deletion from the active SQLite database, not a claim of forensic disk erasure or deletion from independently maintained backups.

## Validation and state merge

- Username: NFC-normalized, 3–32 Unicode alphanumeric characters or `_ . -`; case-insensitive uniqueness.
- Password: 10–128 characters, not all whitespace. Stored with an independent random 16-byte salt and PBKDF2-HMAC-SHA256, 600,000 iterations.
- Display name: trimmed 1–40 characters, no Unicode control characters.
- Favorites: at most 1,000 conference IDs, each 1–100 ASCII letters/digits/underscore/hyphen; duplicate IDs are removed, preserving order.
- Reminders: at most 200 records; each record has exactly `id`, `conferenceId`, `trackName`, `kind`, `deadline`, `leadMinutes`, and `enabled`. IDs are unique within an account, 1–160 ASCII letters/digits/underscore/dot/colon/hyphen beginning with a letter or digit. Conference IDs follow the favorites format. Track names are nonblank, at most 200 characters, and contain no Unicode control characters. `kind` is `abstract` or `full`; `deadline` is a valid timezone-aware ISO date/time (including `Z` or an explicit offset); `leadMinutes` is an integer from `0, 5, 60, 180, 1440, 4320, 10080`; `enabled` is a boolean. A reminder list replaces the current account's entire list; `[]` removes its configurations. Unknown fields, duplicate IDs, missing timezones, and invalid dates are rejected atomically.
- `settings.theme`: `system`, `light`, or `dark`.
- `settings.fontSize`: `standard`, `large`, or `extra`.
- `settings.timezone`: `Asia/Singapore`, `UTC`, or `America/Los_Angeles`.
- `settings.sound` and `settings.reducedMotion`: booleans.
- `relax.woodfish`, `relax.accepts`, `relax.amen`: integers from 0 to 1,000,000,000.
- `/api/relax/increment` accepts nonnegative integer deltas with a sum of at most 1,000 per request. A SQLite write transaction serializes concurrent requests, preserving all taps from multiple tabs and leaving favorites/settings untouched. Use this endpoint for gameplay; use partial `PUT /api/state` updates for settings and favorites. Incrementing above the cumulative 1,000,000,000 limit returns HTTP 400.
- Unknown fields or invalid values return HTTP 400. Top-level state fields and nested settings/relax fields merge with existing values. Favorites and reminders each replace their list when supplied; omitted fields remain untouched. Legacy stored states receive new defaults (`reminders: []`) and missing nested defaults on read without losing existing values; the next state write persists the merged shape. JSON request bodies are bounded at 256 KiB.

## Reminder configuration and delivery boundary

The web UI uses `POST /api/state/sync` for concurrent list edits. The optional `favorites`
field has `{add: [conferenceIds], remove: [conferenceIds]}` and the optional `reminders`
field has `{upsert: [fullReminderRecords], remove: [reminderIds]}`. The server merges
these explicit changes into current SQLite state in one write transaction and returns
`{state}`. Removing a favorite also pauses all current reminders for that conference.
This preserves changes made through WeChat since the browser last read the lists.
The endpoint requires the same authenticated session and CSRF token; ordinary
`PUT /api/state` retains its existing full-list replacement semantics.

Example partial state update:

```json
{
  "reminders": [{
    "id": "cvpr-main-abstract-1440",
    "conferenceId": "cvpr",
    "trackName": "Main Conference",
    "kind": "abstract",
    "deadline": "2026-11-10T23:59:00-12:00",
    "leadMinutes": 1440,
    "enabled": true
  }]
}
```

The record stores a user's chosen deadline snapshot, not a new authoritative conference fact. The frontend selects from verified conference data and reconciles source changes before delivery. Configurations persist in the account database and survive server restart. They are protected by the same session/CSRF checks and account isolation as favorites.

Saving this API configuration alone does not send messages. Browser delivery and local deduplication are handled by the frontend while it is running; exported calendar alarms depend on the user's calendar application. No notification permission is granted by saving a configuration. An optional WeChat binding, separately enabled for DDL push, adds a Python background scheduler. It runs only while the local service/computer/network remain available and does not promise phone notification delivery.

## WeChat bridge

`GET /api/wechat/status` returns only the current account's redacted binding/login state and recent delivery metadata. All mutations below require authentication, same-origin JSON and CSRF:

| Endpoint | Body / behavior |
| --- | --- |
| `POST /api/wechat/chat` | `{text}`; local command preview, saves current account changes, returns `{text,state,preview:true}`; sends nothing to WeChat |
| `POST /api/wechat/login` | `{}`; explicitly requests a QR challenge; expires locally after 5 minutes |
| `POST /api/wechat/login/poll` | `{}` or `{verifyCode}`; verifies scanner identity and saves unique account binding |
| `POST /api/wechat/login/cancel` | `{}`; discards pending local challenge |
| `PATCH /api/wechat/settings` | `enabled` and/or `pushEnabled` booleans; push defaults off |
| `POST /api/wechat/disconnect` | `{}`; removes local credentials, preserves conference state; not a provider-side revocation |

The scanner ID is the only allowed sender. SQLite inbox/delivery keys prevent automatic duplicate execution/sends; database worker leases avoid competing pollers. Unknown send outcomes are not automatically retried. Only `ret:0` is marked `accepted`, which is not a delivery receipt. The scheduler reconciles source dates, ignores unfavorited/disabled reminders, and skips triggers before startup or more than two minutes late. Credentials and peer IDs never appear in the public status API or request logs. QR SVGs are generated locally. See [the setup and validation boundaries](wechat.md).

Inbound commands are persisted to `wechat_commands` before their provider cursor is advanced.
Account mutations and their prepared reply are committed in one transaction. On reconnect,
the worker resumes queued commands or sends prepared replies that were never claimed for
delivery. A previously claimed `sending` outcome is considered uncertain, not retried;
an already accepted delivery is not repeated. Paused/disabled/replaced bindings cannot
resume work. Unexecuted mutations more than 24 hours old require the user to resend;
this application rule is not a statement about WeChat token TTL. The queue is bounded at
100 pending commands per binding, receives at most 30 new commands per minute, and
drains in received order. A deferred batch does not advance the provider cursor.

The private local queue contains original commands and prepared response text while pending;
both text fields are cleared after a terminal result. The status API exposes only the
`pendingCommands` count, never those bodies. Unbinding or account deletion cascades the
queue. The web UI no longer renders delivery history, but internal metadata remains for
deduplication. Messages never received before shutdown depend on provider retention and
are not guaranteed to be recoverable. A valid WeChat session is still needed to send
resumed responses; no guarantee of phone delivery is implied.

## Security and deployment boundary

- Sessions are random 256-bit tokens stored only as SHA-256 digests in SQLite. They expire after seven days; passwords and account disabling revoke sessions.
- Session cookies use `HttpOnly`, `SameSite=Strict`, and `Path=/`. They intentionally omit `Secure` for local plain-HTTP loopback use. A remote deployment must use HTTPS and secure cookies; changing the bind address is rejected by this implementation.
- Host validation mitigates DNS rebinding. Origin/Sec-Fetch-Site validation, JSON-only mutation requests, and per-session CSRF tokens protect state-changing endpoints. No permissive CORS is enabled.
- Five failed login attempts per account in a five-minute window produce HTTP 429; an additional address-wide 40-attempt window bounds distributed-username attempts. Successful login clears that account's failed-attempt bucket.
- Only explicitly allowed static app files are served, including named assets `woodfish.jpg`, `a-men-cat.jpg`, `wood-knock.wav` and the relax/reminder modules. The rest of `assets/` is not automatically exposed. Hidden directories, SQLite files, research/source records, path traversal, and symlinks (including those targeting another file inside the root) are blocked.
- Users may permanently delete their own account only after current-password verification. The public API cannot change another account or grant roles.
- Without a WeChat binding the app sends no account data to an external service. After explicit binding, incoming queries, responses and enabled DDL reminders travel through WeChat. Bot tokens/context are stored as usable credentials in the private local database, not hashes; do not share it. Credentials are never logged; request logging is disabled. Password changes revoke local WeChat bindings, and account deletion cascades the binding and delivery metadata.

## Validation

Run `python3 -m unittest discover -s tests -v`. Tests create a temporary directory, temporary users, temporary SQLite database, and an ephemeral loopback HTTP port, and clean them up afterward. They do not create real user accounts in the project database.

HTTP tests cover browser and compatibility bearer sessions, deletion guards and account isolation, state persistence, reminder validation, simultaneous relax increments and the exact static-file allowlist. They do not replace browser interaction checks or validate a remote production deployment.
