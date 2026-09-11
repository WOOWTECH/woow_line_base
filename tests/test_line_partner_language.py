# -*- coding: utf-8 -*-
"""Contacts created from LINE must use the customer's LINE language.

A contact auto-created for a LINE friend was given no language, so it took
whatever language the creating environment had — en_US on a database where
English is active. All five LINE customers on markstudio ended up en_US while
their LINE preferred language was zh_TW, so every Odoo email template they
received (calendar invitation, quotation, ...) rendered in English (H-17,
2026-09-12).
"""
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged('post_install', '-at_install', 'line_ci')
class TestLinePartnerLanguage(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env['res.lang']._activate_lang('zh_TW')

    def _line_user(self, uid_char, partner, **vals):
        return self.env['line.user'].create(dict({
            'line_user_id': 'U' + uid_char * 32, 'display_name': partner.name,
            'partner_id': partner.id,
        }, **vals))

    def test_contact_created_from_a_liff_login_uses_the_line_language(self):
        line_user = self.env['line.user'].with_context(lang='en_US').create_or_update_from_liff({
            'sub': 'U' + '1' * 32, 'name': 'LINE 客人',
        })
        self.assertTrue(line_user.partner_id, 'a contact is created for the LINE friend')
        self.assertEqual(line_user.preferred_lang, 'zh_TW')
        self.assertEqual(line_user.partner_id.lang, 'zh_TW',
                         "the new contact must use the customer's LINE language, not the server's")

    def test_fixing_existing_line_contacts_only_touches_line_customers(self):
        Partner = self.env['res.partner']
        customer = Partner.create({'name': 'English-by-accident customer', 'lang': 'en_US'})
        self._line_user('2', customer)
        staff = self.env['res.users'].create({
            'name': 'Staff member', 'login': 'line_lang_staff', 'lang': 'en_US'})
        self._line_user('3', staff.partner_id)
        wants_english = Partner.create({'name': 'Prefers English', 'lang': 'en_US'})
        self._line_user('4', wants_english, preferred_lang='en_US')
        not_on_line = Partner.create({'name': 'Not a LINE contact', 'lang': 'en_US'})

        fixed = self.env['line.user'].action_fix_partner_languages()

        self.assertEqual(customer.lang, 'zh_TW')
        self.assertEqual(staff.partner_id.lang, 'en_US',
                         "an employee's own interface language must never be changed")
        self.assertEqual(wants_english.lang, 'en_US')
        self.assertEqual(not_on_line.lang, 'en_US')
        self.assertEqual(fixed, 1)
