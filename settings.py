"""
Django settings for Formative project.
"""

import os, environ
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

CSRF_TRUSTED_ORIGINS = [ 'http://localhost' ]
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
    'polymorphic',
    'webpack_loader',
    'widget_tweaks',
    'formative',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'urls'

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


EMAIL_HOST = env('POSTFIX_HOST', default='localhost')
CONTACT_EMAIL = env('CONTACT_EMAIL')
SERVER_EMAIL = env('SERVER_EMAIL', default=CONTACT_EMAIL)
ADMINS = [(env('ADMIN_NAME', default=''),
           env('ADMIN_EMAIL', default=CONTACT_EMAIL))]

SERVER_HOSTNAME = env('DJANGO_SERVER_HOSTNAME', default=env('SERVER_HOSTNAME'))
port = env('DJANGO_SERVER_PORT', default=None)
DJANGO_SERVER = SERVER_HOSTNAME + (port and ':' + port or '')


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

TIME_ZONE = 'UTC'

USE_I18N = True

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

MEDIA_ROOT = os.path.join(os.path.dirname(BASE_DIR), 'media')

STATICFILES_DIRS = (
    ("bundles", os.path.join(BASE_DIR, 'assets/bundles')),
#    ("img", os.path.join(BASE_DIR, 'assets/img')),
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
    'hide_models': ['formative.collectionblock', 'formative.customblock'],
#    'custom_js': 'admin.js',
#    'custom_css': '',
}

JAZZMIN_UI_TWEAKS = {
    'sidebar_nav_legacy_style': True,
    'sidebar_disable_expand': True,
}


X_FRAME_OPTIONS = 'SAMEORIGIN'
SILENCED_SYSTEM_CHECKS = ['security.W019']
