"""Move the legacy role booleans into groups and real permission flags.

Mapping:
    admin=True   -> is_superuser + is_staff   (they had full access already)
    staff=True   -> is_staff
    owner=True   -> 'owner' group
    employs=True -> 'technician' group

Anyone with no flags at all lands in 'technician', the least-privileged role,
rather than being left with no group and therefore no access. Erring toward
the narrowest role is the safe direction — a user who needs more will say so,
whereas silently over-granting is how the original bug happened.
"""

from django.db import migrations


def forwards(apps, schema_editor):
    from apps.users.roles import PERMISSIONS

    User = apps.get_model('users', 'User')
    Group = apps.get_model('auth', 'Group')

    # Only create the groups here. Their permissions are attached by the
    # post_migrate handler in apps.py, because Permission rows do not exist
    # yet at this point on a fresh database.
    groups = {}
    for name in PERMISSIONS:
        groups[name], _ = Group.objects.get_or_create(name=name)

    for user in User.objects.all():
        user.is_active = True
        user.is_staff = bool(user.staff or user.admin)
        user.is_superuser = bool(user.admin)
        user.save(update_fields=['is_active', 'is_staff', 'is_superuser'])

        assigned = []
        if user.owner and 'owner' in groups:
            assigned.append(groups['owner'])
        if user.employs and 'technician' in groups:
            assigned.append(groups['technician'])

        if not assigned and 'technician' in groups:
            assigned.append(groups['technician'])

        user.groups.set(assigned)


def backwards(apps, schema_editor):
    User = apps.get_model('users', 'User')

    for user in User.objects.all():
        user.staff = user.is_staff
        user.admin = user.is_superuser
        user.owner = user.groups.filter(name='owner').exists()
        user.employs = user.groups.filter(name='technician').exists()
        user.save(update_fields=['staff', 'admin', 'owner', 'employs'])


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0002_permissions_fields'),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
