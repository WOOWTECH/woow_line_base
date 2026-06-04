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

    # Rich Menu
    current_richmenu_id = fields.Many2one('line.richmenu', string='目前 Rich Menu',
        ondelete='set null')

    _sql_constraints = [
        ('line_user_id_unique', 'UNIQUE(line_user_id)', 'LINE User ID 必須唯一'),
    ]

    # ------------------------------------------------------------------
    # 推播快捷方法
    # ------------------------------------------------------------------

    def push_text(self, text):
        self.ensure_one()
        messages = [self.env['line.api.service'].build_text_message(text)]
        return self.env['line.api.service'].push(self, messages)

    def push_messages(self, messages):
        return self.env['line.api.service'].push(self, messages)

    def push_flex(self, alt_text, contents):
        self.ensure_one()
        messages = [{'type': 'flex', 'altText': alt_text, 'contents': contents}]
        return self.env['line.api.service'].push(self, messages)

    # ------------------------------------------------------------------
    # 綁定 / 解綁
    # ------------------------------------------------------------------

    def bind_partner(self, partner_id):
        self.ensure_one()
        partner = self.env['res.partner'].browse(partner_id)
        if not partner.exists():
            return False
        self.write({'partner_id': partner_id, 'bound_at': fields.Datetime.now()})
        _logger.info('LINE %s 綁定 partner %s', self.line_user_id, partner.name)
        return True

    def unbind(self):
        self.ensure_one()
        self.write({'partner_id': False, 'bound_at': False})
        return True

    # ------------------------------------------------------------------
    # 動作（View 按鈕用）
    # ------------------------------------------------------------------

    def action_open_partner(self):
        """Smart Button: 開啟綁定的聯絡人"""
        self.ensure_one()
        if self.partner_id:
            return {
                'type': 'ir.actions.act_window',
                'res_model': 'res.partner',
                'res_id': self.partner_id.id,
                'view_mode': 'form',
                'target': 'current',
            }
        return False

    # ------------------------------------------------------------------
    # 查找 / 建立
    # ------------------------------------------------------------------

    @api.model
    def find_by_line_uid(self, line_user_id):
        return self.sudo().search([('line_user_id', '=', line_user_id)], limit=1)

    @api.model
    def create_or_update_from_webhook(self, line_user_id, profile_data=None):
        existing = self.find_by_line_uid(line_user_id)
        vals = {'line_user_id': line_user_id, 'is_follower': True, 'is_blocked': False}
        if profile_data:
            for src, dst in [('displayName', 'display_name'), ('pictureUrl', 'picture_url'),
                             ('statusMessage', 'status_message'), ('email', 'email')]:
                if profile_data.get(src):
                    vals[dst] = profile_data[src]
        if existing:
            existing.sudo().write(vals)
            return existing
        vals['follow_date'] = fields.Datetime.now()
        return self.sudo().create(vals)

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
            return existing
        vals.update({'follow_date': fields.Datetime.now(), 'is_follower': True})
        return self.sudo().create(vals)
