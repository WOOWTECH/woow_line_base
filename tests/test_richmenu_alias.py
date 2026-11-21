# Part of Odoo. See LICENSE file for full copyright and licensing details.
from unittest.mock import MagicMock, patch

from odoo.tests import TransactionCase, tagged

POST = 'odoo.addons.woow_line_base.models.line_api_service.http_requests.post'


@tagged('post_install', '-at_install', 'line_ci')
class TestRichMenuAlias(TransactionCase):

    def test_update_alias_posts_to_alias_resource(self):
        response = MagicMock(status_code=200)
        with patch(POST, return_value=response) as post:
            ok = self.env['line.api.service'].richmenu_update_alias(
                'tab-staff', 'richmenu-abc', access_token='exact-token',
            )
        self.assertTrue(ok)
        self.assertEqual(
            post.call_args.args[0],
            'https://api.line.me/v2/bot/richmenu/alias/tab-staff',
        )
        self.assertEqual(post.call_args.kwargs['json'], {'richMenuId': 'richmenu-abc'})

    def test_update_alias_reports_line_rejection(self):
        with patch(POST, return_value=MagicMock(status_code=400)):
            self.assertFalse(self.env['line.api.service'].richmenu_update_alias(
                'tab-staff', 'richmenu-abc', access_token='exact-token',
            ))
