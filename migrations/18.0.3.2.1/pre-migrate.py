"""Repair ir_model_data rows that point at ir.config_parameter records which
no longer exist.

Why this exists: the config parameters are declared in
`data/ir_config_parameter.xml` inside `<data noupdate="1">`. If a parameter row
is ever deleted and recreated (Odoo's `set_param` unlinks the row when the
value is False/None, and the settings page used to write empty strings), the
xml_id keeps pointing at the old, now-missing id. On the next `-u` Odoo finds
the xml_id, cannot find the record, falls back to CREATE, and dies on
`ir_config_parameter_key_uniq` — the whole module upgrade aborts.

That happened for real on two tenants (mujimed, komibright) and had to be
repaired by hand before they could be upgraded at all. This migration makes it
self-healing.

Repointing is the safe direction: because the data file is noupdate, Odoo
SKIPS these records once the link is valid, so the live values survive.
Deleting the live rows to let Odoo recreate them would wipe them, since the
data file carries empty values.
"""

import logging

_logger = logging.getLogger(__name__)

MODULE = 'woow_line_base'


def migrate(cr, version):
    if not version:
        return

    cr.execute("""
        SELECT d.id, d.name, d.res_id
          FROM ir_model_data d
         WHERE d.module = %s
           AND d.model = 'ir.config_parameter'
           AND NOT EXISTS (
                 SELECT 1 FROM ir_config_parameter p WHERE p.id = d.res_id)
    """, (MODULE,))
    orphans = cr.fetchall()
    if not orphans:
        return

    repointed = dropped = 0
    for imd_id, name, old_res_id in orphans:
        # xml_id `config_login_channel_id` describes key `<prefix>.login_channel_id`.
        # Match on the suffix so it works whichever prefix the key uses.
        suffix = name[len('config_'):] if name.startswith('config_') else name

        cr.execute("""
            SELECT p.id
              FROM ir_config_parameter p
             WHERE p.key LIKE %s
               AND NOT EXISTS (
                     SELECT 1 FROM ir_model_data d2
                      WHERE d2.model = 'ir.config_parameter'
                        AND d2.res_id = p.id
                        AND d2.id <> %s)
             ORDER BY p.id
             LIMIT 1
        """, ('%%.%s' % suffix, imd_id))
        row = cr.fetchone()

        if row:
            cr.execute("UPDATE ir_model_data SET res_id = %s WHERE id = %s",
                       (row[0], imd_id))
            repointed += 1
            _logger.info('%s: repointed %s from %s to %s',
                         MODULE, name, old_res_id, row[0])
        else:
            # Nothing to adopt — drop the stale link so Odoo can create the
            # record cleanly instead of colliding with it.
            cr.execute("DELETE FROM ir_model_data WHERE id = %s", (imd_id,))
            dropped += 1
            _logger.info('%s: dropped stale xml_id %s (no matching parameter)',
                         MODULE, name)

    _logger.warning(
        '%s: repaired %d orphaned config-parameter xml_ids (%d repointed, '
        '%d dropped) — this would otherwise have aborted the upgrade',
        MODULE, len(orphans), repointed, dropped)
