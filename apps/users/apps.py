from django.apps import AppConfig
from django.db.models.signals import post_migrate


def _sync_roles_after_migrate(sender, **kwargs):
    """Populate role permissions once every app's permissions exist.

    Django creates Permission rows in its own post_migrate handler, so a data
    migration that reads them finds nothing on a fresh database and silently
    produces empty groups.

    Connected without a sender so it runs after *each* app migrates: early
    passes see a partial permission set, and the final pass — once every app
    is done — sets the complete one. sync_roles() uses set(), so repeated runs
    converge rather than accumulate. Missing permissions are logged at debug
    here; use `manage.py sync_roles` to see them as warnings.
    """
    from .roles import sync_roles

    sync_roles(strict=False)


class UsersConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.users'

    def ready(self):
        import apps.users.signals  # noqa: F401

        post_migrate.connect(_sync_roles_after_migrate)
