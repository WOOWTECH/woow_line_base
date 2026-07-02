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

### Data Flow: How Upstream Modules Consume This Module

```
                     LINE Platform
                          |
                     (HTTPS REST)
                          |
              +-----------+-----------+
              |                       |
      Webhook Events           Push/Reply/etc.
              |                       ^
              v                       |
+----------------------------+        |
| woow_odoo_line_liff        |        |
| (LINE Bridge)              |        |
|   - /line/webhook          |        |
|   - News push cron         |--------+
|   - Audience management    |        |
|   - Rich Menu setup        |        |
+----------------------------+        |
              |                       |
              | ORM calls             |
              v                       |
+----------------------------+        |
| woow_odoo_livechat_line    |        |
|   - Discuss integration    |        |
|   - mail.guest bridge      |--------+
|   - Reply from Odoo UI     |        |
+----------------------------+        |
              |                       |
              | ORM calls             |
              v                       |
+============================+        |
| woow_line_base (THIS)      |        |
|                            |        |
|  line.api.service          |--------+
|    _resolve_token()        |   (all HTTP calls
|    _auth_headers()         |    go through here)
|    push / reply / etc.     |
|                            |
|  line.user                 |
|    find_by_line_uid()      |
|    create_or_update_*()    |
|    bind_partner()          |
+============================+
```

### Token Resolution Flow

```
Caller invokes any API method
  |
  |  (access_token=?, channel_id=?, channel_secret=?)
  v
_resolve_token(access_token, channel_id, channel_secret)
  |
  +-- access_token provided? ----YES----> return access_token
  |                                        (use as-is)
  |
  NO
  |
  v
get_access_token(channel_id, channel_secret)
  |
  +-- channel_id AND channel_secret? --YES--> _get_token_oauth()
  |                                             |
  |                                             +-- cached & valid? -> return cached
  |                                             |
  |                                             +-- expired/missing -> POST to
  |                                                  LINE_TOKEN_URL (OAuth2
  |                                                  client_credentials grant)
  |                                                  -> cache token -> return
  |
  NO (global mode)
  |
  v
ir.config_parameter('woow_line_base.messaging_access_token')
  |
  +-- non-empty? ----YES----> return token string
  |
  +-- empty? --------NO-----> return None  (API call will be skipped)
```

### Email Bidirectional Sync Flow

```
+------------------+                        +------------------+
|   line.user      |                        |   res.partner    |
|                  |                        |                  |
| email = "new@.." |                        | email = "old@.." |
+--------+---------+                        +--------+---------+
         |                                           |
         |  write({'email': 'new@..'})               |
         |  (skip_email_sync NOT in context)         |
         v                                           |
  line.user.write() override                         |
         |                                           |
         +-- partner_id bound?                       |
         |   YES: partner.email != new email?        |
         |         YES: partner.with_context(         |
         |                skip_email_sync=True       |
         |              ).write({'email': 'new@..'}) |
         |                        |                  |
         |                        v                  |
         |               res.partner.write()         |
         |               skip_email_sync=True        |
         |               --> NO reverse propagation  |
         |                                           |
         +-------------------------------------------+
         |                                           |
         |  (reverse direction)                      |
         |                                           |
         |               partner.write({'email': ..})|
         |               (skip_email_sync NOT set)   |
         |                        |                  |
         |                        v                  |
         |               res.partner.write() override|
         |               for lu in line_user_ids:    |
         |                 lu.with_context(           |
         |                   skip_email_sync=True    |
         |                 ).write({'email': ..})    |
         |                        |                  |
         v                        v                  |
  line.user.write()                                  |
  skip_email_sync=True                               |
  --> NO forward propagation                         |
+------------------+                        +--------+---------+
```

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

## Quick Start: Send Your First LINE Message

Follow these five steps to go from a fresh install to sending your first
LINE message via Odoo.

**Step 1.** Install the module (see Installation above) and set up your LINE
Developer Console credentials (see LINE Developer Console Setup below).

**Step 2.** Open the Odoo shell:

```bash
odoo shell -d mydb
```

**Step 3.** Look up (or create) a LINE user record. If you have already
received a webhook follow event, the user will exist:

```python
line_user = env['line.user'].sudo().search([('display_name', 'ilike', 'John')], limit=1)
print(line_user.line_user_id, line_user.display_name)
```

If no user exists yet, use a known LINE User ID (`U`-prefixed, 33 chars):

```python
line_user = env['line.user'].sudo().create({
    'line_user_id': 'U1234567890abcdef1234567890abcde',
    'display_name': 'Test User',
})
```

**Step 4.** Send a text message:

```python
svc = env['line.api.service'].sudo()
result = svc.push(line_user, [svc.build_text_message('Hello from Odoo!')])
print('Sent to IDs:', result)
```

**Step 5.** Verify the message arrived in the LINE app on the user's phone.
If `result` is an empty list, check the Odoo log for HTTP error details and
confirm your Channel Access Token is valid.

---

## LINE Developer Console Setup

This section walks through creating the required LINE channels and obtaining
the credentials that `woow_line_base` needs.

### Messaging API Channel (required)

1. Go to [LINE Developers Console](https://developers.line.biz/console/) and
   log in.
2. On the **Providers** tab, click **Create** (or select an existing provider).
3. Inside the provider, click **Create a new channel** and choose
   **Messaging API**.
4. Fill in the required fields (channel name, description, category) and
   click **Create**.
5. On the channel's **Basic settings** tab, copy:
   - **Channel ID** --> set as `woow_line_base.messaging_channel_id`
   - **Channel secret** --> set as `woow_line_base.messaging_channel_secret`
6. Go to the **Messaging API** tab, scroll to **Channel access token
   (long-lived)**, and click **Issue**. Copy the token:
   - **Channel access token** --> set as `woow_line_base.messaging_access_token`

### LINE Login Channel (required for LIFF)

1. In the same provider, click **Create a new channel** and choose
   **LINE Login**.
2. Fill in the required fields and click **Create**.
3. On the channel's **Basic settings** tab, copy:
   - **Channel ID** --> set as `woow_line_base.login_channel_id`
   - **Channel secret** --> set as `woow_line_base.login_channel_secret`
4. On the **LIFF** tab, add a LIFF app if needed by upstream modules
   (`woow_odoo_line_liff`).

### Webhook URL (configured in upstream modules)

The webhook URL is not configured in `woow_line_base` itself. Upstream
modules (`woow_odoo_line_liff`, `woow_odoo_livechat_line`) register
their own webhook controllers. Set the webhook URL on the **Messaging API**
tab of your Messaging API channel:

```
https://your-odoo-domain.com/line/webhook
```

Enable **Use webhook** and disable **Auto-reply messages** and
**Greeting messages** (these are handled by Odoo).

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

##### Internal Token Helpers

These two private methods are used by every API method internally and are
the recommended building blocks when extending the service with new
endpoints (see "Extending with New API Methods").

| Method | Signature | Returns | Description |
|--------|-----------|---------|-------------|
| `_resolve_token` | `(access_token=None, channel_id=None, channel_secret=None)` | `str` or `None` | Resolves the bearer token to use for an API call. Priority: (1) if `access_token` is provided, return it directly; (2) otherwise delegate to `get_access_token(channel_id, channel_secret)` which either reads the global config or performs an OAuth2 grant. Returns `None` if no token can be obtained. |
| `_auth_headers` | `(token)` | `dict` | Builds the HTTP headers dict required by all LINE Platform API calls. Returns `{'Content-Type': 'application/json', 'Authorization': 'Bearer <token>'}`. |

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

### LINE API Rate Limits

The LINE Platform enforces the following rate limits. All `line.api.service`
methods are subject to these limits on the server side. Exceeding them will
result in HTTP 429 responses (logged as warnings but not retried
automatically).

| API | Rate Limit | Notes |
|-----|-----------|-------|
| **Push** (`push_message`, `push`) | 200 requests/second | Per-channel limit. Each call = 1 request regardless of message count (max 5 messages per request). |
| **Multicast** (`multicast`) | 200 requests/second, max 500 users/batch | The module auto-chunks into 500-user batches. Each batch = 1 request. |
| **Broadcast** (`broadcast`) | 60 requests/hour | Sends to all followers. Use sparingly. |
| **Narrowcast** (`narrowcast`) | 60 requests/hour | Targeted push by audience or demographic filter. |
| **Reply** (`reply`) | No rate limit | Must be used within **1 minute** of receiving the webhook event. The `replyToken` expires after 1 minute and can only be used once. |
| **Rich Menu** (all `richmenu_*`) | 200 requests/second | Applies to create, delete, link, and alias operations. |
| **Profile** (`get_profile`) | 200 requests/second | Consider caching profiles in `line.user` fields rather than fetching repeatedly. |
| **Content** (`get_content`) | 200 requests/second | Media download. Large files may take longer but count as 1 request. |

**Monthly message quota:** Free plans have a monthly message limit (typically
200 or 500 free messages depending on region). Use `get_quota()` and
`get_quota_consumption()` to monitor usage programmatically.

### Token Revocation Behavior

Understanding what happens when tokens are revoked or expire is critical for
production deployments.

**Global token revocation:**

- If the long-lived Channel Access Token stored in
  `woow_line_base.messaging_access_token` is revoked (via the LINE Developer
  Console or by issuing a new long-lived token), **all API calls using global
  mode will immediately fail with HTTP 401**.
- There is **no auto-recovery** for global tokens. An administrator must
  manually issue a new token in the LINE Developer Console and update the
  `ir.config_parameter` value.
- Symptoms: every `push`, `broadcast`, `multicast`, `reply`, and profile
  fetch returns `False`/`None`/`{}`. The Odoo log will show repeated
  `401 Unauthorized` warnings.
- Recovery: issue a new long-lived token on the Messaging API tab of the
  LINE Developer Console, then update the system parameter
  `woow_line_base.messaging_access_token` in Odoo.

**Per-channel token expiry/revocation:**

- Per-channel OAuth2 tokens (obtained via `_get_token_oauth`) have a default
  lifetime of 30 days. The in-memory cache refreshes tokens **5 minutes
  before expiry** automatically.
- If a per-channel token is revoked server-side (e.g., channel secret
  rotated), the cached token will fail with 401. On the **next call** after
  the cache entry expires (based on the original `expires_at`), a fresh
  OAuth2 grant will be attempted automatically.
- To force immediate refresh, restart the Odoo worker processes (which
  clears the in-memory `_token_cache`).

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

### Cross-Module Dependency Table

The following table shows exactly which `woow_line_base` methods are called
by each upstream module. Use this as a reference when modifying method
signatures or return values.

| Upstream Module | Model Called | Method(s) Used | Purpose |
|-----------------|-------------|----------------|---------|
| `woow_odoo_line_liff` | `line.api.service` | `push`, `push_message` | Send news push notifications and manual pushes |
| `woow_odoo_line_liff` | `line.api.service` | `multicast` | Batch push to audience groups |
| `woow_odoo_line_liff` | `line.api.service` | `broadcast` | Broadcast announcements to all followers |
| `woow_odoo_line_liff` | `line.api.service` | `narrowcast` | Targeted push by demographic/audience filter |
| `woow_odoo_line_liff` | `line.api.service` | `reply` | Reply to incoming webhook messages |
| `woow_odoo_line_liff` | `line.api.service` | `build_text_message`, `build_image_message`, `build_file_message` | Construct message payloads |
| `woow_odoo_line_liff` | `line.api.service` | `richmenu_create`, `richmenu_upload_image`, `richmenu_set_default`, `richmenu_delete`, `richmenu_link_to_user`, `richmenu_link_to_users`, `richmenu_create_alias`, `richmenu_update_alias` | Rich Menu lifecycle management |
| `woow_odoo_line_liff` | `line.api.service` | `audience_create`, `audience_add_users`, `audience_delete` | Audience group management for narrowcast |
| `woow_odoo_line_liff` | `line.api.service` | `get_insight_delivery`, `get_insight_followers`, `get_insight_message_event` | Dashboard analytics |
| `woow_odoo_line_liff` | `line.api.service` | `get_quota`, `get_quota_consumption` | Quota monitoring widget |
| `woow_odoo_line_liff` | `line.api.service` | `verify_id_token`, `verify_access_token` | LIFF login verification |
| `woow_odoo_line_liff` | `line.api.service` | `verify_webhook_signature` | Webhook endpoint authentication |
| `woow_odoo_line_liff` | `line.api.service` | `get_profile` | Fetch user profile on webhook follow event |
| `woow_odoo_line_liff` | `line.api.service` | `get_content` | Download media from image/video/audio messages |
| `woow_odoo_line_liff` | `line.user` | `create_or_update_from_webhook` | Create/update user on every webhook event |
| `woow_odoo_line_liff` | `line.user` | `create_or_update_from_liff` | Create/update user on LIFF login |
| `woow_odoo_line_liff` | `line.user` | `find_by_line_uid` | Look up user by LINE UID |
| `woow_odoo_line_liff` | `line.user` | `bind_partner`, `unbind` | Manual partner binding via UI |
| `woow_odoo_livechat_line` | `line.api.service` | `push_message` | Send Odoo Discuss replies back to LINE |
| `woow_odoo_livechat_line` | `line.api.service` | `reply` | Immediate reply via webhook reply token |
| `woow_odoo_livechat_line` | `line.api.service` | `build_text_message`, `build_image_message` | Construct reply messages |
| `woow_odoo_livechat_line` | `line.api.service` | `verify_webhook_signature` | Authenticate incoming webhook requests |
| `woow_odoo_livechat_line` | `line.api.service` | `get_profile` | Fetch user profile for mail.guest creation |
| `woow_odoo_livechat_line` | `line.api.service` | `get_content` | Download media attachments from LINE messages |
| `woow_odoo_livechat_line` | `line.user` | `create_or_update_from_webhook` | Create/update user on livechat message |
| `woow_odoo_livechat_line` | `line.user` | `find_by_line_uid` | Look up user for message routing |
| `woow_odoo_livechat_line` | `line.user` | `_sync_to_mail_guest` | Sync partner binding to mail.guest for Discuss |

### Key Context Flags

| Flag | Used by | Effect |
|------|---------|--------|
| `skip_email_sync` | `line.user.write`, `res.partner.write` | Prevents bidirectional email propagation. |
| `skip_auto_bind` | `_auto_bind_or_create_partner` | Prevents automatic partner creation/matching. |

---

## Quick Start: Send Your First LINE Message

```python
# In Odoo Shell (odoo-bin shell -d mydb)
svc = env['line.api.service']

# 1. Send to ALL followers
svc.broadcast([svc.build_text_message('Hello from Odoo!')])

# 2. Send to one user
user = env['line.user'].search([('display_name', 'like', 'Peter')], limit=1)
svc.push(user.line_user_id, [svc.build_text_message('Hi Peter!')])

# 3. Batch send to multiple users
uids = env['line.user'].search([('is_follower', '=', True)]).mapped('line_user_id')
svc.multicast(uids, [svc.build_text_message('Announcement!')])
```

---

## LINE Developer Console Setup

### Step 1: Create a Provider

1. Go to https://developers.line.biz/console/
2. Click **Create** under Providers
3. Enter your company name → **Create**

### Step 2: Create a Messaging API Channel

1. In your Provider, click **Create a new channel** → choose **Messaging API**
2. Fill in channel name, description, category → **Create**
3. Go to **Basic settings** tab:
   - Copy **Channel ID** → `woow_line_base.messaging_channel_id`
   - Copy **Channel secret** → `woow_line_base.messaging_channel_secret`
4. Go to **Messaging API** tab:
   - Scroll to **Channel access token (long-lived)** → click **Issue**
   - Copy the token → `woow_line_base.messaging_access_token`
5. Set **Webhook URL** to `https://your-domain.com/line/webhook/{config_id}`
6. Enable **Use webhook** toggle

### Step 3: Create a LINE Login Channel (for LIFF)

1. In the same Provider, **Create a new channel** → choose **LINE Login**
2. Fill in channel name → **Create**
3. Go to **Basic settings** tab:
   - Copy **Channel ID** → `woow_line_base.login_channel_id`
   - Copy **Channel secret** → `woow_line_base.login_channel_secret`

### Step 4: Set Odoo System Parameters

```
Settings → Technical → Parameters → System Parameters
```

| Key | Value | Source |
|-----|-------|--------|
| `woow_line_base.messaging_channel_id` | `20XXXXXXXX` | Messaging API → Basic settings |
| `woow_line_base.messaging_channel_secret` | `2ad784...` | Messaging API → Basic settings |
| `woow_line_base.messaging_access_token` | `lnNuYK8...` | Messaging API → Messaging API tab |
| `woow_line_base.login_channel_id` | `20XXXXXXXX` | LINE Login → Basic settings |
| `woow_line_base.login_channel_secret` | `b24b00...` | LINE Login → Basic settings |

---

## Flow Diagrams

### Token Resolution Flow

```
push() / multicast() / broadcast() called
    │
    ├── access_token param provided?
    │   └── YES → use it directly
    │
    ├── channel_id + channel_secret provided?
    │   └── YES → _get_token_oauth(channel_id, secret)
    │       └── POST /oauth2/v3/token (client_credentials)
    │       └── cache token in memory (per-worker)
    │       └── return bearer token
    │
    └── NO explicit credentials
        └── _resolve_token() reads ir.config_parameter:
            └── woow_line_base.messaging_access_token
            └── return global long-lived token
```

### Email Bidirectional Sync Flow

```
LINE User email changed          Partner email changed
        │                                │
        v                                v
line.user.write()                res.partner.write()
        │                                │
   skip_email_sync?                skip_email_sync?
   ├── YES → stop                  ├── YES → stop
   └── NO                         └── NO
        │                                │
   partner_id exists?              line_user_ids exist?
   ├── NO → stop                   ├── NO → stop
   └── YES                        └── YES
        │                                │
   partner.write(                  line_user.write(
     email=new_email,                email=new_email,
     context={skip_email_sync}       context={skip_email_sync}
   )                               )
```

### Data Flow: How Upstream Modules Use This Module

```
┌─────────────────────────────┐     ┌─────────────────────────────┐
│   woow_odoo_line_liff       │     │  woow_odoo_livechat_line    │
│                             │     │                             │
│ • push/multicast/broadcast  │     │ • push_message (replies)    │
│ • narrowcast (audience)     │     │ • get_content (media DL)    │
│ • richmenu_* (6 methods)    │     │ • get_profile (guest info)  │
│ • audience_create/delete    │     │ • verify_webhook_signature  │
│ • get_insight_* (3 methods) │     │ • create_or_update_from_    │
│ • verify_id_token           │     │   webhook                   │
│ • verify_webhook_signature  │     │ • _sync_to_mail_guest       │
│ • create_or_update_from_*   │     │                             │
└─────────────┬───────────────┘     └──────────────┬──────────────┘
              │                                    │
              ▼                                    ▼
┌─────────────────────────────────────────────────────────────────┐
│                      woow_line_base                             │
│                                                                 │
│  line.api.service        line.user         ir.config_parameter  │
│  ├─ push()               ├─ create_or_    ├─ messaging_*       │
│  ├─ multicast()          │  update_from_  ├─ login_*           │
│  ├─ broadcast()          │  webhook/liff  └─ auto_line_notify  │
│  ├─ narrowcast()         ├─ bind_partner                       │
│  ├─ reply()              ├─ _auto_bind_                        │
│  ├─ richmenu_*()         │  or_create_                         │
│  ├─ audience_*()         │  partner                            │
│  ├─ get_insight_*()      ├─ _sync_to_                          │
│  ├─ verify_id_token()    │  mail_guest                         │
│  └─ get_profile()        └─ find_by_                           │
│                             line_uid                            │
└─────────────────────────────────────────────────────────────────┘
```

---

## LINE API Rate Limits

| API | Limit | Module Behavior on Limit |
|-----|-------|--------------------------|
| Push | 200 req/sec | No built-in throttling; callers should batch |
| Multicast | 200 req/sec, 500 users/batch | Auto-chunks into 500-user batches |
| Broadcast | 60 req/hour | Returns `False`; upstream may auto-degrade to multicast |
| Narrowcast | 60 req/hour | Returns `None`; no retry logic |
| Reply | Must reply within 1 min | Reply token expires silently after 1 minute |
| Get Profile | 2,000 req/min | No throttling; log warning on failure |
| Rich Menu | Varies by endpoint | No throttling; errors logged |

---

## Token Revocation & Expiry

### Global Long-Lived Token

- If revoked in LINE Developer Console, **all API calls fail with HTTP 401**.
- The module does **NOT** detect 401 or attempt re-authentication for global tokens.
- You must manually re-issue the token and update `woow_line_base.messaging_access_token`.

### Per-Channel OAuth2 Token

- Uses `client_credentials` grant → automatically refreshes on expiry.
- Cached in-memory per worker process; lost on Odoo restart.
- Cache TTL: 30 days (LINE's default token validity).

### Token After Odoo Restart

- All in-memory caches are cleared.
- Next API call triggers a fresh `_resolve_token()` read from `ir.config_parameter`.
- Per-channel tokens re-authenticate via OAuth2 on first use.

---

## Internal Helper Methods

| Method | Signature | Returns | Description |
|--------|-----------|---------|-------------|
| `_resolve_token` | `(access_token=None, channel_id=None, channel_secret=None)` | `str` or `None` | Resolves bearer token: returns explicit token if provided, calls `_get_token_oauth` if channel credentials provided, otherwise reads global `ir.config_parameter`. |
| `_auth_headers` | `(token)` | `dict` | Returns `{'Authorization': 'Bearer {token}', 'Content-Type': 'application/json'}`. |
| `_get_token_oauth` | `(channel_id, channel_secret)` | `str` or `None` | Obtains token via `POST /oauth2/v3/token` with `client_credentials` grant. Caches result in `_token_cache`. |

---

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| All push/broadcast calls fail silently | Access token revoked or missing | Re-issue in LINE Console → update system parameter |
| `verify_webhook_signature` returns False | Channel secret mismatch | Check `woow_line_base.messaging_channel_secret` matches LINE Console |
| Email not syncing partner → LINE user | `skip_email_sync` in context | Check calling code doesn't pass this flag |
| `_auto_bind_or_create_partner` not triggering | `skip_auto_bind` in context | Check webhook/LIFF code context |
| `get_profile` returns empty dict | Rate limited (2000/min) or invalid token | Check logs for HTTP status; re-issue token |
| `multicast` sends to wrong users | Passing partner IDs instead of LINE UIDs | Use `mapped('line_user_id')` to get LINE UIDs |
| `line.push.log` KeyError on create | `woow_odoo_line_liff` not installed | Install bridge module or override `_log_push` |
