# -*- coding: utf-8 -*-
# woow_line_base/models/res_partner.py
# 擴充 res.partner：LINE 弱關聯 + email 雙向同步
from odoo import api, fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'
    line_user_ids = fields.One2many('line.user', 'partner_id', string='LINE 帳號')

    def write(self, vals):
        res = super().write(vals)
        # email 反向同步：partner → line.user
        if 'email' in vals:
            for partner in self:
                for lu in partner.line_user_ids:
                    if lu.email != partner.email:
                        lu.with_context(skip_email_sync=True).write({'email': partner.email or False})
        return res
