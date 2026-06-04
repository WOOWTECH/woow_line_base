# -*- coding: utf-8 -*-
# woow_line_base/models/res_partner.py
# 擴充 res.partner：LINE 弱關聯
from odoo import api, fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    line_user_ids = fields.One2many('line.user', 'partner_id', string='LINE 帳號')
    has_line_bound = fields.Boolean('已綁定 LINE', compute='_compute_has_line_bound', store=True)

    @api.depends('line_user_ids', 'line_user_ids.is_follower')
    def _compute_has_line_bound(self):
        for partner in self:
            partner.has_line_bound = bool(partner.line_user_ids.filtered('is_follower'))

    def push_to_line(self, msg_or_flex):
        """推播 LINE 通知給此聯絡人"""
        self.ensure_one()
        line_users = self.line_user_ids.filtered(
            lambda lu: lu.is_follower and not lu.is_blocked and lu.notification_enabled
        )
        if not line_users:
            return False
        if isinstance(msg_or_flex, str):
            messages = [{'type': 'text', 'text': msg_or_flex}]
        elif isinstance(msg_or_flex, dict):
            messages = [{'type': 'flex', 'altText': msg_or_flex.get('altText', '通知'), 'contents': msg_or_flex.get('contents', msg_or_flex)}]
        else:
            messages = msg_or_flex if isinstance(msg_or_flex, list) else []
        return bool(self.env['line.api.service'].push(line_users, messages))
