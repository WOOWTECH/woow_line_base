# -*- coding: utf-8 -*-
# woow_line_base/wizard/line_bind_partner_wizard.py
from odoo import fields, models


class LineBindPartnerWizard(models.TransientModel):
    """綁定 LINE 用戶到聯絡人的向導"""
    _name = 'line.bind.partner.wizard'
    _description = '綁定 LINE 用戶到聯絡人'

    line_user_id = fields.Many2one(
        'line.user', string='LINE 用戶',
        required=True, readonly=True,
    )
    partner_id = fields.Many2one(
        'res.partner', string='聯絡人',
        required=True,
    )

    def action_bind(self):
        """執行綁定"""
        self.ensure_one()
        self.line_user_id.bind_partner(self.partner_id.id)
        return {'type': 'ir.actions.act_window_close'}
