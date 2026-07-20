"""Local development settings."""

from .base import *  # noqa: F401,F403

DEBUG = True

ALLOWED_HOSTS = ['localhost', '127.0.0.1', '[::1]', 'testserver']

# Run Celery tasks inline so provisioning work is debuggable without a
# broker running. Set CELERY_TASK_ALWAYS_EAGER=False once Redis is up.
CELERY_TASK_ALWAYS_EAGER = config('CELERY_EAGER', default=True, cast=bool)  # noqa: F405
CELERY_TASK_EAGER_PROPAGATES = True

EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
