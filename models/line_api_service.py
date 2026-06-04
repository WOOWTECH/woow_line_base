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

# OAuth token 快取（per channel，in-memory）
_token_cache = {}
_TOKEN_REFRESH_BUFFER = 300  # 5 分鐘提前刷新


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

    def _get_token_oauth(self, channel_id, channel_secret):
        """OAuth2 client_credentials 取得 token（帶快取）"""
        now = time.time()
        cached = _token_cache.get(channel_id)
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
                _token_cache[channel_id] = {
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
        try:
            resp = http_requests.get(
                f'{LINE_PROFILE_URL}/{line_user_id}',
                headers=self._auth_headers(token),
                timeout=5,
            )
            if resp.status_code == 200:
                return resp.json()
            _logger.warning('Profile 取得失敗: %s', resp.status_code)
        except http_requests.RequestException:
            _logger.exception('Profile 網路錯誤')
        return {}

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
        PushLog = self.env['line.push.log'].sudo()

        for lu in line_users:
            if lu.is_blocked or not lu.notification_enabled or not lu.is_follower:
                continue

            success, status_code, resp_text = self._push_message_raw(
                token, lu.line_user_id, messages,
            )
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

    def multicast(self, line_user_ids_list, messages, channel_id=None, channel_secret=None):
        """群發（最多 500 人/批）"""
        token = self._resolve_token(None, channel_id, channel_secret)
        if not token:
            return False
        for i in range(0, len(line_user_ids_list), 500):
            batch = line_user_ids_list[i:i + 500]
            try:
                resp = http_requests.post(LINE_MULTICAST_URL,
                    headers=self._auth_headers(token),
                    json={'to': batch, 'messages': messages}, timeout=10)
                if resp.status_code != 200:
                    _logger.warning('multicast 失敗: %s', resp.status_code)
                    return False
            except http_requests.RequestException:
                _logger.exception('multicast 網路錯誤')
                return False
        return True

    def broadcast(self, messages, channel_id=None, channel_secret=None):
        """廣播給所有好友"""
        token = self._resolve_token(None, channel_id, channel_secret)
        if not token:
            return False
        try:
            resp = http_requests.post(LINE_BROADCAST_URL,
                headers=self._auth_headers(token),
                json={'messages': messages}, timeout=10)
            return resp.status_code == 200
        except http_requests.RequestException:
            _logger.exception('broadcast 網路錯誤')
            return False

    def reply(self, reply_token, messages, channel_id=None, channel_secret=None):
        """回覆（Reply Token 只能用一次）"""
        token = self._resolve_token(None, channel_id, channel_secret)
        if not token:
            return False
        try:
            resp = http_requests.post(LINE_REPLY_URL,
                headers=self._auth_headers(token),
                json={'replyToken': reply_token, 'messages': messages}, timeout=10)
            return resp.status_code == 200
        except http_requests.RequestException:
            _logger.exception('reply 網路錯誤')
            return False

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
        try:
            resp = http_requests.get(
                f'{LINE_CONTENT_URL}/{message_id}/content',
                headers={'Authorization': f'Bearer {token}'},
                timeout=30,
            )
            if resp.status_code == 200:
                return resp.content, resp.headers.get('Content-Type', '')
            _logger.warning('媒體下載失敗: %s', resp.status_code)
        except http_requests.RequestException:
            _logger.exception('媒體下載網路錯誤')
        return None, None

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
