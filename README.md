# WOOW LINE Base

**Odoo 18 LINE Platform Integration -- Foundation Module**

| Field     | Value                                              |
|-----------|----------------------------------------------------|
| Name      | WOOW LINE Base                                     |
| Technical | `woow_line_base`                                   |
| Version   | 18.0.3.1.0                                         |
| Category  | Marketing                                          |
| Author    | WOOWTECH                                           |
| License   | LGPL-3                                             |
| Website   | https://woowtech.io                                |
| Depends   | `base`                                             |
| Python    | `requests`                                         |
| Application | Yes                                              |

---

## Overview

`woow_line_base` is the **foundation layer** of a three-module LINE integration
suite for Odoo 18 Community Edition. It provides:

1. A **unified LINE Messaging API client** (`line.api.service`) that supports both
   global credentials and per-channel OAuth2 tokens.
2. A **LINE user identity model** (`line.user`) with weak association to
   `res.partner`, bidirectional email sync, and automatic partner binding.
3. A **manual partner-binding wizard** (`line.bind.partner.wizard`).

The two higher-level modules build on this base:

```
+---------------------------------+
| woow_odoo_livechat_line         |  LiveChat bridge (Odoo Discuss)
|   depends: im_livechat,         |
|            woow_line_base       |
+---------------------------------+
          |
+---------------------------------+
| woow_odoo_line_liff             |  LIFF login, Rich Menu UI, News push,
| (a.k.a. woow_line_bridge)      |  Audience tags, Insight stats, Webhook
|   depends: woow_line_base,      |
|            website, portal      |
+---------------------------------+
          |
+---------------------------------+
| woow_line_base  (THIS)          |  Core: LINE API client + user identity
|   depends: base                 |
+---------------------------------+
```

`woow_line_base` is a **pure data + API module** -- it has no controllers, no
frontend assets, and no dependency on `website` or `mail`. Upstream modules
call into `line.api.service` and `line.user` via standard ORM.

---

## Installation

### 1. Place the module

Copy (or symlink) the `woow_line_base` directory into your Odoo 18 addons path:

```bash
cp -r woow_line_base /opt/odoo/addons/
```

### 2. Install Python dependency

```bash
pip install requests
```

### 3. Update the module list and install

```
Settings > Apps > Update Apps List > search "WOOW LINE Base" > Install
```

Or via CLI:

```bash
odoo -d mydb -u woow_line_base --stop-after-init
```

### 4. Post-install hook

The module runs `_post_init_hook` on installation to clean up a legacy
`group_line_user` group (hides it from the user form and removes
`implied_ids`). No manual action required.

---

## Configuration

All credentials are stored as `ir.config_parameter` keys. Set them via
**Settings > Technical > Parameters > System Parameters** or via XML/Python:

| Key                                        | Purpose                                  | Example                       |
|--------------------------------------------|------------------------------------------|-------------------------------|
| `woow_line_base.messaging_access_token`    | Long-lived Channel Access Token          | `abc123...`                   |
| `woow_line_base.messaging_channel_id`      | Messaging API Channel ID                 | `1234567890`                  |
| `woow_line_base.messaging_channel_secret`  | Messaging API Channel Secret             | `abcdef0123456789`            |
| `woow_line_base.login_channel_id`          | LINE Login Channel ID (for LIFF)         | `9876543210`                  |
| `woow_line_base.login_channel_secret`      | LINE Login Channel Secret                | `fedcba9876543210`            |

**Dual-credential mode:**

- **Global mode** (default) -- the module reads from the five system parameters
  above. Suitable for single-LINE-account deployments.
- **Per-channel mode** -- pass `channel_id` and `channel_secret` explicitly to
  any `line.api.service` method. The service will issue an OAuth2
  `client_credentials` grant and cache the token in memory. Suitable for
  multi-tenant or multi-LINE-account deployments.

---

## File Structure

```
woow_line_base/
|-- __init__.py                          # Package init + _post_init_hook
|-- __manifest__.py                      # Module manifest
|
|-- data/
|   `-- ir_config_parameter.xml          # 5 credential stubs
|
|-- models/
|   |-- __init__.py
|   |-- line_api_service.py              # AbstractModel: unified LINE API client
|   |-- line_user.py                     # Model: LINE user identity
|   |-- res_config_settings.py           # (empty -- settings delegated to bridge modules)
|   `-- res_partner.py                   # Inherit: res.partner with One2many + email sync
|
|-- security/
|   |-- ir.model.access.csv             # ACL: line.user + wizard for group_line_manager
|   `-- line_security.xml               # Security group: group_line_manager
|
|-- static/
|   `-- description/
|       |-- icon.png                     # Module icon
|       `-- line_icon.png                # LINE brand icon
|
|-- tests/
|   `-- __init__.py                      # Test package (placeholder)
|
|-- views/
|   |-- line_user_views.xml              # List / Form / Search views for line.user
|   |-- menus.xml                        # Top-level LINE menu (group_line_manager)
|   |-- res_config_settings_views.xml    # Placeholder (empty arch)
|   `-- res_partner_views.xml            # Placeholder (empty arch)
|
`-- wizard/
    |-- __init__.py
    |-- line_bind_partner_wizard.py      # TransientModel: manual partner binding
    `-- line_bind_partner_wizard_views.xml
```

---

## Architecture

### `line.api.service` (AbstractModel)

Technical name: `line.api.service`

An `AbstractModel` (no database table). All LINE Platform API calls go through
this service. Any Odoo model can access it via:

```python
svc = self.env['line.api.service']
svc.push_message('U1234...', [svc.build_text_message('Hello!')])
```

#### LINE API Endpoints (Constants)

```python
LINE_TOKEN_URL             = 'https://api.line.me/v2/oauth/accessToken'
LINE_VERIFY_URL            = 'https://api.line.me/oauth2/v2.1/verify'
LINE_PROFILE_URL           = 'https://api.line.me/v2/bot/profile'
LINE_PUSH_URL              = 'https://api.line.me/v2/bot/message/push'
LINE_MULTICAST_URL         = 'https://api.line.me/v2/bot/message/multicast'
LINE_BROADCAST_URL         = 'https://api.line.me/v2/bot/message/broadcast'
LINE_REPLY_URL             = 'https://api.line.me/v2/bot/message/reply'
LINE_CONTENT_URL           = 'https://api-data.line.me/v2/bot/message'
LINE_RICHMENU_URL          = 'https://api.line.me/v2/bot/richmenu'
LINE_RICHMENU_CONTENT_URL  = 'https://api-data.line.me/v2/bot/richmenu'
LINE_RICHMENU_ALIAS_URL    = 'https://api.line.me/v2/bot/richmenu/alias'
LINE_NARROWCAST_URL        = 'https://api.line.me/v2/bot/message/narrowcast'
LINE_INSIGHT_DELIVERY_URL  = 'https://api.line.me/v2/bot/insight/message/delivery'
LINE_INSIGHT_FOLLOWERS_URL = 'https://api.line.me/v2/bot/insight/followers'
LINE_INSIGHT_MESSAGE_EVENT_URL = 'https://api.line.me/v2/bot/insight/message/event'
LINE_QUOTA_URL             = 'https://api.line.me/v2/bot/message/quota'
LINE_QUOTA_CONSUMPTION_URL = 'https://api.line.me/v2/bot/message/quota/consumption'
LINE_AUDIENCE_URL          = 'https://api.line.me/v2/bot/audienceGroup/upload'
```

#### API Methods Reference

All public methods accept optional `access_token`, `channel_id`, and
`channel_secret` keyword arguments for per-channel credential override.
When omitted, the global `ir.config_parameter` values are used.

##### Token Management

| Method | Signature | Returns | Description |
|--------|-----------|---------|-------------|
| `get_access_token` | `(channel_id=None, channel_secret=None)` | `str` or `None` | Get access token. Global (from config) or per-channel (via OAuth2). |
| `_get_token_oauth` | `(channel_id, channel_secret)` | `str` or `None` | OAuth2 `client_credentials` grant with in-memory cache. Refreshes 5 minutes before expiry. |
| `verify_id_token` | `(id_token, login_channel_id=None)` | `dict` or `None` | Verify a LIFF ID Token against LINE's `/oauth2/v2.1/verify` endpoint. Returns decoded payload. |
| `verify_access_token` | `(access_token)` | `dict` or `None` | Fallback: verify LIFF access token and fetch profile. Returns `{sub, name, picture}`. |

##### Messaging

| Method | Signature | Returns | Description |
|--------|-----------|---------|-------------|
| `push` | `(line_users, messages, ...)` | `list[int]` | Push messages to a `line.user` recordset. Filters out blocked/unfollowed/notification-disabled users. Writes to `line.push.log`. Returns list of successful `line.user` IDs. |
| `push_message` | `(line_uid, messages, ...)` | `bool` | Low-level push to a LINE User ID string. No logging, no filtering. |
| `reply` | `(reply_token, messages, ...)` | `bool` | One-time reply using a webhook reply token. |
| `multicast` | `(line_user_ids_list, messages, ...)` | `bool` | Batch push to a list of LINE User ID strings. Automatically chunks into batches of 500. |
| `broadcast` | `(messages, ...)` | `bool` | Broadcast to all followers of the LINE Official Account. |
| `narrowcast` | `(messages, recipient=None, demographic_filter=None, ...)` | `str` (request_id) or `None` | Targeted push by audience group or demographic filter. Returns the LINE request ID on success (HTTP 202). |

##### Message Builders

| Method | Signature | Returns | Description |
|--------|-----------|---------|-------------|
| `build_text_message` | `(text)` | `dict` | `{'type': 'text', 'text': ...}` |
| `build_image_message` | `(original_url, preview_url=None)` | `dict` | Image message. `preview_url` defaults to `original_url`. |
| `build_video_message` | `(original_url, preview_url)` | `dict` | Video message (both URLs required). |
| `build_audio_message` | `(original_url, duration_ms)` | `dict` | Audio message with duration in milliseconds. |
| `build_file_message` | `(filename, file_url, file_size=None)` | `dict` | Flex Message "kilo" bubble simulating a file download card. Shows file extension badge, filename, and human-readable size. |

##### Rich Menu

| Method | Signature | Returns | Description |
|--------|-----------|---------|-------------|
| `richmenu_create` | `(menu_data, ...)` | `str` (richMenuId) or `None` | Create a Rich Menu. `menu_data` must include `size`, `selected`, `name`, `chatBarText`, `areas`. |
| `richmenu_upload_image` | `(richmenu_id, image_data, content_type='image/png', ...)` | `bool` | Upload the image for a Rich Menu. Accepts PNG or JPEG bytes. |
| `richmenu_set_default` | `(richmenu_id, ...)` | `bool` | Set a Rich Menu as the default for all users. |
| `richmenu_clear_default` | `(...)` | `bool` | Remove the default Rich Menu. |
| `richmenu_link_to_user` | `(richmenu_id, line_user_id, ...)` | `bool` | Link a Rich Menu to a specific user. |
| `richmenu_unlink_from_user` | `(line_user_id, ...)` | `bool` | Unlink the Rich Menu from a specific user. |
| `richmenu_link_to_users` | `(richmenu_id, line_user_ids, ...)` | `bool` | Batch link a Rich Menu to up to 500 users at once. Expects HTTP 202. |
| `richmenu_delete` | `(richmenu_id, ...)` | `bool` | Delete a Rich Menu by ID. |
| `richmenu_get_user_menu` | `(line_user_id, ...)` | `str` (richMenuId) or `None` | Get the Rich Menu currently linked to a user. |
| `richmenu_create_alias` | `(alias_id, richmenu_id, ...)` | `bool` | Create a Rich Menu Alias (used for tab switching). |
| `richmenu_update_alias` | `(alias_id, richmenu_id, ...)` | `bool` | Update the target Rich Menu of an alias. |
| `richmenu_delete_alias` | `(alias_id, ...)` | `bool` | Delete a Rich Menu Alias. |

##### Analytics (Insight)

| Method | Signature | Returns | Description |
|--------|-----------|---------|-------------|
| `get_insight_delivery` | `(date_str, ...)` | `dict` or `None` | Delivery stats for a date. `date_str` must be in `yyyyMMdd` format. |
| `get_insight_followers` | `(date_str, ...)` | `dict` or `None` | Follower count stats for a date. `date_str` in `yyyyMMdd` format. |
| `get_insight_message_event` | `(request_id, ...)` | `dict` or `None` | User interaction stats (impressions, clicks) for a push identified by `request_id`. |

##### Quota

| Method | Signature | Returns | Description |
|--------|-----------|---------|-------------|
| `get_quota` | `(...)` | `dict` or `None` | Monthly message quota. Returns `{'type': 'limited'|'none', 'value': int}`. |
| `get_quota_consumption` | `(...)` | `dict` or `None` | Current month usage. Returns `{'totalUsage': int}`. |

##### Audience

| Method | Signature | Returns | Description |
|--------|-----------|---------|-------------|
| `audience_create` | `(description, user_ids, ...)` | `int` (audienceGroupId) or `None` | Create an audience group by uploading LINE User IDs. Accepts HTTP 200 or 202. |
| `audience_add_users` | `(audience_group_id, user_ids, ...)` | `bool` | Add users to an existing audience group via PUT. |
| `audience_delete` | `(audience_group_id, ...)` | `bool` | Delete an audience group. |

##### Webhook Security

| Method | Signature | Returns | Description |
|--------|-----------|---------|-------------|
| `verify_webhook_signature` | `(body_bytes, signature_header, channel_secret=None)` | `bool` | Verify the `X-Line-Signature` header using HMAC-SHA256. Falls back to global channel secret if not provided. |

##### Media & Profile

| Method | Signature | Returns | Description |
|--------|-----------|---------|-------------|
| `get_content` | `(message_id, ...)` | `(bytes, str)` or `(None, None)` | Download media content (image/video/audio/file). Returns `(data, content_type)`. |
| `get_profile` | `(line_user_id, ...)` | `dict` or `{}` | Fetch a user's LINE profile. Returns `{userId, displayName, pictureUrl, statusMessage}`. |

---

### `line.user` Model

Technical name: `line.user`

Represents a LINE user identity. Each record is uniquely identified by
`line_user_id` (LINE UID). Optionally associated with a `res.partner` via a
weak Many2one (`ondelete='set null'`).

#### Fields

| Field | Type | Label (Chinese) | Description |
|-------|------|------------------|-------------|
| `line_user_id` | `Char` | LINE User ID | **Required, Unique, Indexed.** The LINE platform UID (`U` prefix). |
| `display_name` | `Char` | 顯示名稱 | LINE display name. Also used as `_rec_name`. |
| `picture_url` | `Char` | 頭像網址 | URL to LINE profile picture. |
| `status_message` | `Char` | 狀態訊息 | LINE status message. |
| `email` | `Char` | Email | Email from LIFF ID Token or manual entry. Bidirectionally synced with `partner_id.email`. |
| `messaging_channel_id` | `Char` | Messaging Channel ID | The LINE Messaging API Channel this user originates from. Indexed. |
| `messaging_channel_name` | `Char` | Messaging Channel | Human-readable channel name. |
| `partner_id` | `Many2one(res.partner)` | 聯絡人 | Weak association. `ondelete='set null'`. Indexed. |
| `is_follower` | `Boolean` | 追蹤中 | Whether the user currently follows the LINE OA. Default `True`. |
| `is_blocked` | `Boolean` | 已封鎖 | Whether the user has been blocked. Default `False`. |
| `notification_enabled` | `Boolean` | 啟用通知 | Whether push notifications are enabled. Default `True`. |
| `follow_date` | `Datetime` | 追蹤時間 | When the user first followed. |
| `unfollow_date` | `Datetime` | 取消追蹤時間 | When the user unfollowed. |
| `last_login` | `Datetime` | 最後登入 | Last LIFF login timestamp. |
| `bound_at` | `Datetime` | 綁定時間 | When `partner_id` was bound. |
| `preferred_lang` | `Selection` | 偏好語言 | `zh_TW` (default), `en_US`, or `ja_JP`. |
| `push_count` | `Integer` | 推播次數 | Total successful pushes to this user. Default `0`. |
| `event_count` | `Integer` | 事件次數 | Total webhook events from this user. Default `0`. |

Default ordering: `last_login desc, create_date desc`

SQL constraint: `UNIQUE(line_user_id)`

#### Methods

| Method | Signature | Returns | Description |
|--------|-----------|---------|-------------|
| `find_by_line_uid` | `(line_user_id)` | `line.user` recordset | Search by LINE UID. Returns empty recordset if not found. `@api.model`. |
| `create_or_update_from_webhook` | `(line_user_id, profile_data=None, messaging_channel_id=None, messaging_channel_name=None)` | `line.user` record | Webhook flow: find-or-create a LINE user, update profile data, set `is_follower=True`, auto-bind partner. `@api.model`. |
| `create_or_update_from_liff` | `(id_token_payload)` | `line.user` record | LIFF flow: find-or-create from ID Token payload (`sub`, `name`, `picture`, `email`). Sets `last_login`. `@api.model`. |
| `bind_partner` | `(partner_id)` | `bool` | Bind to a `res.partner`. Syncs email bidirectionally, updates `bound_at`, syncs to `mail.guest` if available. |
| `unbind` | `()` | `bool` | Clear `partner_id` and `bound_at`. Also clears `mail.guest` link. |
| `_auto_bind_or_create_partner` | `(line_user)` | `None` | Auto-binding strategy: (1) skip if already bound or `skip_auto_bind` in context; (2) match by email; (3) create new partner. `@api.model`. |
| `_sync_to_mail_guest` | `(partner_id)` | `None` | Sync partner binding to `mail.guest` records (only if `woow_odoo_livechat_line` is installed and `mail.guest` has `line_user_id` field). |
| `action_bind_partner` | `()` | `dict` | View button: opens the `line.bind.partner.wizard` in a dialog. |

#### Email Bidirectional Sync

The `write` method on `line.user` is overridden. When `email` changes:

1. `line.user.email` --> `partner.email` (if partner is bound and emails differ)
2. `partner.email` --> `line.user.email` (via `res.partner.write` override)

Both directions use `context={'skip_email_sync': True}` to prevent infinite
recursion. See the "For AI Agents" section for how to suppress this behavior.

---

### `res.partner` Extension

The `res.partner` model gains:

| Field | Type | Description |
|-------|------|-------------|
| `line_user_ids` | `One2many(line.user, partner_id)` | All LINE accounts associated with this contact. |

The `write` method is overridden to propagate email changes to all linked
`line.user` records (reverse sync).

---

### `line.bind.partner.wizard` (TransientModel)

A simple wizard for manually binding a `line.user` to a `res.partner`:

| Field | Type | Description |
|-------|------|-------------|
| `line_user_id` | `Many2one(line.user)` | The LINE user to bind (readonly, set from context). |
| `partner_id` | `Many2one(res.partner)` | The partner to bind to. Supports search and create. |

Single action: `action_bind()` -- delegates to `line_user.bind_partner(partner_id)`.

---

## Security

### Groups

| XML ID | Name | Description |
|--------|------|-------------|
| `woow_line_base.group_line_manager` | LINE 管理者 | Full CRUD access on `line.user` and `line.bind.partner.wizard`. Assigned to `base.user_root` and `base.user_admin` by default. |

### Access Control (ir.model.access.csv)

| Model | Group | Read | Write | Create | Delete |
|-------|-------|------|-------|--------|--------|
| `line.user` | `group_line_manager` | Yes | Yes | Yes | Yes |
| `line.bind.partner.wizard` | `group_line_manager` | Yes | Yes | Yes | Yes |

### Webhook Verification

All webhook controllers (provided by upstream modules) should call:

```python
svc = request.env['line.api.service'].sudo()
if not svc.verify_webhook_signature(request.httprequest.data,
                                     request.httprequest.headers.get('X-Line-Signature'),
                                     channel_secret):
    raise Forbidden()
```

This performs HMAC-SHA256 verification per the LINE Platform specification.

---

## Menus

The module creates a top-level **LINE** menu in the Odoo backend, visible only
to `group_line_manager` members:

```
LINE (top-level, icon: static/description/icon.png)
  +-- LINE 用戶 (list/form of line.user, default filter: followers)
```

Upstream modules (LINE Bridge, LiveChat LINE) add their own sub-menus under
this root.

---

## For AI Agents

This section describes how to use `woow_line_base` programmatically from other
Odoo modules, scheduled actions, or server actions.

### Accessing the API Service

```python
svc = self.env['line.api.service']
```

`line.api.service` is an `AbstractModel` -- it has no database records. You call
methods directly on the model proxy. It always operates in the current user's
environment unless you explicitly `.sudo()`.

### Common Patterns

#### Push a text message to a LINE user

```python
svc = self.env['line.api.service']
line_user = self.env['line.user'].find_by_line_uid('U1234567890abcdef...')
if line_user:
    svc.push(line_user, [svc.build_text_message('Hello from Odoo!')])
```

The `push()` method:
- Accepts a `line.user` **recordset** (can contain multiple users)
- Automatically skips blocked, unfollowed, and notification-disabled users
- Writes to `line.push.log` (if the model exists -- provided by upstream modules)
- Increments `push_count` on each successfully pushed user
- Returns a list of `line.user` IDs that were successfully sent

#### Push without filtering (low-level)

```python
svc = self.env['line.api.service']
success = svc.push_message('U1234567890abcdef...', [
    svc.build_text_message('Direct push'),
])
```

This bypasses all filtering and logging. Use for system-level messages.

#### Send an image

```python
svc = self.env['line.api.service']
msg = svc.build_image_message(
    'https://example.com/photo.jpg',
    'https://example.com/photo_thumb.jpg',
)
svc.push(line_users, [msg])
```

#### Send a file download card

```python
svc = self.env['line.api.service']
msg = svc.build_file_message('report.pdf', 'https://example.com/report.pdf', 1048576)
svc.push(line_users, [msg])
```

This renders as a Flex Message "kilo" bubble with a file extension badge,
filename, and human-readable size (e.g., "1.0 MB").

#### Broadcast to all followers

```python
svc = self.env['line.api.service']
svc.broadcast([svc.build_text_message('Announcement for everyone!')])
```

#### Multicast to a specific list of LINE UIDs

```python
svc = self.env['line.api.service']
uids = ['U111...', 'U222...', 'U333...']
svc.multicast(uids, [svc.build_text_message('Group message')])
# Automatically batches in groups of 500
```

#### Use per-channel credentials

```python
svc = self.env['line.api.service']
token = svc.get_access_token(channel_id='1234567890', channel_secret='abcdef...')
svc.push_message('U1234...', [svc.build_text_message('Hello')],
                 access_token=token)
```

Or let each method resolve the token internally:

```python
svc.push_message('U1234...', [svc.build_text_message('Hello')],
                 channel_id='1234567890', channel_secret='abcdef...')
```

#### Verify a LIFF login

```python
svc = self.env['line.api.service']
payload = svc.verify_id_token(id_token_from_liff)
if payload:
    line_user = self.env['line.user'].create_or_update_from_liff(payload)
```

#### Create or update a user from a webhook event

```python
line_user = self.env['line.user'].create_or_update_from_webhook(
    'U1234567890abcdef...',
    profile_data={'displayName': 'John', 'pictureUrl': 'https://...'},
    messaging_channel_id='9999999999',
    messaging_channel_name='My LINE OA',
)
```

### Extending with New API Methods

To add a new LINE API endpoint, add a method to `line.api.service` via
inheritance:

```python
from odoo import models

class LineApiServiceExtend(models.AbstractModel):
    _inherit = 'line.api.service'

    def my_new_api_call(self, param, access_token=None, channel_id=None, channel_secret=None):
        token = self._resolve_token(access_token, channel_id, channel_secret)
        if not token:
            return None
        try:
            resp = http_requests.get(
                'https://api.line.me/v2/bot/some/endpoint',
                headers=self._auth_headers(token),
                params={'key': param},
                timeout=10,
            )
            if resp.status_code == 200:
                return resp.json()
        except http_requests.RequestException:
            _logger.exception('my_new_api_call failed')
        return None
```

Follow this pattern:
1. Accept optional `access_token`, `channel_id`, `channel_secret`.
2. Call `self._resolve_token(...)` to get the bearer token.
3. Use `self._auth_headers(token)` for the HTTP headers.
4. Wrap in try/except for `http_requests.RequestException`.
5. Return `None`, `False`, `{}`, or `[]` on failure -- **never raise**.

### Error Handling Conventions

All `line.api.service` methods follow a fail-safe convention:

| Return type expected | Failure value |
|----------------------|---------------|
| `str`                | `None`        |
| `dict`               | `None` or `{}` |
| `bool`               | `False`       |
| `list`               | `[]`          |
| `tuple`              | `(None, None)` |
| `int`                | `None`        |

Methods **never raise exceptions** to callers. All HTTP and parsing errors are
caught, logged via `_logger`, and converted to the appropriate failure value.
This makes the service safe to call from cron jobs and webhook handlers.

### Token Caching Behavior

- **Global tokens** (from `ir.config_parameter`) are **not cached** -- they are
  read fresh from the database on every call. This is appropriate because they
  are long-lived channel access tokens that rarely change.
- **Per-channel OAuth2 tokens** are cached **in-memory** in a module-level
  `_token_cache` dict, keyed by `channel_id`. The cache entry includes an
  `expires_at` timestamp. Tokens are refreshed **5 minutes before expiry**
  (`_TOKEN_REFRESH_BUFFER = 300` seconds).
- The in-memory cache is **per-worker-process**. In a multi-worker Odoo
  deployment, each worker maintains its own cache. This is acceptable because
  LINE OAuth2 tokens have a 30-day default lifetime.
- There is no explicit cache invalidation API. Restarting the Odoo process
  clears the cache.

### Email Sync Gotchas

The bidirectional email sync between `line.user` and `res.partner` can cause
unexpected side effects in automated scripts:

1. **Preventing infinite loops:** Both `line.user.write` and `res.partner.write`
   check for `self.env.context.get('skip_email_sync')`. The flag is set
   automatically during cross-model sync. You normally do not need to set it.

2. **Suppressing email sync in bulk operations:**
   If you are importing or bulk-updating `line.user` records and do NOT want
   email changes to propagate to partners:

   ```python
   line_users.with_context(skip_email_sync=True).write({'email': 'new@example.com'})
   ```

3. **Suppressing auto-bind during manual binding:**
   When using the wizard or performing manual partner assignment:

   ```python
   line_user.with_context(skip_auto_bind=True).write({'partner_id': some_partner.id})
   ```

   The `skip_auto_bind` context key prevents `_auto_bind_or_create_partner`
   from running and potentially creating a duplicate partner.

4. **mail.guest sync is conditional:** The `_sync_to_mail_guest` method checks
   at runtime whether the `mail.guest` model has a `line_user_id` field. This
   field is only present when `woow_odoo_livechat_line` is installed. If it is
   not installed, the sync is silently skipped.

### Dependency on `line.push.log`

The high-level `push()` method references `self.env['line.push.log']`. This
model is **not** defined in `woow_line_base` itself -- it is provided by the
upstream `woow_odoo_line_liff` (LINE Bridge) module. If you call `push()` without
the bridge module installed, it will raise a `KeyError`. In that case, use the
low-level `push_message()` method instead, or define your own `line.push.log`
model.

### Key Context Flags

| Flag | Used by | Effect |
|------|---------|--------|
| `skip_email_sync` | `line.user.write`, `res.partner.write` | Prevents bidirectional email propagation. |
| `skip_auto_bind` | `_auto_bind_or_create_partner` | Prevents automatic partner creation/matching. |
