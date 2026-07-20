"""Production settings.

manage.py check --deploy must pass clean against this module.
"""

from .base import *  # noqa: F401,F403

DEBUG = False

# No default — a missing ALLOWED_HOSTS should fail loudly at boot rather
# than silently accepting any Host header.
ALLOWED_HOSTS = config('ALLOWED_HOSTS', cast=Csv())  # noqa: F405

SECURE_SSL_REDIRECT = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = 'same-origin'

SESSION_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_SECURE = True
CSRF_TRUSTED_ORIGINS = config('CSRF_TRUSTED_ORIGINS', default='', cast=Csv())  # noqa: F405

X_FRAME_OPTIONS = 'DENY'

STORAGES = {
    'default': {
        'BACKEND': 'django.core.files.storage.FileSystemStorage',
    },
    'staticfiles': {
        'BACKEND': 'django.contrib.staticfiles.storage.ManifestStaticFilesStorage',
    },
}

CELERY_TASK_ALWAYS_EAGER = False
