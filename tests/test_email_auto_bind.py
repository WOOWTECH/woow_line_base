# Part of Odoo. See LICENSE file for full copyright and licensing details.
"""LINE 回傳的 email 不能單獨用來綁定既有聯絡人。"""

from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install', 'line_ci')
class TestEmailAutoBind(TransactionCase):

    def setUp(self):
        super().setUp()
        self.Partner = self.env['res.partner'].sudo()
        self.LineUser = self.env['line.user'].sudo()

    def test_existing_partner_email_is_not_auto_bound(self):
        victim = self.Partner.create({'name': 'Existing customer', 'email': 'owner@example.com'})
        before = self.Partner.search_count([])
        line_user = self.LineUser.create_or_update_from_liff({
            'sub': 'U' + 'c' * 32, 'name': 'Someone', 'email': 'owner@example.com'})
        self.assertTrue(line_user)
        self.assertFalse(line_user.partner_id, 'email claim alone must not bind an existing partner')
        self.assertEqual(self.Partner.search_count([]), before, 'no duplicate partner either')
        self.assertEqual(victim.email, 'owner@example.com')

    def test_new_email_still_creates_and_binds_partner(self):
        line_user = self.LineUser.create_or_update_from_liff({
            'sub': 'U' + 'd' * 32, 'name': 'New customer', 'email': 'new-customer@example.com'})
        self.assertTrue(line_user.partner_id)
        self.assertEqual(line_user.partner_id.email, 'new-customer@example.com')

    def test_without_email_creates_partner(self):
        line_user = self.LineUser.create_or_update_from_webhook(
            'U' + 'e' * 32, {'displayName': 'Webhook follower'})
        self.assertEqual(line_user.partner_id.name, 'Webhook follower')

    def test_case_variant_of_existing_email_is_not_auto_bound(self):
        self.Partner.create({'name': 'Existing customer', 'email': 'Owner.Case@Example.com'})
        line_user = self.LineUser.create_or_update_from_liff({
            'sub': 'U' + 'f' * 32, 'name': 'Someone', 'email': 'owner.case@example.com'})
        self.assertFalse(line_user.partner_id)

    def test_like_wildcards_do_not_match_other_contacts(self):
        self.Partner.create({'name': 'Existing customer', 'email': 'axb@example.com'})
        line_user = self.LineUser.create_or_update_from_liff({
            'sub': 'U' + '1' * 32, 'name': 'Someone', 'email': 'a_b@example.com'})
        self.assertTrue(line_user.partner_id, '"_" must not act as a wildcard')
        self.assertEqual(line_user.partner_id.email, 'a_b@example.com')
