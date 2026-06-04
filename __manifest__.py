# -*- coding: utf-8 -*-
# woow_line_base/__manifest__.py
# LINE 基礎模組 — 統一 API 客戶端、用戶身份、Rich Menu 管理
{
    'name': 'WOOW LINE Base',
    'version': '18.0.1.0.0',
    'category': 'Marketing',
    'summary': 'LINE 基礎層：統一 API、用戶身份、Rich Menu、推播記錄',
    'description': """
        WOOW LINE Base
        ===============
        LINE 平台整合基礎模組，提供：
        - 統一 LINE Messaging API 客戶端（支援全域 + per-channel 金鑰）
        - LINE 用戶身份模型（line.user）與聯絡人弱關聯
        - Rich Menu 管理（建立/上傳/綁定/Tab 切換）
        - Webhook 事件記錄 + 推播記錄
        - 360 度客戶視圖（LINE 用戶 ↔ 聯絡人互看）
    """,
    'author': 'WOOWTECH',
    'website': 'https://woowtech.io',
    'license': 'LGPL-3',
    'depends': [
        'base',
        'mail',
    ],
    'external_dependencies': {
        'python': ['requests'],
    },
    'data': [
        # 1. 安全性
        'security/line_security.xml',
        'security/ir.model.access.csv',
        # 2. 資料
        'data/ir_config_parameter.xml',
        # 3. 視圖
        'views/line_user_views.xml',
        'views/line_richmenu_views.xml',
        'views/line_logs_views.xml',
        'views/res_partner_views.xml',
        'views/res_config_settings_views.xml',
        'views/menus.xml',
    ],
    'application': True,
    'installable': True,
    'auto_install': False,
}
