# Part of Odoo. See LICENSE file for full copyright and licensing details.
"""line.api.service 與 line.user 的伺服器端 method 不能經 RPC 呼叫。

這些 method 以 sudo 讀全域 LINE 憑證、建立或綁定 line.user、改寫聯絡人。
它們只供 controller、wizard、migration 以 Python 呼叫；若讓 portal／內部
使用者經 /web/dataset/call_kw 呼叫，等於把全域 token 與綁定權交出去。
"""

import json

from odoo.exceptions import AccessError
from odoo.service.model import get_public_method
from odoo.tests import HttpCase, TransactionCase, new_test_user, tagged

from odoo.addons.woow_line_base.models.line_api_service import LineApiService

DUMMY_TOKEN = 'dummy-messaging-token-for-rpc-test'
ATTACKER_UID = 'U' + 'a' * 32

LINE_USER_SERVER_ONLY = (
    'bind_partner',
    'find_by_line_uid',
    'create_or_update_from_webhook',
    'create_or_update_from_liff',
    'action_fix_partner_languages',
)
LINE_USER_VIEW_BUTTONS = ('action_bind_partner', 'unbind')


def _own_public_methods(cls):
    return sorted(
        name for name, value in vars(cls).items()
        if not name.startswith('_') and callable(value)
    )


@tagged('post_install', '-at_install', 'line_ci')
class TestServerOnlyMethods(TransactionCase):

    def test_every_public_service_method_is_rpc_private(self):
        names = _own_public_methods(LineApiService)
        self.assertGreater(len(names), 30, 'sanity：應涵蓋整個 LINE API 客戶端')
        service = self.env['line.api.service']
        for name in names:
            with self.subTest(method=name), self.assertRaises(AccessError):
                get_public_method(service, name)

    def test_line_user_server_methods_are_rpc_private(self):
        line_user = self.env['line.user']
        for name in LINE_USER_SERVER_ONLY:
            with self.subTest(method=name), self.assertRaises(AccessError):
                get_public_method(line_user, name)

    def test_view_buttons_stay_public(self):
        line_user = self.env['line.user']
        for name in LINE_USER_VIEW_BUTTONS:
            with self.subTest(method=name):
                self.assertTrue(get_public_method(line_user, name))

    def test_python_callers_are_unaffected(self):
        """api.private 只擋 RPC；webhook／LIFF controller 的 Python 呼叫照常。"""
        uid = 'U' + 'b' * 32
        line_user = self.env['line.user'].create_or_update_from_webhook(
            uid, {'displayName': 'Python caller'})
        self.assertEqual(line_user.line_user_id, uid)
        self.assertEqual(self.env['line.user'].find_by_line_uid(uid), line_user)
        self.env['ir.config_parameter'].sudo().set_param(
            'woow_line_base.messaging_access_token', DUMMY_TOKEN)
        self.assertEqual(self.env['line.api.service'].get_access_token(), DUMMY_TOKEN)


@tagged('post_install', '-at_install', 'line_ci')
class TestRpcExposure(HttpCase):
    """以 portal 使用者實際打 /web/dataset/call_kw（修正前兩個攻擊都會成功）。"""

    def setUp(self):
        super().setUp()
        self.env['ir.config_parameter'].sudo().set_param(
            'woow_line_base.messaging_access_token', DUMMY_TOKEN)
        new_test_user(self.env, login='line_rpc_portal', groups='base.group_portal')
        self.victim = self.env['res.partner'].create({
            'name': 'RPC Victim', 'email': 'rpc-victim@example.com'})

    def _portal_call_kw(self, model, method, args):
        self.authenticate('line_rpc_portal', 'line_rpc_portal')
        payload = {
            'jsonrpc': '2.0', 'method': 'call', 'id': 1,
            'params': {'model': model, 'method': method, 'args': args, 'kwargs': {}},
        }
        response = self.url_open(
            f'/web/dataset/call_kw/{model}/{method}',
            data=json.dumps(payload),
            headers={'Content-Type': 'application/json'},
        )
        return response.json()

    def test_portal_cannot_read_global_token(self):
        body = self._portal_call_kw('line.api.service', 'get_access_token', [[]])
        self.assertNotIn('result', body)
        self.assertNotIn(DUMMY_TOKEN, json.dumps(body))

    def test_portal_cannot_forge_line_user_binding(self):
        body = self._portal_call_kw(
            'line.user', 'create_or_update_from_webhook',
            [ATTACKER_UID, {'email': 'rpc-victim@example.com'}])
        self.assertNotIn('result', body)
        forged = self.env['line.user'].sudo().search([('line_user_id', '=', ATTACKER_UID)])
        self.assertFalse(forged)
        self.assertEqual(self.victim.email, 'rpc-victim@example.com')
