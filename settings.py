"""
Django settings for Formative project.
"""

import os, environ
from pkg_resources import iter_entry_points
from pathlib import Path

env = environ.Env()

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent

environ.Env.read_env(os.path.join(BASE_DIR, '.env'), overwrite=True)
ENV = env('DJANGO_ENV')

SECRET_KEY = env('SECRET_KEY')

DEBUG = env.bool('DEBUG', default=False)

WSGI_APPLICATION = "config.wsgi.application"

ALLOWED_HOSTS = env('ALLOWED_HOSTS', default='').split(',')
csrf_hosts = [ host[0] == '.' and '*' + host or host for host in ALLOWED_HOSTS ]

DEFAULT_SERVER_HOSTNAME = env('SERVER_HOSTNAME')
SERVER_HOSTNAME = env('DJANGO_SERVER_HOSTNAME', default='')
if not SERVER_HOSTNAME: SERVER_HOSTNAME = DEFAULT_SERVER_HOSTNAME

port = env('DJANGO_SERVER_PORT', default=None)
DJANGO_SERVER = SERVER_HOSTNAME + (port and ':' + port or '')

CSRF_TRUSTED_ORIGINS = [ f'https://{DJANGO_SERVER}' ]
if DEBUG:
    CSRF_TRUSTED_ORIGINS = [ f'http://{host}:8000' for host in csrf_hosts ]

CSRF_COOKIE_NAME = 'XSRF-TOKEN'

# Application definition

INSTALLED_APPS = [
    'jazzmin',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.forms',
    'django_better_admin_arrayfield',
    'django_admin_inline_paginator',
    'polymorphic',
    'webpack_loader',
    'widget_tweaks',
    'formative',
]

PLUGINS = []
for entry_point in iter_entry_points(group='formative.plugin', name=None):
    PLUGINS.append(entry_point.module_name)
    INSTALLED_APPS.append(entry_point.module_name)


MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'formative.middleware.DynamicModelMiddleware',
]

ROOT_URLCONF = 'urls'

FORM_RENDERER = 'django.forms.renderers.TemplatesSetting'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [os.path.join(BASE_DIR, 'templates')],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]


host = env('POSTGRES_HOST', default='')
if env('DOCKER_ENV', default=''):
    host = env('POSTGRES_DOCKER_HOST')

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql_psycopg2',
        'NAME': env('POSTGRES_DB'),
        'USER': env('POSTGRES_USER'),
        'PASSWORD': env('POSTGRES_PASSWORD'),
        'HOST': host,
        'PORT': '5432',
    }
}

CACHES = {
    'default': env.cache_url('REDIS_URL', default='redis://redis/',
         backend='django.core.cache.backends.redis.RedisCache'
    )
}


EMAIL_HOST = env('POSTFIX_HOST', default='localhost')
TECH_EMAIL = env('DJANGO_SU_EMAIL')
CONTACT_EMAIL = env('CONTACT_EMAIL', default=TECH_EMAIL)
SERVER_EMAIL = env('SERVER_EMAIL', default=CONTACT_EMAIL)
DEFAULT_FROM_EMAIL = CONTACT_EMAIL
ADMINS = [(env('ADMIN_NAME', default=''),
           env('ADMIN_EMAIL', default=TECH_EMAIL))]


prefix = 'django.contrib.auth.password_validation'
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': prefix + '.UserAttributeSimilarityValidator',
    },
    {
        'NAME': prefix + '.MinimumLengthValidator',
    },
    {
        'NAME': prefix + '.CommonPasswordValidator',
    },
    {
        'NAME': prefix + '.NumericPasswordValidator',
    },
]


LANGUAGE_CODE = 'en-us'

USE_I18N = True

TIME_ZONE = 'UTC'
USE_TZ = True


LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'filters': {
        'require_debug_false': {
            '()': 'django.utils.log.RequireDebugFalse',
        },
        'require_debug_true': {
            '()': 'django.utils.log.RequireDebugTrue',
        },
    },
    'handlers': {
        'console': {
            'level': 'INFO',
            'class': 'logging.StreamHandler',
        },
        'mail_admins': {
            'level': 'ERROR',
            'filters': ['require_debug_false'],
            'class': 'django.utils.log.AdminEmailHandler',
        },
        'mail_debug_admins': {
            'level': 'CRITICAL',
            'filters': ['require_debug_true'],
            'class': 'django.utils.log.AdminEmailHandler',
        }
    },
    'loggers': {
        'django': {
            'handlers': ['console', 'mail_admins', 'mail_debug_admins'],
            'level': 'INFO',
        }
    }
}


STATIC_URL = '/static/'

STATIC_ROOT = os.path.join(os.path.dirname(BASE_DIR), 'static')

STATICFILES_STORAGE = 'whitenoise.storage.CompressedStaticFilesStorage'

MEDIA_ROOT = os.path.join(os.path.dirname(BASE_DIR), 'media')
MEDIA_URL = 'media/'

STATICFILES_DIRS = (
    ("bundles", os.path.join(BASE_DIR, 'assets/bundles')),
#    ("img", os.path.join(BASE_DIR, 'assets/img')),
    os.path.join(BASE_DIR, 'assets/static')
)


WEBPACK_LOADER = {
    'DEFAULT': {
        'CACHE': not DEBUG,
        'BUNDLE_DIR_NAME': 'bundles/',
        'STATS_FILE': os.path.join(os.path.join(BASE_DIR, 'assets/bundles/',
                                                f'webpack-bundle.{ENV}.json')),
        'POLL_INTERVAL': 0.5,
        'TIMEOUT': None,
        'IGNORE': [r".+\.hot-update.js", r".+\.map"]
    }
}


DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'


JAZZMIN_SETTINGS = {
    'related_modal_active': True,
    'hide_models': ['formative.collectionblock', 'formative.customblock',
                    'formative.formblock'],
}

JAZZMIN_UI_TWEAKS = {
    'sidebar_nav_legacy_style': True,
    'sidebar_disable_expand': True,
}


X_FRAME_OPTIONS = 'SAMEORIGIN'
SILENCED_SYSTEM_CHECKS = ['security.W019']
