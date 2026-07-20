"""Role definitions.

One place that maps the four business roles to Django permissions. Migrations
call sync_roles() so adding a permission here is picked up by a data migration
rather than needing manual admin work on every environment.

Later phases extend PERMISSIONS as their models land (subscribers, billing,
network). A permission named here that does not exist yet is skipped with a
warning rather than raising, so this file can name future permissions safely.
"""

import logging

from django.contrib.auth.models import Group, Permission

from .models import ROLE_COLLECTOR, ROLE_MANAGER, ROLE_OWNER, ROLE_TECHNICIAN

logger = logging.getLogger(__name__)


# codename lists per role. "app_label.codename" form.
#
# Guiding rule: "can record a payment" and "can cut off a customer" are not the
# same trust level, so they are never the same permission.
PERMISSIONS = {
    ROLE_OWNER: [
        # owners get everything via is_superuser in practice, but the group is
        # populated so a non-superuser owner is still workable
        'accountants.view_owner', 'accountants.add_owner', 'accountants.change_owner',
        'accountants.view_commission', 'accountants.change_commission',
        'accountants.view_invest', 'accountants.add_invest', 'accountants.change_invest',
        'accountants.view_earning', 'accountants.add_earning', 'accountants.change_earning',
        'accountants.view_companyprofile', 'accountants.change_companyprofile',
        'employ.view_employ', 'employ.add_employ', 'employ.change_employ',
        'billing.view_package', 'billing.add_package',
        'billing.change_package', 'billing.delete_package',
        'subscribers.view_subscriber', 'subscribers.add_subscriber',
        'subscribers.change_subscriber', 'subscribers.delete_subscriber',
        'network.view_router', 'network.add_router', 'network.change_router',
        'network.view_serviceevent',
    ],
    ROLE_MANAGER: [
        'subscribers.view_subscriber', 'subscribers.add_subscriber',
        'subscribers.change_subscriber',
        'network.view_router',
        'network.view_serviceevent',
        'billing.view_package',
        'onu.view_onu', 'onu.add_onu', 'onu.change_onu',
        'pop.view_pop', 'pop.add_pop', 'pop.change_pop',
        'tasks.view_tasks', 'tasks.add_tasks', 'tasks.change_tasks',
        'warehouse.view_warehouse', 'warehouse.add_warehouse', 'warehouse.change_warehouse',
        'employ.view_employ',
    ],
    ROLE_COLLECTOR: [
        # deliberately narrow: sees subscribers, records money, nothing else.
        # explicitly NOT change_subscriber — recording a payment and cutting
        # off a customer are not the same trust level.
        'subscribers.view_subscriber',
        'billing.view_package',
    ],
    ROLE_TECHNICIAN: [
        'subscribers.view_subscriber',
        'onu.view_onu', 'onu.change_onu',
        'pop.view_pop',
        'tasks.view_tasks', 'tasks.change_tasks',
        'warehouse.view_warehouse', 'warehouse.change_warehouse',
    ],
}


def sync_roles(apps=None, *, strict=True):
    """Create the role groups and set their permissions.

    Idempotent — safe to call repeatedly. Permissions are *set*, not added to,
    so removing an entry from PERMISSIONS removes it from the group on the
    next run.

    strict=False downgrades "permission not found" to debug, for the
    post_migrate path where partial permission sets are expected mid-migrate.
    Returns the list of missing codenames so callers can report on them.
    """
    group_model = apps.get_model('auth', 'Group') if apps else Group
    perm_model = apps.get_model('auth', 'Permission') if apps else Permission

    missing = []

    for role, codenames in PERMISSIONS.items():
        group, _ = group_model.objects.get_or_create(name=role)

        wanted = []
        for entry in codenames:
            app_label, codename = entry.split('.', 1)
            perm = perm_model.objects.filter(
                content_type__app_label=app_label, codename=codename
            ).first()
            if perm is None:
                # model not migrated yet, or renamed — surface it, don't crash
                missing.append(entry)
                logger.log(
                    logging.WARNING if strict else logging.DEBUG,
                    'sync_roles: permission %s not found, skipped', entry,
                )
                continue
            wanted.append(perm)

        group.permissions.set(wanted)

    return missing
