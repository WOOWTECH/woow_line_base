# -*- coding: utf-8 -*-
# woow_line_base/models/line_event_log.py
# Webhook 事件記錄
from odoo import fields, models


class LineEventLog(models.Model):
    _name = 'line.event.log'
    _description = 'LINE 事件記錄'
    _order = 'create_date desc'

    line_user_id = fields.Many2one('line.user', string='LINE 用戶', ondelete='set null', index=True)
    event_type = fields.Selection([
        ('follow', '追蹤'), ('unfollow', '取消追蹤'), ('message', '訊息'),
        ('postback', 'Postback'), ('join', '加入群組'), ('leave', '離開群組'),
        ('memberJoined', '成員加入'), ('memberLeft', '成員離開'),
        ('beacon', 'Beacon'), ('accountLink', '帳號連結'),
        ('things', 'IoT'), ('unsend', '收回'), ('videoPlayComplete', '影片播放完成'),
        ('other', '其他'),
    ], string='事件類型', index=True)
    message_type = fields.Selection([
        ('text', '文字'), ('image', '圖片'), ('video', '影片'), ('audio', '音訊'),
        ('location', '位置'), ('sticker', '貼圖'), ('file', '檔案'), ('other', '其他'),
    ], string='訊息類型')
    raw_payload = fields.Text('原始 Payload')
    text_content = fields.Char('文字內容')
    processed = fields.Boolean('已處理', default=False)
    error_msg = fields.Text('錯誤訊息')
    create_date = fields.Datetime('建立時間', readonly=True)
