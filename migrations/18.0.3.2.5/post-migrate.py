# -*- coding: utf-8 -*-
"""18.0.3.2.5：把從 LINE 自動建立、卻被設成 en_US 的聯絡人改回 LINE 偏好語言。

之前建立聯絡人時沒有指定語言，英文有啟用的資料庫因此全部是 en_US，Odoo 寄給
這些客人的範本信件（以及 LINE 通知卡片的來源信件）都是英文（H-17）。
規則與防護（不動員工、不動偏好英文的客人）見 line.user.action_fix_partner_languages。
"""
import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    fixed = env['line.user'].action_fix_partner_languages()
    _logger.info('woow_line_base 18.0.3.2.5：更正 %d 位 LINE 聯絡人的語言', fixed)
