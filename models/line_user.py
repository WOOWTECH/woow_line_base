# -*- coding: utf-8 -*-
# woow_line_base/models/line_user.py
# LINE 用戶身份模型 — 與 res.partner 弱關聯
import logging

from odoo import api, fields, models

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
        3. 若有 email → 搜尋同 email 的 partner，找到則綁定
        4. 否則 → 建立新 partner，再綁定
        """
        if line_user.partner_id:
            return
        if self.env.context.get('skip_auto_bind'):
            return
        Partner = self.env['res.partner'].sudo()
        partner = None
        if line_user.email:
            partner = Partner.search([('email', '=', line_user.email)], limit=1)
        if not partner:
            name = line_user.display_name or ('LINE ' + line_user.line_user_id[:8])
            partner = Partner.create({
                'name': name,
                'email': line_user.email or False,
            })
            _logger.info('LINE: 自動建立 partner %s (id=%s) for %s',
                         partner.name, partner.id, line_user.line_user_id)
        else:
            _logger.info('LINE: email 匹配綁定 partner %s (id=%s) for %s',
                         partner.name, partner.id, line_user.line_user_id)
        line_user.bind_partner(partner.id)

    # ------------------------------------------------------------------
    # 查找 / 建立
    # ------------------------------------------------------------------

    @api.model
    def find_by_line_uid(self, line_user_id):
        return self.sudo().search([('line_user_id', '=', line_user_id)], limit=1)

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
