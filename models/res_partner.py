# -*- coding: utf-8 -*-
# woow_line_base/models/res_partner.py
# 擴充 res.partner：LINE 弱關聯
from odoo import fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'
    line_user_ids = fields.One2many('line.user', 'partner_id', string='LINE 帳號')
