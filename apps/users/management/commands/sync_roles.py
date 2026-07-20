"""Re-apply role permissions from apps/users/roles.py.

Runs automatically on migrate. Use this to re-sync after editing PERMISSIONS
without generating a migration, and to surface typos — anything named in
PERMISSIONS that does not resolve to a real permission is reported here.
"""

from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand

from apps.users.roles import PERMISSIONS, sync_roles


class Command(BaseCommand):
    help = 'Create role groups and set their permissions.'

    def handle(self, *args, **options):
        missing = sync_roles(strict=False)

        for role in PERMISSIONS:
            count = Group.objects.get(name=role).permissions.count()
            self.stdout.write(f'  {role:12} {count:3d} permissions')

        if missing:
            self.stdout.write('')
            self.stderr.write(
                self.style.WARNING(f'{len(missing)} permission(s) did not resolve:')
            )
            for entry in sorted(set(missing)):
                self.stderr.write(f'  - {entry}')
            self.stderr.write(
                'These are either typos or models that have not been migrated yet.'
            )
        else:
            self.stdout.write(self.style.SUCCESS('\nAll permissions resolved.'))
