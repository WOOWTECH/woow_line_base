# -*- coding: utf-8 -*-
# woow_line_base/models/line_api_service.py
# 統一 LINE API 客戶端（AbstractModel）
# 合併 woow_line_bridge 的 line.service 與 woow_odoo_livechat_line 的 line.api.mixin
# 支援雙軌 credential：全域 ir.config_parameter 或 per-channel 傳入
import hashlib
import hmac
import base64
import json
import logging
import time

import requests as http_requests

from odoo import api, models

_logger = logging.getLogger(__name__)

# LINE API 端點
LINE_TOKEN_URL = 'https://api.line.me/v2/oauth/accessToken'
LINE_VERIFY_URL = 'https://api.line.me/oauth2/v2.1/verify'
LINE_PROFILE_URL = 'https://api.line.me/v2/bot/profile'
LINE_PUSH_URL = 'https://api.line.me/v2/bot/message/push'
LINE_MULTICAST_URL = 'https://api.line.me/v2/bot/message/multicast'
LINE_BROADCAST_URL = 'https://api.line.me/v2/bot/message/broadcast'
LINE_REPLY_URL = 'https://api.line.me/v2/bot/message/reply'
LINE_CONTENT_URL = 'https://api-data.line.me/v2/bot/message'

# Rich Menu API
LINE_RICHMENU_URL = 'https://api.line.me/v2/bot/richmenu'
LINE_RICHMENU_CONTENT_URL = 'https://api-data.line.me/v2/bot/richmenu'
LINE_RICHMENU_ALIAS_URL = 'https://api.line.me/v2/bot/richmenu/alias'

# Narrowcast / Insight / Quota / Audience API
LINE_NARROWCAST_URL = 'https://api.line.me/v2/bot/message/narrowcast'
LINE_INSIGHT_DELIVERY_URL = 'https://api.line.me/v2/bot/insight/message/delivery'
LINE_INSIGHT_FOLLOWERS_URL = 'https://api.line.me/v2/bot/insight/followers'
LINE_INSIGHT_MESSAGE_EVENT_URL = 'https://api.line.me/v2/bot/insight/message/event'
LINE_QUOTA_URL = 'https://api.line.me/v2/bot/message/quota'
LINE_QUOTA_CONSUMPTION_URL = 'https://api.line.me/v2/bot/message/quota/consumption'
LINE_AUDIENCE_URL = 'https://api.line.me/v2/bot/audienceGroup/upload'

# OAuth token 快取（per channel，in-memory）
_token_cache = {}
_TOKEN_REFRESH_BUFFER = 300  # 5 分鐘提前刷新

# H-12：媒體下載大小上限，預設值；可用 ir.config_parameter 覆寫
_CONTENT_MAX_MB_DEFAULT = 50
_CONTENT_CHUNK_SIZE = 1024 * 1024  # 1 MB


class LineApiService(models.AbstractModel):
    """統一 LINE API 客戶端

    所有 LINE Platform API 呼叫都透過這個 AbstractModel。
    支援兩種 credential 模式：
    1. 全域模式（不傳參數）→ 從 ir.config_parameter 讀取
    2. Per-channel 模式（傳入 channel_id + channel_secret）→ OAuth2 token cache
    """
    _name = 'line.api.service'
    _description = '統一 LINE API 客戶端'

    # ------------------------------------------------------------------
    # 私有：Credential 取得
    # ------------------------------------------------------------------

    def _get_config(self, key, default=''):
        return self.env['ir.config_parameter'].sudo().get_param(key, default)

    def _get_global_access_token(self):
        return self._get_config('woow_line_base.messaging_access_token')

    def _get_global_channel_secret(self):
        return self._get_config('woow_line_base.messaging_channel_secret')

    # ------------------------------------------------------------------
    # 公開：Access Token 取得
    # ------------------------------------------------------------------

    def get_access_token(self, channel_id=None, channel_secret=None):
        """取得 LINE Channel Access Token

        :param channel_id: Messaging API Channel ID（per-channel 用）
        :param channel_secret: Messaging API Channel Secret（per-channel 用）
        :return: access token 字串，失敗回 None
        """
        if channel_id and channel_secret:
            return self._get_token_oauth(channel_id, channel_secret)
        return self._get_global_access_token() or None

    def _token_cache_key(self, channel_id, channel_secret):
        """B-8：cache key 要含 secret 的指紋，否則改掉/修正 secret 之後，
        該 worker 仍會用舊 secret 換出的 token 繼續運作到 process 重啟或 TTL 到期。
        用 hash 而不是存明文 secret，避免快取 key 本身洩漏憑證。"""
        secret_fingerprint = hashlib.sha256((channel_secret or '').encode('utf-8')).hexdigest()
        return (channel_id, secret_fingerprint)

    def _invalidate_cached_token(self, channel_id, channel_secret):
        """收到 401/403 時呼叫，強制下次 _get_token_oauth 重新換發 token"""
        if channel_id:
            _token_cache.pop(self._token_cache_key(channel_id, channel_secret), None)

    def _get_token_oauth(self, channel_id, channel_secret):
        """OAuth2 client_credentials 取得 token（帶快取）"""
        now = time.time()
        cache_key = self._token_cache_key(channel_id, channel_secret)
        cached = _token_cache.get(cache_key)
        if cached and cached['expires_at'] > now + _TOKEN_REFRESH_BUFFER:
            return cached['token']

        try:
            resp = http_requests.post(LINE_TOKEN_URL, data={
                'grant_type': 'client_credentials',
                'client_id': channel_id,
                'client_secret': channel_secret,
            }, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                token = data.get('access_token')
                expires_in = data.get('expires_in', 2592000)
                _token_cache[cache_key] = {
                    'token': token,
                    'expires_at': now + expires_in,
                }
                _logger.info('LINE OAuth token 取得成功: channel=%s', channel_id)
                return token
            _logger.warning('LINE OAuth token 取得失敗: status=%s', resp.status_code)
        except http_requests.RequestException:
            _logger.exception('LINE OAuth token 網路錯誤')
        return None

    def _resolve_token(self, access_token=None, channel_id=None, channel_secret=None):
        """解析 token：優先用傳入的，否則取得新的"""
        if access_token:
            return access_token
        return self.get_access_token(channel_id, channel_secret)

    def _auth_headers(self, token):
        return {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {token}',
        }

    # ------------------------------------------------------------------
    # 公開：ID Token / Access Token 驗證
    # ------------------------------------------------------------------

    def verify_id_token(self, id_token, login_channel_id=None):
        """驗證 LINE Login ID Token

        :param id_token: LIFF 取得的 ID Token
        :param login_channel_id: LINE Login Channel ID（不傳則從 config 讀）
        :return: payload dict 或 None
        """
        channel_id = login_channel_id or self._get_config('woow_line_base.login_channel_id')
        if not channel_id:
            _logger.error('LINE Login Channel ID 未設定')
            return None

        try:
            resp = http_requests.post(LINE_VERIFY_URL, data={
                'id_token': id_token,
                'client_id': channel_id,
            }, timeout=10)
            if resp.status_code == 200:
                return resp.json()
            _logger.warning('ID Token 驗證失敗: %s %s', resp.status_code, resp.text)
        except http_requests.RequestException:
            _logger.exception('ID Token 驗證網路錯誤')
        return None

    def verify_access_token(self, access_token):
        """用 LIFF Access Token 取得 Profile（ID Token 備援方案）

        :param access_token: LIFF 取得的 access token
        :return: 類似 ID Token payload 的 dict（含 sub, name, picture）或 None
        """
        if not access_token:
            return None
        try:
            verify_resp = http_requests.get(
                'https://api.line.me/oauth2/v2.1/verify',
                params={'access_token': access_token},
                timeout=10,
            )
            if verify_resp.status_code != 200:
                _logger.warning('Access Token 驗證失敗: %s', verify_resp.status_code)
                return None

            expected_client_id = self._get_config('woow_line_base.login_channel_id')
            if not expected_client_id:
                # fail closed：本站沒設定 login channel id 就不可能比對，
                # 不能因此放行任何 LINE Login channel 簽發的 token
                _logger.error('login_channel_id 未設定，拒絕驗證 access token（fail closed）')
                return None
            verify_data = verify_resp.json()
            if verify_data.get('client_id') != expected_client_id:
                # 沒比對 client_id = 接受任何 LINE Login channel 簽發的 token
                # （audience confusion，攻擊者可用自己的 channel 換取本站 portal 登入）
                _logger.warning(
                    'Access Token client_id 不符，拒絕: got=%s expected=%s',
                    verify_data.get('client_id'), expected_client_id,
                )
                return None

            profile_resp = http_requests.get(
                'https://api.line.me/v2/profile',
                headers={'Authorization': f'Bearer {access_token}'},
                timeout=10,
            )
            if profile_resp.status_code != 200:
                return None

            profile = profile_resp.json()
            return {
                'sub': profile.get('userId', ''),
                'name': profile.get('displayName', ''),
                'picture': profile.get('pictureUrl', ''),
            }
        except http_requests.RequestException:
            _logger.exception('Access Token 驗證網路錯誤')
        return None

    # ------------------------------------------------------------------
    # 公開：Webhook 簽章驗證
    # ------------------------------------------------------------------

    def verify_webhook_signature(self, body_bytes, signature_header, channel_secret=None):
        """驗證 LINE Webhook X-Line-Signature（HMAC-SHA256）"""
        secret = channel_secret or self._get_global_channel_secret()
        if not secret:
            _logger.error('Channel Secret 未設定')
            return False
        try:
            digest = hmac.new(
                secret.encode('utf-8'), body_bytes, hashlib.sha256,
            ).digest()
            expected = base64.b64encode(digest).decode('utf-8')
            return hmac.compare_digest(expected, signature_header or '')
        except Exception:
            _logger.exception('Webhook 簽章驗證錯誤')
            return False

    # ------------------------------------------------------------------
    # 公開：Profile
    # ------------------------------------------------------------------

    def get_profile(self, line_user_id, access_token=None, channel_id=None, channel_secret=None):
        """取得 LINE 用戶 Profile

        :return: dict {userId, displayName, pictureUrl, statusMessage} 或 {}
        """
        token = self._resolve_token(access_token, channel_id, channel_secret)
        if not token:
            return {}
        profile, status_code = self._get_profile_raw(token, line_user_id)
        if not profile and status_code in (401, 403) and not access_token and channel_id and channel_secret:
            # B-8：token 可能是舊 secret 換出的快取，清掉重試一次
            self._invalidate_cached_token(channel_id, channel_secret)
            token = self._resolve_token(None, channel_id, channel_secret)
            if not token:
                return {}
            profile, _ = self._get_profile_raw(token, line_user_id)
        return profile

    def _get_profile_raw(self, token, line_user_id):
        try:
            resp = http_requests.get(
                f'{LINE_PROFILE_URL}/{line_user_id}',
                headers=self._auth_headers(token),
                timeout=5,
            )
            if resp.status_code == 200:
                return resp.json(), resp.status_code
            _logger.warning('Profile 取得失敗: %s', resp.status_code)
            return {}, resp.status_code
        except http_requests.RequestException:
            _logger.exception('Profile 網路錯誤')
            return {}, 0

    # ------------------------------------------------------------------
    # 公開：推播
    # ------------------------------------------------------------------

    def push(self, line_users, messages, channel_id=None, channel_secret=None):
        """推播訊息給 line.user recordset（過濾 blocked/disabled/unfollowed）

        :param line_users: line.user recordset
        :param messages: LINE message list
        :return: 成功送出的 line.user id list
        """
        token = self._resolve_token(None, channel_id, channel_secret)
        if not token:
            _logger.error('無法取得 Access Token，推播中止')
            return []

        sent_ids = []
        # 新·4：line.push.log 定義在 woow_odoo_line_liff，不是這個 repo。
        # 只裝 woow_line_base + woow_odoo_livechat_line（合法組合，livechat 不依賴
        # liff）時這個 model 不存在於 registry，直接 self.env['line.push.log'] 會
        # KeyError。正解是把 line.push.log 搬進 woow_line_base，但那需要跨 repo的
        # migration，這裡先讓沒裝 liff 時跳過寫 log、其餘照跑。
        PushLog = self.env['line.push.log'].sudo() if 'line.push.log' in self.env else None

        for lu in line_users:
            if lu.is_blocked or not lu.notification_enabled or not lu.is_follower:
                continue

            success, status_code, resp_text = self._push_message_raw(
                token, lu.line_user_id, messages,
            )
            if PushLog is not None:
                PushLog.create({
                    'line_user_id': lu.id,
                    'messages': json.dumps(messages, ensure_ascii=False),
                    'status_code': status_code,
                    'response_body': resp_text,
                    'success': success,
                })
            if success:
                sent_ids.append(lu.id)
                lu.sudo().write({'push_count': lu.push_count + 1})

        return sent_ids

    def push_message(self, line_uid, messages, access_token=None, channel_id=None, channel_secret=None):
        """推播訊息給指定 LINE User ID（低階方法，不寫 log）

        :param line_uid: LINE User ID 字串
        :param messages: LINE message list（max 5）
        :return: True/False
        """
        token = self._resolve_token(access_token, channel_id, channel_secret)
        if not token:
            return False
        success, status_code, _ = self._push_message_raw(token, line_uid, messages)
        if not success and status_code in (401, 403) and not access_token and channel_id and channel_secret:
            # B-8：token 可能是舊 secret 換出的快取，清掉重試一次
            self._invalidate_cached_token(channel_id, channel_secret)
            token = self._resolve_token(None, channel_id, channel_secret)
            if not token:
                return False
            success, _, _ = self._push_message_raw(token, line_uid, messages)
        return success

    def _push_message_raw(self, token, line_uid, messages):
        """實際推播"""
        try:
            resp = http_requests.post(LINE_PUSH_URL, headers=self._auth_headers(token),
                json={'to': line_uid, 'messages': messages}, timeout=10)
            return resp.status_code == 200, resp.status_code, resp.text
        except http_requests.RequestException as e:
            _logger.exception('推播網路錯誤: %s', line_uid)
            return False, 0, str(e)

    def multicast_ex(self, line_user_ids_list, messages, channel_id=None, channel_secret=None):
        """群發（最多 500 人/批），回傳 (ok, status_code, body) 供下游判斷真實失敗原因

        D-7：舊 multicast() 把逾時（RequestException）跟真的 4xx/5xx 都壓成同一個
        False，下游沒有狀態碼可看，只能瞎猜（例如誤當 429 而降級成 narrowcast）。
        逾時時 LINE 可能其實已受理，若下游因此重送會造成重複投遞。
        多批次時只要有一批失敗就立刻回傳該批的狀態碼/body，後面的批次不會再送。

        :return: (bool ok, int status_code, str body)。網路例外時 status_code=0，
                 body 是例外訊息字串。
        """
        token = self._resolve_token(None, channel_id, channel_secret)
        if not token:
            return False, 0, 'no_access_token'
        for i in range(0, len(line_user_ids_list), 500):
            batch = line_user_ids_list[i:i + 500]
            try:
                resp = http_requests.post(LINE_MULTICAST_URL,
                    headers=self._auth_headers(token),
                    json={'to': batch, 'messages': messages}, timeout=10)
                if resp.status_code != 200:
                    _logger.warning('multicast 失敗: %s %s', resp.status_code, resp.text[:500])
                    return False, resp.status_code, resp.text
            except http_requests.RequestException as e:
                _logger.exception('multicast 網路錯誤')
                return False, 0, str(e)
        return True, 200, ''

    def multicast(self, line_user_ids_list, messages, channel_id=None, channel_secret=None):
        """群發（最多 500 人/批）（薄包裝，向下相容；需要狀態碼/body 請改用 multicast_ex）"""
        return self.multicast_ex(
            line_user_ids_list, messages, channel_id=channel_id, channel_secret=channel_secret,
        )[0]

    def broadcast_ex(self, messages, channel_id=None, channel_secret=None):
        """廣播給所有好友，回傳 (ok, status_code, body)

        D-7：理由同 multicast_ex——狀態碼與 body 被丟掉會讓下游只能瞎猜失敗原因。

        :return: (bool ok, int status_code, str body)。網路例外時 status_code=0，
                 body 是例外訊息字串。
        """
        token = self._resolve_token(None, channel_id, channel_secret)
        if not token:
            return False, 0, 'no_access_token'
        try:
            resp = http_requests.post(LINE_BROADCAST_URL,
                headers=self._auth_headers(token),
                json={'messages': messages}, timeout=10)
            return resp.status_code == 200, resp.status_code, resp.text
        except http_requests.RequestException as e:
            _logger.exception('broadcast 網路錯誤')
            return False, 0, str(e)

    def broadcast(self, messages, channel_id=None, channel_secret=None):
        """廣播給所有好友（薄包裝，向下相容；需要狀態碼/body 請改用 broadcast_ex）"""
        return self.broadcast_ex(messages, channel_id=channel_id, channel_secret=channel_secret)[0]

    def reply(self, reply_token, messages, channel_id=None, channel_secret=None):
        """回覆（Reply Token 只能用一次）"""
        token = self._resolve_token(None, channel_id, channel_secret)
        if not token:
            return False
        success, status_code = self._reply_raw(token, reply_token, messages)
        if not success and status_code in (401, 403) and channel_id and channel_secret:
            # B-8：token 可能是舊 secret 換出的快取，清掉重試一次
            # （401/403 代表這次呼叫沒被 LINE 受理，reply_token 還沒被消耗，重試安全）
            self._invalidate_cached_token(channel_id, channel_secret)
            token = self._resolve_token(None, channel_id, channel_secret)
            if not token:
                return False
            success, _ = self._reply_raw(token, reply_token, messages)
        return success

    def _reply_raw(self, token, reply_token, messages):
        try:
            resp = http_requests.post(LINE_REPLY_URL,
                headers=self._auth_headers(token),
                json={'replyToken': reply_token, 'messages': messages}, timeout=10)
            return resp.status_code == 200, resp.status_code
        except http_requests.RequestException:
            _logger.exception('reply 網路錯誤')
            return False, 0

    # ------------------------------------------------------------------
    # 公開：媒體下載
    # ------------------------------------------------------------------

    def get_content(self, message_id, access_token=None, channel_id=None, channel_secret=None):
        """下載 LINE 媒體內容

        :return: (bytes, content_type) 或 (None, None)
        """
        token = self._resolve_token(access_token, channel_id, channel_secret)
        if not token:
            return None, None
        content, content_type, status_code = self._get_content_raw(token, message_id)
        if content is None and status_code in (401, 403) and not access_token and channel_id and channel_secret:
            # B-8：token 可能是舊 secret 換出的快取，清掉重試一次
            self._invalidate_cached_token(channel_id, channel_secret)
            token = self._resolve_token(None, channel_id, channel_secret)
            if not token:
                return None, None
            content, content_type, _ = self._get_content_raw(token, message_id)
        return content, content_type

    def _get_content_max_bytes(self):
        """H-12：上限來自 ir.config_parameter，預設 50 MB"""
        raw = self.env['ir.config_parameter'].sudo().get_param(
            'woow_line_base.content_max_mb', _CONTENT_MAX_MB_DEFAULT)
        try:
            mb = float(raw)
        except (TypeError, ValueError):
            mb = _CONTENT_MAX_MB_DEFAULT
        return int(mb * 1024 * 1024)

    def _get_content_raw(self, token, message_id):
        """H-12：串流下載，邊讀邊檢查大小，絕不把整包吃進記憶體。

        Content-Length 是客戶端宣稱的，不可信；串流本身也要邊讀邊算，
        兩邊任一超過上限就中止並關閉連線。
        """
        cap_bytes = self._get_content_max_bytes()
        try:
            resp = http_requests.get(
                f'{LINE_CONTENT_URL}/{message_id}/content',
                headers={'Authorization': f'Bearer {token}'},
                timeout=30,
                stream=True,
            )
        except http_requests.RequestException:
            _logger.exception('媒體下載網路錯誤')
            return None, None, 0

        if resp.status_code != 200:
            _logger.warning('媒體下載失敗: %s', resp.status_code)
            status_code = resp.status_code
            resp.close()
            return None, None, status_code

        declared_length = resp.headers.get('Content-Length')
        if declared_length is not None:
            try:
                declared_over_cap = int(declared_length) > cap_bytes
            except ValueError:
                declared_over_cap = False
            if declared_over_cap:
                _logger.warning(
                    '媒體下載拒絕：宣告大小超過上限 (message_id=%s, declared_bytes=%s)',
                    message_id, declared_length)
                resp.close()
                return None, None, resp.status_code

        content_type = resp.headers.get('Content-Type', '')
        chunks = []
        total = 0
        try:
            for chunk in resp.iter_content(chunk_size=_CONTENT_CHUNK_SIZE):
                if not chunk:
                    continue
                total += len(chunk)
                if total > cap_bytes:
                    _logger.warning(
                        '媒體下載拒絕：串流大小超過上限 (message_id=%s, pulled_bytes=%s)',
                        message_id, total)
                    return None, None, resp.status_code
                chunks.append(chunk)
        finally:
            resp.close()

        return b''.join(chunks), content_type, resp.status_code

    # ------------------------------------------------------------------
    # 公開：Message Builder
    # ------------------------------------------------------------------

    def build_text_message(self, text):
        return {'type': 'text', 'text': text}

    def build_image_message(self, original_url, preview_url=None):
        return {
            'type': 'image',
            'originalContentUrl': original_url,
            'previewImageUrl': preview_url or original_url,
        }

    def build_video_message(self, original_url, preview_url):
        return {
            'type': 'video',
            'originalContentUrl': original_url,
            'previewImageUrl': preview_url,
        }

    def build_audio_message(self, original_url, duration_ms):
        return {
            'type': 'audio',
            'originalContentUrl': original_url,
            'duration': duration_ms,
        }

    def build_file_message(self, filename, file_url, file_size=None):
        """用 Flex Message kilo bubble 模擬檔案卡片"""
        ext = filename.rsplit('.', 1)[-1].upper() if '.' in filename else 'FILE'
        size_text = ''
        if file_size:
            if file_size > 1048576:
                size_text = f'{file_size / 1048576:.1f} MB'
            elif file_size > 1024:
                size_text = f'{file_size / 1024:.0f} KB'
            else:
                size_text = f'{file_size} B'

        body_contents = [
            {'type': 'text', 'text': filename, 'weight': 'bold', 'size': 'sm',
             'wrap': True, 'maxLines': 2, 'color': '#111111'},
        ]
        if size_text:
            body_contents.append(
                {'type': 'text', 'text': size_text, 'size': 'xs', 'color': '#AAAAAA'}
            )

        return {
            'type': 'flex',
            'altText': f'[檔案] {filename}',
            'contents': {
                'type': 'bubble',
                'size': 'kilo',
                'body': {
                    'type': 'box', 'layout': 'horizontal', 'spacing': 'md',
                    'paddingAll': '12px',
                    'contents': [
                        {'type': 'box', 'layout': 'vertical',
                         'width': '44px', 'height': '44px',
                         'backgroundColor': '#E8E8E8', 'cornerRadius': '8px',
                         'justifyContent': 'center', 'alignItems': 'center',
                         'contents': [
                             {'type': 'text', 'text': ext, 'size': 'xxs',
                              'weight': 'bold', 'color': '#555555', 'align': 'center'},
                         ]},
                        {'type': 'box', 'layout': 'vertical', 'flex': 1,
                         'justifyContent': 'center',
                         'contents': body_contents},
                    ],
                    'action': {'type': 'uri', 'label': '下載', 'uri': file_url},
                },
            },
        }

    # ------------------------------------------------------------------
    # 公開：Rich Menu API
    # ------------------------------------------------------------------

    def richmenu_create(self, menu_data, access_token=None, channel_id=None, channel_secret=None):
        """建立 Rich Menu

        :param menu_data: dict（size, selected, name, chatBarText, areas）
        :return: richMenuId 字串或 None
        """
        token = self._resolve_token(access_token, channel_id, channel_secret)
        if not token:
            return None
        try:
            resp = http_requests.post(LINE_RICHMENU_URL,
                headers=self._auth_headers(token), json=menu_data, timeout=10)
            if resp.status_code == 200:
                return resp.json().get('richMenuId')
            _logger.warning('Rich Menu 建立失敗: %s %s', resp.status_code, resp.text)
        except http_requests.RequestException:
            _logger.exception('Rich Menu 建立網路錯誤')
        return None

    def richmenu_upload_image(self, richmenu_id, image_data, content_type='image/png',
                              access_token=None, channel_id=None, channel_secret=None):
        """上傳 Rich Menu 圖片

        :param richmenu_id: LINE Rich Menu ID
        :param image_data: 圖片 bytes
        :param content_type: image/png 或 image/jpeg
        :return: True/False
        """
        token = self._resolve_token(access_token, channel_id, channel_secret)
        if not token:
            return False
        try:
            resp = http_requests.post(
                f'{LINE_RICHMENU_CONTENT_URL}/{richmenu_id}/content',
                headers={
                    'Authorization': f'Bearer {token}',
                    'Content-Type': content_type,
                },
                data=image_data, timeout=30,
            )
            return resp.status_code == 200
        except http_requests.RequestException:
            _logger.exception('Rich Menu 圖片上傳網路錯誤')
        return False

    def richmenu_set_default(self, richmenu_id, access_token=None, channel_id=None, channel_secret=None):
        """設定預設 Rich Menu"""
        token = self._resolve_token(access_token, channel_id, channel_secret)
        if not token:
            return False
        try:
            resp = http_requests.post(
                f'https://api.line.me/v2/bot/user/all/richmenu/{richmenu_id}',
                headers=self._auth_headers(token), timeout=10)
            return resp.status_code == 200
        except http_requests.RequestException:
            _logger.exception('Rich Menu 設定預設失敗')
        return False

    def richmenu_clear_default(self, access_token=None, channel_id=None, channel_secret=None):
        """取消預設 Rich Menu"""
        token = self._resolve_token(access_token, channel_id, channel_secret)
        if not token:
            return False
        try:
            resp = http_requests.delete(
                'https://api.line.me/v2/bot/user/all/richmenu',
                headers=self._auth_headers(token), timeout=10)
            return resp.status_code == 200
        except http_requests.RequestException:
            _logger.exception('Rich Menu 取消預設失敗')
        return False

    def richmenu_link_to_user(self, richmenu_id, line_user_id,
                               access_token=None, channel_id=None, channel_secret=None):
        """綁定 Rich Menu 到特定用戶"""
        token = self._resolve_token(access_token, channel_id, channel_secret)
        if not token:
            return False
        try:
            resp = http_requests.post(
                f'https://api.line.me/v2/bot/user/{line_user_id}/richmenu/{richmenu_id}',
                headers=self._auth_headers(token), timeout=10)
            return resp.status_code == 200
        except http_requests.RequestException:
            _logger.exception('Rich Menu 綁定用戶失敗')
        return False

    def richmenu_unlink_from_user(self, line_user_id,
                                   access_token=None, channel_id=None, channel_secret=None):
        """解除用戶的 Rich Menu 綁定"""
        token = self._resolve_token(access_token, channel_id, channel_secret)
        if not token:
            return False
        try:
            resp = http_requests.delete(
                f'https://api.line.me/v2/bot/user/{line_user_id}/richmenu',
                headers=self._auth_headers(token), timeout=10)
            return resp.status_code == 200
        except http_requests.RequestException:
            _logger.exception('Rich Menu 解除綁定失敗')
        return False

    def richmenu_link_to_users(self, richmenu_id, line_user_ids,
                                access_token=None, channel_id=None, channel_secret=None):
        """批次綁定 Rich Menu（最多 500 人）"""
        token = self._resolve_token(access_token, channel_id, channel_secret)
        if not token:
            return False
        try:
            resp = http_requests.post(
                'https://api.line.me/v2/bot/richmenu/bulk/link',
                headers=self._auth_headers(token),
                json={'richMenuId': richmenu_id, 'userIds': line_user_ids[:500]},
                timeout=10)
            return resp.status_code == 202
        except http_requests.RequestException:
            _logger.exception('Rich Menu 批次綁定失敗')
        return False

    def richmenu_delete(self, richmenu_id, access_token=None, channel_id=None, channel_secret=None):
        """刪除 Rich Menu"""
        token = self._resolve_token(access_token, channel_id, channel_secret)
        if not token:
            return False
        try:
            resp = http_requests.delete(
                f'{LINE_RICHMENU_URL}/{richmenu_id}',
                headers=self._auth_headers(token), timeout=10)
            return resp.status_code == 200
        except http_requests.RequestException:
            _logger.exception('Rich Menu 刪除失敗')
        return False

    def richmenu_get_user_menu(self, line_user_id,
                                access_token=None, channel_id=None, channel_secret=None):
        """取得用戶目前綁定的 Rich Menu ID"""
        token = self._resolve_token(access_token, channel_id, channel_secret)
        if not token:
            return None
        try:
            resp = http_requests.get(
                f'https://api.line.me/v2/bot/user/{line_user_id}/richmenu',
                headers=self._auth_headers(token), timeout=10)
            if resp.status_code == 200:
                return resp.json().get('richMenuId')
        except http_requests.RequestException:
            pass
        return None

    # Rich Menu Alias（Tab 切換）
    def richmenu_create_alias(self, alias_id, richmenu_id,
                               access_token=None, channel_id=None, channel_secret=None):
        """建立 Rich Menu Alias"""
        token = self._resolve_token(access_token, channel_id, channel_secret)
        if not token:
            return False
        try:
            resp = http_requests.post(LINE_RICHMENU_ALIAS_URL,
                headers=self._auth_headers(token),
                json={'richMenuAliasId': alias_id, 'richMenuId': richmenu_id}, timeout=10)
            return resp.status_code == 200
        except http_requests.RequestException:
            _logger.exception('Rich Menu Alias 建立失敗')
        return False

    def richmenu_update_alias(self, alias_id, richmenu_id,
                               access_token=None, channel_id=None, channel_secret=None):
        """更新 Rich Menu Alias"""
        token = self._resolve_token(access_token, channel_id, channel_secret)
        if not token:
            return False
        try:
            resp = http_requests.post(
                f'{LINE_RICHMENU_ALIAS_URL}/{alias_id}/update',
                headers=self._auth_headers(token),
                json={'richMenuId': richmenu_id}, timeout=10)
            return resp.status_code == 200
        except http_requests.RequestException:
            _logger.exception('Rich Menu Alias 更新失敗')
        return False

    def richmenu_delete_alias(self, alias_id,
                               access_token=None, channel_id=None, channel_secret=None):
        """刪除 Rich Menu Alias"""
        token = self._resolve_token(access_token, channel_id, channel_secret)
        if not token:
            return False
        try:
            resp = http_requests.delete(
                f'{LINE_RICHMENU_ALIAS_URL}/{alias_id}',
                headers=self._auth_headers(token), timeout=10)
            return resp.status_code == 200
        except http_requests.RequestException:
            _logger.exception('Rich Menu Alias 刪除失敗')
        return False

    # ------------------------------------------------------------------
    # Narrowcast（精準推播）
    # ------------------------------------------------------------------

    def narrowcast_ex(self, messages, recipient=None, demographic_filter=None,
                       access_token=None, channel_id=None, channel_secret=None):
        """精準推播（按 audience 或人口屬性篩選），回傳 (ok, status_code, body)

        D-7：理由同 broadcast_ex/multicast_ex——狀態碼與 body 被丟掉會讓下游只能
        瞎猜失敗原因（例如逾時卻誤判成配額限制而降級成別的投遞方式）。
        202 成功時 body 是完整 response text（含 requestId）。

        :return: (bool ok, int status_code, str body)。網路例外時 status_code=0，
                 body 是例外訊息字串。
        """
        token = self._resolve_token(access_token, channel_id, channel_secret)
        if not token:
            return False, 0, 'no_access_token'
        payload = {'messages': messages}
        if recipient:
            payload['recipient'] = recipient
        if demographic_filter:
            payload['filter'] = {'demographic': demographic_filter}
        try:
            resp = http_requests.post(LINE_NARROWCAST_URL,
                headers=self._auth_headers(token), json=payload, timeout=30)
            if resp.status_code != 202:
                _logger.warning('narrowcast 失敗: %s %s', resp.status_code, resp.text[:300])
            return resp.status_code == 202, resp.status_code, resp.text
        except http_requests.RequestException as e:
            _logger.exception('narrowcast 網路錯誤')
            return False, 0, str(e)

    def narrowcast(self, messages, recipient=None, demographic_filter=None,
                   access_token=None, channel_id=None, channel_secret=None):
        """精準推播（薄包裝，向下相容；需要狀態碼/body 請改用 narrowcast_ex）

        :return: request_id string or None
        """
        ok, _, body = self.narrowcast_ex(
            messages, recipient=recipient, demographic_filter=demographic_filter,
            access_token=access_token, channel_id=channel_id, channel_secret=channel_secret,
        )
        if not ok:
            return None
        try:
            return json.loads(body).get('requestId', 'ok')
        except (ValueError, AttributeError):
            return 'ok'

    # ------------------------------------------------------------------
    # Insight 統計
    # ------------------------------------------------------------------

    def get_insight_delivery(self, date_str, access_token=None, channel_id=None, channel_secret=None):
        """取得指定日期的訊息送達統計

        :param date_str: 'yyyyMMdd' 格式日期
        :return: dict with delivery stats or None
        """
        token = self._resolve_token(access_token, channel_id, channel_secret)
        if not token:
            return None
        try:
            resp = http_requests.get(LINE_INSIGHT_DELIVERY_URL,
                headers=self._auth_headers(token),
                params={'date': date_str}, timeout=10)
            if resp.status_code == 200:
                return resp.json()
            _logger.warning('insight delivery 失敗: %s', resp.status_code)
        except http_requests.RequestException:
            _logger.exception('insight delivery 網路錯誤')
        return None

    def get_insight_followers(self, date_str, access_token=None, channel_id=None, channel_secret=None):
        """取得指定日期的好友數統計

        :param date_str: 'yyyyMMdd' 格式日期
        :return: dict with follower stats or None
        """
        token = self._resolve_token(access_token, channel_id, channel_secret)
        if not token:
            return None
        try:
            resp = http_requests.get(LINE_INSIGHT_FOLLOWERS_URL,
                headers=self._auth_headers(token),
                params={'date': date_str}, timeout=10)
            if resp.status_code == 200:
                return resp.json()
            _logger.warning('insight followers 失敗: %s', resp.status_code)
        except http_requests.RequestException:
            _logger.exception('insight followers 網路錯誤')
        return None

    def get_insight_message_event(self, request_id, access_token=None, channel_id=None, channel_secret=None):
        """取得推播的用戶互動統計（開封/點擊）

        :param request_id: 推播時取得的 request ID
        :return: dict with event stats or None
        """
        token = self._resolve_token(access_token, channel_id, channel_secret)
        if not token:
            return None
        try:
            resp = http_requests.get(LINE_INSIGHT_MESSAGE_EVENT_URL,
                headers=self._auth_headers(token),
                params={'requestId': request_id}, timeout=10)
            if resp.status_code == 200:
                return resp.json()
        except http_requests.RequestException:
            _logger.exception('insight message event 網路錯誤')
        return None

    # ------------------------------------------------------------------
    # Quota 配額查詢
    # ------------------------------------------------------------------

    def get_quota(self, access_token=None, channel_id=None, channel_secret=None):
        """取得月度訊息配額

        :return: dict {'type': 'limited'/'none', 'value': int} or None
        """
        token = self._resolve_token(access_token, channel_id, channel_secret)
        if not token:
            return None
        try:
            resp = http_requests.get(LINE_QUOTA_URL,
                headers=self._auth_headers(token), timeout=10)
            if resp.status_code == 200:
                return resp.json()
        except http_requests.RequestException:
            _logger.exception('quota 查詢錯誤')
        return None

    def get_quota_consumption(self, access_token=None, channel_id=None, channel_secret=None):
        """取得當月已用訊息量

        :return: dict {'totalUsage': int} or None
        """
        token = self._resolve_token(access_token, channel_id, channel_secret)
        if not token:
            return None
        try:
            resp = http_requests.get(LINE_QUOTA_CONSUMPTION_URL,
                headers=self._auth_headers(token), timeout=10)
            if resp.status_code == 200:
                return resp.json()
        except http_requests.RequestException:
            _logger.exception('quota consumption 查詢錯誤')
        return None

    # ------------------------------------------------------------------
    # Audience 分眾群組
    # ------------------------------------------------------------------

    def audience_create(self, description, user_ids,
                        access_token=None, channel_id=None, channel_secret=None):
        """建立 audience 群組（上傳 user ID 列表）

        :param description: 群組描述
        :param user_ids: LINE user ID 列表
        :return: audience_group_id int or None
        """
        token = self._resolve_token(access_token, channel_id, channel_secret)
        if not token:
            return None
        audiences = [{'id': uid} for uid in user_ids]
        try:
            resp = http_requests.post(LINE_AUDIENCE_URL,
                headers=self._auth_headers(token),
                json={
                    'description': description,
                    'isIfaAudience': False,
                    'audiences': audiences,
                }, timeout=30)
            if resp.status_code in (200, 202):
                return resp.json().get('audienceGroupId')
            _logger.warning('audience 建立失敗: %s %s', resp.status_code, resp.text[:300])
        except http_requests.RequestException:
            _logger.exception('audience 建立網路錯誤')
        return None

    def audience_add_users(self, audience_group_id, user_ids,
                           access_token=None, channel_id=None, channel_secret=None):
        """新增用戶到 audience 群組"""
        token = self._resolve_token(access_token, channel_id, channel_secret)
        if not token:
            return False
        audiences = [{'id': uid} for uid in user_ids]
        try:
            resp = http_requests.put(
                f'{LINE_AUDIENCE_URL}/{audience_group_id}/updateDescription',
                headers=self._auth_headers(token), timeout=10)
            # LINE API uses PUT to add users
            resp2 = http_requests.put(LINE_AUDIENCE_URL,
                headers=self._auth_headers(token),
                json={
                    'audienceGroupId': audience_group_id,
                    'audiences': audiences,
                }, timeout=30)
            return resp2.status_code == 200
        except http_requests.RequestException:
            _logger.exception('audience 新增用戶失敗')
        return False

    def audience_delete(self, audience_group_id,
                        access_token=None, channel_id=None, channel_secret=None):
        """刪除 audience 群組"""
        token = self._resolve_token(access_token, channel_id, channel_secret)
        if not token:
            return False
        try:
            resp = http_requests.delete(
                f'https://api.line.me/v2/bot/audienceGroup/{audience_group_id}',
                headers=self._auth_headers(token), timeout=10)
            return resp.status_code == 200
        except http_requests.RequestException:
            _logger.exception('audience 刪除失敗')
        return False
