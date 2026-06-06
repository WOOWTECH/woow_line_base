# -*- coding: utf-8 -*-
# woow_line_base/models/res_config_settings.py
# 系統設定：Messaging API 金鑰
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    # LINE Login（LIFF 用）
    line_login_channel_id = fields.Char('LINE Login Channel ID',
        config_parameter='woow_line_base.login_channel_id')
    line_login_channel_secret = fields.Char('LINE Login Channel Secret',
        config_parameter='woow_line_base.login_channel_secret')

    # Messaging API
    line_messaging_channel_id = fields.Char('Messaging Channel ID',
        config_parameter='woow_line_base.messaging_channel_id')
    line_messaging_channel_secret = fields.Char('Messaging Channel Secret',
        config_parameter='woow_line_base.messaging_channel_secret')
    line_messaging_access_token = fields.Char('Messaging Access Token',
        config_parameter='woow_line_base.messaging_access_token')

    # 管理員 LINE User ID（預覽 Rich Menu 用）
    line_admin_user_id = fields.Char('管理員 LINE User ID',
        config_parameter='woow_line_base.admin_line_user_id',
        help='管理員的 LINE User ID，用於預覽 Rich Menu')

    # 自動推送 LINE 通知
    auto_line_notify = fields.Boolean(
        string='自動推送 LINE 通知',
        config_parameter='woow_line_base.auto_line_notify',
        help='啟用後，當任何 mail.thread 模型的追蹤欄位變更時，自動推送 LINE Flex 通知給有綁定 LINE 的跟隨者。',
    )
