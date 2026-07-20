"""Drop the legacy role booleans now that 0003 has moved their data.

Reversing this migration restores the columns; 0003's backwards() then
repopulates them from groups.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0003_migrate_roles'),
    ]

    operations = [
        migrations.RemoveField(model_name='user', name='owner'),
        migrations.RemoveField(model_name='user', name='employs'),
        migrations.RemoveField(model_name='user', name='staff'),
        migrations.RemoveField(model_name='user', name='admin'),
    ]
