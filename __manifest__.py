# -*- coding: utf-8 -*-
# woow_line_base/__manifest__.py
{
    'name': 'WOOW LINE Base',
    'version': '18.0.3.0.0',
    'category': 'Marketing',
    'summary': 'LINE 基礎層：統一 API 客戶端、用戶身份',
    'description': """
        WOOW LINE Base
        ===============
        LINE 平台整合基礎模組，提供：
        - 統一 LINE Messaging API 客戶端（支援全域 + per-channel 金鑰）
        - LINE 用戶身份模型（line.user）與聯絡人弱關聯
    """,
    'author': 'WOOWTECH',
    'website': 'https://woowtech.io',
    'license': 'LGPL-3',
    'depends': ['base'],
    'external_dependencies': {
        'python': ['requests'],
    },
    'data': [
        'security/line_security.xml',
        'security/ir.model.access.csv',
        'data/ir_config_parameter.xml',
        'views/line_user_views.xml',
        'views/res_partner_views.xml',
        'views/res_config_settings_views.xml',
        'views/menus.xml',
    ],
    'post_init_hook': '_post_init_hook',
    'application': True,
    'installable': True,
    'auto_install': False,
}
