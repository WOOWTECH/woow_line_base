# Part of Odoo. See LICENSE file for full copyright and licensing details.
"""Regression tests for the 2026-09 pre-deployment security fixes."""

from unittest.mock import patch

from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestAccessTokenVerification(TransactionCase):
    """The LINE verify endpoint returns 200 for a token issued by ANY Login
    channel. Without comparing client_id, someone else's channel could mint a
    token that logs into this tenant."""

    def setUp(self):
        super().setUp()
        self.api = self.env['line.api.service']
        self.ICP = self.env['ir.config_parameter'].sudo()

    def _fake_verify(self, payload, status=200):
        class Resp:
            status_code = status

            def json(self):
                return payload
        return Resp()

    def test_fails_closed_when_channel_id_not_configured(self):
        """An unset parameter must deny, never wave the token through."""
        self.ICP.set_param('woow_line_base.login_channel_id', '')
        with patch('odoo.addons.woow_line_base.models.line_api_service'
                   '.http_requests.get',
                   return_value=self._fake_verify({'client_id': '999'})):
            self.assertIsNone(self.api.verify_access_token('any-token'))

    def test_rejects_token_from_another_channel(self):
        self.ICP.set_param('woow_line_base.login_channel_id', '1111111111')
        with patch('odoo.addons.woow_line_base.models.line_api_service'
                   '.http_requests.get',
                   return_value=self._fake_verify({'client_id': '2222222222'})):
            self.assertIsNone(
                self.api.verify_access_token('token-from-a-foreign-channel'))

    def test_reads_the_key_its_consumers_write(self):
        """The parameter lives under woow_line_base.*; reading a different
        namespace would make the check fail closed on every tenant."""
        import inspect
        src = inspect.getsource(type(self.api).verify_access_token)
        self.assertIn('woow_line_base.login_channel_id', src)
        self.assertNotIn('woow_odoo_line_liff.login_channel_id', src)


@tagged('post_install', '-at_install')
class TestPartnerLineUserAccess(TransactionCase):
    """B-7: res.partner.write() read a one2many on line.user without sudo.
    Odoo 18 checks read access before optimising the domain, so any employee
    outside the LINE manager group hit AccessError just for editing an email
    — and the whole write rolled back."""

    def test_non_manager_can_edit_a_contact_email(self):
        # group_partner_manager is what grants res.partner write at all; the
        # point of this test is a user who HAS that but is NOT a LINE manager.
        employee = self.env['res.users'].create({
            'name': 'plain employee',
            'login': 'plain_employee_b7',
            'groups_id': [(6, 0, [
                self.env.ref('base.group_user').id,
                self.env.ref('base.group_partner_manager').id,
            ])],
        })
        self.assertFalse(
            employee.has_group('woow_line_base.group_line_manager'),
            'precondition: this user must NOT be a LINE manager')

        partner = self.env['res.partner'].create({'name': 'b7 contact'})
        partner.with_user(employee).write({'email': 'changed@example.com'})
        self.assertEqual(partner.email, 'changed@example.com')

    def test_internal_users_have_read_only_line_user_access(self):
        """The ACL must grant read without opening the PII up to writes."""
        acl = self.env['ir.model.access'].search([
            ('model_id.model', '=', 'line.user'),
            ('group_id', '=', self.env.ref('base.group_user').id),
        ])
        self.assertTrue(acl, 'internal users need a read ACL on line.user')
        self.assertTrue(acl.perm_read)
        self.assertFalse(acl.perm_write)
        self.assertFalse(acl.perm_create)
        self.assertFalse(acl.perm_unlink)


@tagged('post_install', '-at_install')
class TestPushResilience(TransactionCase):
    """新-4: push() logs to line.push.log, a model that lives in the LIFF
    module — but this module only depends on base. Installing base+livechat
    without liff is legal, and every push would have raised KeyError."""

    def test_push_survives_without_the_log_model(self):
        api = self.env['line.api.service']
        real_get = type(self.env).__getitem__

        def missing_log(env_self, name):
            if name == 'line.push.log':
                raise KeyError(name)
            return real_get(env_self, name)

        with patch.object(type(self.env), '__getitem__', missing_log), \
             patch.object(type(api), '_resolve_token', return_value=None):
            # _resolve_token None short-circuits before any HTTP; the point is
            # that reaching push() at all must not explode on the missing model
            self.assertEqual(api.push(self.env['line.user'], []), [])
