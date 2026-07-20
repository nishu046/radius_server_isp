"""Settings shared by every environment.

Environment-specific values live in dev.py and prod.py. Pick one with
DJANGO_SETTINGS_MODULE; manage.py defaults to dev.
"""

import os
from pathlib import Path

from decouple import Csv, config

# isp_management/settings/base.py -> project root
BASE_DIR = Path(__file__).resolve().parent.parent.parent


# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = config('SECRET_KEY')

# Overridden in dev.py / prod.py. Never default to True.
DEBUG = config('DEBUG', default=False, cast=bool)

ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='', cast=Csv())


# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'crispy_forms',
    'crispy_bootstrap5',
    'django_filters',
    'django_celery_beat',
    # Custom applications
    'apps.users.apps.UsersConfig',
    'apps.network',
    'apps.employ',
    'apps.packages',
    'apps.onu',
    'apps.pop',
    'apps.warehouse',
    'apps.tasks',
    'apps.clients',
    'apps.accountants',
]

# user model
AUTH_USER_MODEL = 'users.User'

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'isp_management.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'apps.accountants.context_processors.company_profile',
            ],
        },
    },
]

WSGI_APPLICATION = 'isp_management.wsgi.application'


# Database
#
# DATABASE_URL drives everything. Defaults to SQLite so a fresh checkout
# runs without infrastructure, but PostgreSQL is the supported target —
# Celery workers writing concurrently and the P7 expiry sweep's
# select_for_update(skip_locked=True) both need it.
#
#   postgres://user:pass@localhost:5432/isp

DATABASE_URL = config('DATABASE_URL', default=f'sqlite:///{BASE_DIR / "db.sqlite3"}')


def _parse_database_url(url):
    from urllib.parse import unquote, urlparse

    parsed = urlparse(url)

    if parsed.scheme == 'sqlite':
        return {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': url.replace('sqlite:///', '', 1),
        }

    if parsed.scheme in ('postgres', 'postgresql'):
        return {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': parsed.path.lstrip('/'),
            'USER': unquote(parsed.username or ''),
            'PASSWORD': unquote(parsed.password or ''),
            'HOST': parsed.hostname or '',
            'PORT': str(parsed.port or ''),
            'CONN_MAX_AGE': 60,
        }

    raise ValueError(f'Unsupported DATABASE_URL scheme: {parsed.scheme}')


DATABASES = {'default': _parse_database_url(DATABASE_URL)}


# Password validation

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LOGIN_URL = 'login'
LOGIN_REDIRECT_URL = 'dashboard:dashboard'
LOGOUT_REDIRECT_URL = '/'


# Internationalization

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Asia/Dhaka'
USE_I18N = True
USE_TZ = True


# Static files

STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'

# Media files
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'


# crispy-forms — removed entirely in P3 when Tailwind form partials land
CRISPY_ALLOWED_TEMPLATE_PACKS = 'bootstrap5'
CRISPY_TEMPLATE_PACK = 'bootstrap5'


# Celery
CELERY_BROKER_URL = config('CELERY_BROKER_URL', default='redis://localhost:6379/0')
CELERY_RESULT_BACKEND = config('CELERY_RESULT_BACKEND', default='redis://localhost:6379/1')
CELERY_TASK_DEFAULT_QUEUE = 'default'
CELERY_TIMEZONE = TIME_ZONE
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 300
CELERY_BEAT_SCHEDULER = 'django_celery_beat.schedulers:DatabaseScheduler'

# Queues are declared now and used later:
#   provisioning — bulk router writes (P5)
#   priority     — doorstep reconnections that a person is waiting on (P7)
CELERY_TASK_ROUTES = {
    'apps.network.tasks.provision_*': {'queue': 'provisioning'},
    'apps.network.tasks.reconcile_*': {'queue': 'provisioning'},
}


# Router credential encryption (P1). Generate with:
#   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
ROUTER_CRED_KEY = config('ROUTER_CRED_KEY', default='')


LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {name} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
    },
    'root': {'handlers': ['console'], 'level': 'INFO'},
    'loggers': {
        'apps': {'handlers': ['console'], 'level': 'INFO', 'propagate': False},
        'django.db.backends': {'level': 'WARNING'},
    },
}
