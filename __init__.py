# -*- coding: utf-8 -*-
from . import models


def _post_init_hook(env):
    """Clean up legacy group_line_user for admin-only access pattern."""
    group_user = env.ref('woow_line_base.group_line_user', raise_if_not_found=False)
    if group_user:
        # Hide from user form by removing category
        group_user.sudo().write({'category_id': False})
    group_manager = env.ref('woow_line_base.group_line_manager', raise_if_not_found=False)
    if group_manager:
        # Remove implied_ids link to group_line_user
        group_manager.sudo().write({'implied_ids': [(5,)]})
