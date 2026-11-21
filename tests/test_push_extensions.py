# Part of Odoo. See LICENSE file for full copyright and licensing details.
import time
from unittest.mock import patch

from odoo import SUPERUSER_ID, api, sql_db
from odoo.addons.woow_line_base.models.line_api_service import LineApiService
from odoo.tests import TransactionCase, tagged
from odoo.tools import mute_logger


@tagged('post_install', '-at_install', 'line_ci')
class TestPushExtensions(TransactionCase):

    def setUp(self):
        super().setUp()
        self.api = self.env['line.api.service']

    def test_default_push_log_extension_is_content_free(self):
        # Call the shared Python implementation directly.  A site module may
        # legitimately override the registry method when integration tests run
        # with additional addons installed.
        self.assertEqual(
            LineApiService._push_log_extra_vals(
                self.api, False, [{'type': 'text', 'text': 'not retained'}]),
            {},
        )

    def test_locked_push_count_is_skipped_without_aborting_business_work(self):
        database = sql_db.db_connect(self.env.cr.dbname)
        line_user_id = partner_id = False
        lock_cr = None
        try:
            with database.cursor() as setup_cr:
                setup_env = api.Environment(setup_cr, SUPERUSER_ID, {})
                line_user = setup_env['line.user'].create({
                    'line_user_id': 'U-push-counter-lock-test',
                    'display_name': 'Counter Lock Test',
                    'push_count': 0,
                })
                line_user_id = line_user.id
                setup_cr.commit()

            lock_cr = database.cursor()
            lock_cr.execute('SELECT id FROM line_user WHERE id = %s FOR UPDATE',
                            (line_user_id,))
            lock_cr.execute('SELECT pg_backend_pid()')
            lock_backend_pid = lock_cr.fetchone()[0]

            with database.cursor() as worker_cr:
                worker_env = api.Environment(worker_cr, SUPERUSER_ID, {})
                worker_cr.execute('SELECT pg_backend_pid()')
                self.assertNotEqual(worker_cr.fetchone()[0], lock_backend_pid)
                service = worker_env['line.api.service']
                started = time.monotonic()
                self.assertFalse(service._bump_push_count(
                    worker_env['line.user'].browse(line_user_id)))
                self.assertLess(time.monotonic() - started, 1.0)

                # The same transaction must remain usable after the skipped
                # statistic.  Commit proves it was not left aborted.
                partner = worker_env['res.partner'].create({
                    'name': 'Business work after locked LINE counter',
                })
                partner_id = partner.id
                worker_cr.commit()

            lock_cr.rollback()
            lock_cr.close()
            lock_cr = None

            with database.cursor() as worker_cr:
                worker_env = api.Environment(worker_cr, SUPERUSER_ID, {})
                self.assertTrue(worker_env['line.api.service']._bump_push_count(
                    worker_env['line.user'].browse(line_user_id)))
                worker_cr.commit()

            with database.cursor() as verify_cr:
                verify_cr.execute('SELECT push_count FROM line_user WHERE id = %s',
                                  (line_user_id,))
                self.assertEqual(verify_cr.fetchone()[0], 1)
        finally:
            if lock_cr is not None:
                lock_cr.rollback()
                lock_cr.close()
            if line_user_id or partner_id:
                with database.cursor() as cleanup_cr:
                    cleanup_env = api.Environment(cleanup_cr, SUPERUSER_ID, {})
                    if line_user_id:
                        cleanup_env['line.user'].browse(line_user_id).unlink()
                    if partner_id:
                        cleanup_env['res.partner'].browse(partner_id).unlink()
                    cleanup_cr.commit()

    def test_database_counter_error_isolated_from_business_transaction(self):
        database = sql_db.db_connect(self.env.cr.dbname)
        line_user_id = partner_id = False
        try:
            with database.cursor() as setup_cr:
                setup_env = api.Environment(setup_cr, SUPERUSER_ID, {})
                line_user = setup_env['line.user'].create({
                    'line_user_id': 'U-push-counter-db-error-test',
                    'display_name': 'Counter DB Error Test',
                    'push_count': 0,
                })
                line_user_id = line_user.id
                setup_cr.commit()

            with database.cursor() as worker_cr:
                worker_env = api.Environment(worker_cr, SUPERUSER_ID, {})
                cursor_type = type(worker_cr)
                original_execute = cursor_type.execute

                def fail_counter_sql(cursor, query, params=None, *args, **kwargs):
                    if 'UPDATE line_user SET push_count' in query:
                        # A real PostgreSQL error marks the transaction aborted
                        # until the enclosing savepoint rolls it back.
                        return original_execute(cursor, 'SELECT 1 / 0')
                    return original_execute(cursor, query, params, *args, **kwargs)

                with mute_logger('odoo.sql_db'), \
                     patch.object(cursor_type, 'execute', fail_counter_sql):
                    self.assertFalse(
                        worker_env['line.api.service']._bump_push_count(
                            worker_env['line.user'].browse(line_user_id)))

                partner = worker_env['res.partner'].create({
                    'name': 'Business work after LINE counter SQL error',
                })
                partner_id = partner.id
                worker_cr.commit()

            with database.cursor() as verify_cr:
                verify_cr.execute('SELECT push_count FROM line_user WHERE id = %s',
                                  (line_user_id,))
                self.assertEqual(verify_cr.fetchone()[0], 0)
                verify_cr.execute('SELECT id FROM res_partner WHERE id = %s',
                                  (partner_id,))
                self.assertEqual(verify_cr.fetchone()[0], partner_id)
        finally:
            if line_user_id or partner_id:
                with database.cursor() as cleanup_cr:
                    cleanup_env = api.Environment(cleanup_cr, SUPERUSER_ID, {})
                    if line_user_id:
                        cleanup_env['line.user'].browse(line_user_id).unlink()
                    if partner_id:
                        cleanup_env['res.partner'].browse(partner_id).unlink()
                    cleanup_cr.commit()
