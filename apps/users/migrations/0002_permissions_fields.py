"""Add the PermissionsMixin fields alongside the legacy role booleans.

Split into three migrations deliberately: 0002 adds, 0003 moves the data,
0004 drops the old columns. Doing it in one step would drop owner/employs/
staff/admin before anything had read them.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('auth', '0012_alter_user_first_name_max_length'),
        ('users', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='is_active',
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name='user',
            name='is_staff',
            field=models.BooleanField(
                default=False,
                help_text='Can sign in to the Django admin.',
            ),
        ),
        migrations.AddField(
            model_name='user',
            name='is_superuser',
            field=models.BooleanField(
                default=False,
                help_text='Designates that this user has all permissions '
                          'without explicitly assigning them.',
                verbose_name='superuser status',
            ),
        ),
        migrations.AddField(
            model_name='user',
            name='groups',
            field=models.ManyToManyField(
                blank=True,
                help_text='The groups this user belongs to. A user will get all '
                          'permissions granted to each of their groups.',
                related_name='user_set',
                related_query_name='user',
                to='auth.group',
                verbose_name='groups',
            ),
        ),
        migrations.AddField(
            model_name='user',
            name='user_permissions',
            field=models.ManyToManyField(
                blank=True,
                help_text='Specific permissions for this user.',
                related_name='user_set',
                related_query_name='user',
                to='auth.permission',
                verbose_name='user permissions',
            ),
        ),
        migrations.AlterField(
            model_name='user',
            name='first_name',
            field=models.CharField(blank=True, max_length=245),
        ),
        migrations.AlterField(
            model_name='user',
            name='last_name',
            field=models.CharField(blank=True, max_length=245),
        ),
        migrations.AlterField(
            model_name='user',
            name='gender',
            field=models.CharField(blank=True, max_length=245),
        ),
        migrations.AlterModelOptions(
            name='user',
            options={'ordering': ['email']},
        ),
    ]
