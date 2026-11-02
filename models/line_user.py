# -*- coding: utf-8 -*-
# woow_line_base/models/line_user.py
# LINE 用戶身份模型 — 與 res.partner 弱關聯
import logging

from odoo import api, fields, models
from odoo.tools import escape_psql

_logger = logging.getLogger(__name__)


class LineUser(models.Model):
    """LINE 用戶

    每個 LINE 用戶對應一筆記錄，透過 line_user_id (LINE UID) 唯一辨識。
    與 res.partner 是弱關聯（optional Many2one, ondelete='set null'）。
    """
    _name = 'line.user'
    _description = 'LINE 用戶'
    _rec_name = 'display_name'
    _order = 'last_login desc, create_date desc'

    # LINE Profile
    line_user_id = fields.Char('LINE User ID', required=True, index=True)
    display_name = fields.Char('顯示名稱')
    picture_url = fields.Char('頭像網址')
    status_message = fields.Char('狀態訊息')
    email = fields.Char('Email')

    # Messaging Channel 來源
    messaging_channel_id = fields.Char(
        'Messaging Channel ID', index=True,
        help='此用戶來自的 LINE Messaging API Channel ID')
    messaging_channel_name = fields.Char(
        'Messaging Channel',
        help='Messaging API Channel 的顯示名稱')

    # 弱關聯 Partner
    partner_id = fields.Many2one('res.partner', string='聯絡人',
        ondelete='set null', index=True)

    # 狀態
    is_follower = fields.Boolean('追蹤中', default=True)
    is_blocked = fields.Boolean('已封鎖', default=False)
    notification_enabled = fields.Boolean('啟用通知', default=True)

    # 時間
    follow_date = fields.Datetime('追蹤時間')
    unfollow_date = fields.Datetime('取消追蹤時間')
    last_login = fields.Datetime('最後登入')
    bound_at = fields.Datetime('綁定時間')

    # 偏好
    preferred_lang = fields.Selection([
        ('zh_TW', '繁體中文'), ('en_US', 'English'), ('ja_JP', '日本語'),
    ], string='偏好語言', default='zh_TW')

    # 統計
    push_count = fields.Integer('推播次數', default=0)
    event_count = fields.Integer('事件次數', default=0)

    _sql_constraints = [
        ('line_user_id_unique', 'UNIQUE(line_user_id)', 'LINE User ID 必須唯一'),
    ]

    # ------------------------------------------------------------------
    # 綁定 / 解綁
    # ------------------------------------------------------------------
    # 下面以 sudo 建立、綁定 line.user 或改寫聯絡人的 method 只供伺服器端
    # （webhook／LIFF controller、wizard、migration）呼叫，一律 @api.private，
    # 不能經 RPC 由使用者自己帶 LINE UID、email 或 partner 進來。
    # View 按鈕用的 action_bind_partner、unbind 維持 public，受 ACL 保護。

    def action_bind_partner(self):
        """View 按鈕：開啟綁定聯絡人向導"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': '綁定聯絡人',
            'res_model': 'line.bind.partner.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_line_user_id': self.id},
        }

    @api.private
    def bind_partner(self, partner_id):
        self.ensure_one()
        partner = self.env['res.partner'].browse(partner_id)
        if not partner.exists():
            return False
        vals = {'partner_id': partner_id, 'bound_at': fields.Datetime.now()}
        # 同步 email：partner → line.user（或反向）
        if partner.email and not self.email:
            vals['email'] = partner.email
        elif self.email and not partner.email:
            partner.sudo().write({'email': self.email})
        self.write(vals)
        # 同步到 mail.guest（如果 woow_odoo_livechat_line 已安裝）
        self._sync_to_mail_guest(partner_id)
        _logger.info('LINE %s 綁定 partner %s', self.line_user_id, partner.name)
        return True

    def _sync_to_mail_guest(self, partner_id):
        """同步綁定到對應的 mail.guest 記錄"""
        self.ensure_one()
        if 'mail.guest' not in self.env:
            return
        if not hasattr(self.env['mail.guest'], 'line_user_id'):
            return
        guests = self.env['mail.guest'].sudo().search([
            ('line_user_id', '=', self.line_user_id),
        ])
        for guest in guests:
            if guest.line_partner_id.id != partner_id:
                guest.write({'line_partner_id': partner_id})

    def write(self, vals):
        res = super().write(vals)
        # email 雙向同步：line.user → partner（避免遞迴）
        if 'email' in vals and not self.env.context.get('skip_email_sync'):
            for rec in self:
                if rec.partner_id and rec.email != rec.partner_id.email:
                    rec.partner_id.sudo().with_context(skip_email_sync=True).write(
                        {'email': rec.email or False})
        return res

    def unbind(self):
        self.ensure_one()
        self._sync_to_mail_guest(False)
        self.write({'partner_id': False, 'bound_at': False})
        return True

    # ------------------------------------------------------------------
    # 自動綁定 / 建立 Partner
    # ------------------------------------------------------------------

    @api.model
    def _auto_bind_or_create_partner(self, line_user):
        """自動綁定或建立聯絡人

        策略：
        1. 若 line.user 已有 partner_id → 跳過
        2. context 有 skip_auto_bind → 跳過（wizard 手動綁定時用）
        3. 若有 email 且已有同 email 的 partner → 不綁定、也不另建，維持未綁定
        4. 否則 → 建立新 partner，再綁定

        第 3 點：LINE 回傳的 email 沒有「已驗證屬於本人」的保證，只憑它綁定既有
        partner，等於讓任何人用別人的 email 取得對方的身分（下游 LIFF 會據此發出
        portal session）。要綁到既有 partner，必須另外證明擁有該信箱（LIFF 的確認信）
        或由員工用「綁定聯絡人」精靈手動綁定。
        """
        if line_user.partner_id:
            return
        if self.env.context.get('skip_auto_bind'):
            return
        Partner = self.env['res.partner'].sudo()
        # 不分大小寫的精確比對（escape_psql 讓 % 與 _ 不被當成萬用字元）
        if line_user.email and Partner.search_count(
                [('email', '=ilike', escape_psql(line_user.email.strip()))], limit=1):
            _logger.info('LINE: %s 的 email 對應到既有聯絡人，需確認信箱擁有權才綁定',
                         line_user.line_user_id)
            return
        name = line_user.display_name or ('LINE ' + line_user.line_user_id[:8])
        vals = {
            'name': name,
            'email': line_user.email or False,
        }
        # 不指定語言的話，聯絡人會拿到建立當下環境的語言（webhook 下多半是 en_US），
        # 之後 Odoo 寄給這位客人的範本信件（行事曆邀請、報價單…）全部變英文（H-17）。
        lang = self._active_lang(line_user.preferred_lang)
        if lang:
            vals['lang'] = lang
        partner = Partner.create(vals)
        _logger.info('LINE: 自動建立 partner %s (id=%s) for %s',
                     partner.name, partner.id, line_user.line_user_id)
        line_user.bind_partner(partner.id)

    @api.model
    def _active_lang(self, code):
        """code 若是這個資料庫已啟用的語言就回傳它，否則 False
        （res.partner.lang 只接受已啟用的語言）。"""
        return code if code and self.env['res.lang']._lang_get(code) else False

    @api.private
    @api.model
    def action_fix_partner_languages(self):
        """把綁定 LINE、卻被設成 en_US 的聯絡人改回 LINE 偏好語言。

        在 18.0.3.2.5 之前，從 LINE 自動建立的聯絡人都拿到建立當下環境的語言，
        英文有啟用的資料庫（markstudio）因此全部是 en_US。只改：
          * 綁定 LINE 用戶、目前是 en_US 的聯絡人；
          * 該 LINE 用戶的偏好語言不是 en_US，而且在這個資料庫已啟用；
          * 不屬於任何內部使用者——那會連帶改掉員工自己的後台介面語言。
        可以重複執行。18.0.3.2.5 的 migration 會呼叫一次。

        :return: 改了幾位聯絡人
        """
        fixed = 0
        line_users = self.sudo().search([
            ('partner_id', '!=', False),
            ('partner_id.lang', '=', 'en_US'),
        ])
        for line_user in line_users:
            partner = line_user.partner_id
            lang = self._active_lang(line_user.preferred_lang)
            if not lang or lang == 'en_US' or partner.lang != 'en_US':
                continue
            if partner.with_context(active_test=False).user_ids.filtered(lambda u: not u.share):
                continue
            partner.write({'lang': lang})
            fixed += 1
        if fixed:
            _logger.info('LINE: %d 位 LINE 聯絡人的語言由 en_US 改回 LINE 偏好語言', fixed)
        return fixed

    # ------------------------------------------------------------------
    # 查找 / 建立
    # ------------------------------------------------------------------

    @api.private
    @api.model
    def find_by_line_uid(self, line_user_id):
        return self.sudo().search([('line_user_id', '=', line_user_id)], limit=1)

    @api.private
    @api.model
    def create_or_update_from_webhook(self, line_user_id, profile_data=None,
                                       messaging_channel_id=None,
                                       messaging_channel_name=None):
        existing = self.find_by_line_uid(line_user_id)
        vals = {'line_user_id': line_user_id, 'is_follower': True, 'is_blocked': False}
        if messaging_channel_id:
            vals['messaging_channel_id'] = messaging_channel_id
        if messaging_channel_name:
            vals['messaging_channel_name'] = messaging_channel_name
        if profile_data:
            for src, dst in [('displayName', 'display_name'), ('pictureUrl', 'picture_url'),
                             ('statusMessage', 'status_message'), ('email', 'email')]:
                if profile_data.get(src):
                    vals[dst] = profile_data[src]
        if existing:
            existing.sudo().write(vals)
            if not existing.partner_id:
                self.sudo()._auto_bind_or_create_partner(existing)
            return existing
        vals['follow_date'] = fields.Datetime.now()
        line_user = self.sudo().create(vals)
        self.sudo()._auto_bind_or_create_partner(line_user)
        return line_user

    @api.private
    @api.model
    def create_or_update_from_liff(self, id_token_payload):
        line_uid = id_token_payload.get('sub')
        if not line_uid:
            return self.browse()
        existing = self.find_by_line_uid(line_uid)
        vals = {'line_user_id': line_uid, 'last_login': fields.Datetime.now()}
        if id_token_payload.get('name'):
            vals['display_name'] = id_token_payload['name']
        if id_token_payload.get('picture'):
            vals['picture_url'] = id_token_payload['picture']
        if id_token_payload.get('email'):
            vals['email'] = id_token_payload['email']
        if existing:
            existing.sudo().write(vals)
            if not existing.partner_id:
                self.sudo()._auto_bind_or_create_partner(existing)
            return existing
        vals.update({'follow_date': fields.Datetime.now(), 'is_follower': True})
        line_user = self.sudo().create(vals)
        self.sudo()._auto_bind_or_create_partner(line_user)
        return line_user
