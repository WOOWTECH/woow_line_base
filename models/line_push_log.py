# -*- coding: utf-8 -*-
# woow_line_base/models/line_push_log.py
# 推播記錄
from odoo import fields, models


class LinePushLog(models.Model):
    _name = 'line.push.log'
    _description = 'LINE 推播記錄'
    _order = 'create_date desc'

    line_user_id = fields.Many2one('line.user', string='LINE 用戶', ondelete='set null', index=True)
    messages = fields.Text('訊息內容')
    status_code = fields.Integer('HTTP 狀態碼')
    response_body = fields.Text('回應內容')
    success = fields.Boolean('成功', default=False, index=True)
    create_date = fields.Datetime('建立時間', readonly=True)
