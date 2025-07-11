"""
Base settings to build other settings files upon.
"""
from datetime import timedelta

from django.core.serializers.json import DjangoJSONEncoder
from django.utils.translation import ugettext_lazy as _

import environ
import pytz
import sentry_sdk
from corsheaders.defaults import default_headers
from kombu.serialization import register
from kombu.utils.json import json
from daphne import server  # noqa
from sentry_sdk.integrations.celery import CeleryIntegration
from sentry_sdk.integrations.django import DjangoIntegration


def celery_dumps(obj):
    return json.dumps(obj, cls=DjangoJSONEncoder)


ROOT_DIR = environ.Path(__file__) - 3  # (project/project/settings/base.py - 3 = project/)

env = environ.Env()

READ_DOT_ENV_FILE = env.bool('DJANGO_READ_DOT_ENV_FILE', default=False)
if READ_DOT_ENV_FILE:
    # OS environment variables take precedence over variables from .env
    env.read_env(str(ROOT_DIR.path('.env')))

SENTRY_DSN = "https://a8fa886972934f20ae889b587f7ba497@sentry.holyaff.com/2"
SITE_ID = 1

WIKI_ACCOUNT_HANDLING = True
WIKI_ACCOUNT_SIGNUP_ALLOWED = False
WIKI_ANONYMOUS = False
WIKI_ANONYMOUS_WRITE = False

RAVEN_CONFIG = {
    'dsn': SENTRY_DSN,
    # If you are using git, you can also automatically configure the
    # release based on the git info.
    'release': env('CI_COMMIT_SHA', default='dev'),
}

sentry_sdk.init(
    release=f"crm-api@{env('CI_COMMIT_SHA', default='dev')}",
    environment=env('ENVIRONMENT', default='local'),
    dsn=SENTRY_DSN,
    integrations=[DjangoIntegration(), CeleryIntegration()],
    send_default_pii=True,
)

# GENERAL
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#debug
DEBUG = env.bool('DJANGO_DEBUG', False)
# Local time zone. Choices are
# http://en.wikipedia.org/wiki/List_of_tz_zones_by_name
# though not all of them may be available with every OS.
# In Windows, this must be set to your system time zone.
TIME_ZONE = 'UTC'
TZ = pytz.timezone(TIME_ZONE)

# https://docs.djangoproject.com/en/dev/ref/settings/#language-code
LANGUAGE_CODE = 'en-us'

LANGUAGES = (('en', _('English')), ('ru', _('Russian')))
#
# LOCALE_PATHS = (
#     os.path.join(BASE_DIR, 'locale'),
# )
# https://docs.djangoproject.com/en/dev/ref/settings/#use-i18n
USE_I18N = True
# https://docs.djangoproject.com/en/dev/ref/settings/#use-l10n
USE_L10N = True
# https://docs.djangoproject.com/en/dev/ref/settings/#use-tz
USE_TZ = True

# CSRF_COOKIE_HTTPONLY = False

# URLS
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#root-urlconf
ROOT_URLCONF = 'project.urls'
# https://docs.djangoproject.com/en/dev/ref/settings/#wsgi-application
WSGI_APPLICATION = 'project.wsgi.application'
ASGI_APPLICATION = 'websockets.routing.application'


CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {
            "hosts": [(env('REDIS_HOST', default='redis'), env('REDIS_PORT', default=6379))],
            "capacity": 1500,  # default 100
            "expiry": 10,  # default 60
        },
    }
}


GRAPPELLI_ADMIN_TITLE = 'HolyAff CRM Admin'
# APPS
# ------------------------------------------------------------------------------
DJANGO_APPS = [
    'grappelli',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.sites',
    'django.contrib.humanize',
]


THIRD_PARTY_APPS = [
    'django_celery_beat',
    'rest_framework',
    'corsheaders',
    'django_filters',
    'django_redis',
    'channels',
    'core',
    'websockets',
    'knox',
    'raven.contrib.django.raven_compat',
    'drf_yasg',
    'django_fsm',
    'fsm_admin',
    'django_json_widget',
    'wiki',
    'mptt',
    'sekizai',
    'sorl.thumbnail',
    'wiki.plugins.attachments.apps.AttachmentsConfig',
    'wiki.plugins.editsection.apps.EditSectionConfig',
    'wiki.plugins.globalhistory.apps.GlobalHistoryConfig',
    'wiki.plugins.help.apps.HelpConfig',
    'wiki.plugins.images.apps.ImagesConfig',
    'wiki.plugins.links.apps.LinksConfig',
    'wiki.plugins.macros.apps.MacrosConfig',
]

# https://docs.djangoproject.com/en/dev/ref/settings/#installed-apps
INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS

LOGIN_REDIRECT_URL = '/dashboard/'
# AUTHENTICATION
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#authentication-backends
AUTHENTICATION_BACKENDS = ('django.contrib.auth.backends.ModelBackend',)

AUTH_USER_MODEL = 'core.User'

REST_FRAMEWORK = {
    'DEFAULT_RENDERER_CLASSES': ('rest_framework.renderers.JSONRenderer',),
    'DEFAULT_PERMISSION_CLASSES': ('api.v1.permissions.AllowedRoles',),
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'knox.auth.TokenAuthentication',
        'rest_framework.authentication.SessionAuthentication',
    ),
    'DEFAULT_VERSIONING_CLASS': 'rest_framework.versioning.NamespaceVersioning',
    'DEFAULT_VERSION': 'v1',
    'DEFAULT_FILTER_BACKENDS': ('django_filters.rest_framework.DjangoFilterBackend',),
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.LimitOffsetPagination',
    'PAGE_SIZE': 50,
    'DEFAULT_PARSER_CLASSES': ('rest_framework.parsers.JSONParser', 'rest_framework.parsers.MultiPartParser'),
}

REST_KNOX = {
    'TOKEN_TTL': timedelta(hours=24 * 7),  # 1 week
    'AUTO_REFRESH': True,
}

DATA_UPLOAD_MAX_NUMBER_FIELDS = None

# Register your new serializer methods into kombu
register('celery_json', celery_dumps, json.loads, content_type='application/json', content_encoding='utf-8')

# Tell celery to use your new serializer:
CELERY_ACCEPT_CONTENT = ['celery_json']
CELERY_TASK_SERIALIZER = 'celery_json'
CELERY_RESULT_SERIALIZER = 'celery_json'

# PASSWORDS
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#password-hashers
PASSWORD_HASHERS = [
    # https://docs.djangoproject.com/en/dev/topics/auth/passwords/#using-argon2-with-django
    'django.contrib.auth.hashers.Argon2PasswordHasher',
    'django.contrib.auth.hashers.PBKDF2PasswordHasher',
    'django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher',
    'django.contrib.auth.hashers.BCryptSHA256PasswordHasher',
    'django.contrib.auth.hashers.BCryptPasswordHasher',
]

# https://docs.djangoproject.com/en/dev/ref/settings/#auth-password-validators
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# MIDDLEWARE
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#middleware
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    # 'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
]

SESSION_SAVE_EVERY_REQUEST = True
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_HEADERS = default_headers + ('content-disposition',)

# STATIC
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#static-root
STATIC_ROOT = str(ROOT_DIR('static'))

# https://docs.djangoproject.com/en/dev/ref/settings/#static-url
STATIC_URL = '/static/'
# https://docs.djangoproject.com/en/dev/ref/contrib/staticfiles/#std:setting-STATICFILES_DIRS
STATICFILES_DIRS = [str(ROOT_DIR.path('project/static'))]

# https://docs.djangoproject.com/en/dev/ref/contrib/staticfiles/#staticfiles-finders
STATICFILES_FINDERS = [
    'django.contrib.staticfiles.finders.FileSystemFinder',
    'django.contrib.staticfiles.finders.AppDirectoriesFinder',
    # 'compressor.finders.CompressorFinder',
]

# http://docs.celeryproject.org/en/latest/userguide/configuration.html#std:setting-timezone
timezone = TIME_ZONE
# MEDIA
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#media-root
MEDIA_ROOT = str(ROOT_DIR('media'))
# https://docs.djangoproject.com/en/dev/ref/settings/#media-url
MEDIA_URL = '/media/'

# TEMPLATES
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#templates
TEMPLATES = [
    {
        # https://docs.djangoproject.com/en/dev/ref/settings/#std:setting-TEMPLATES-BACKEND
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [str(ROOT_DIR.path('project/templates'))],
        # https://docs.djangoproject.com/en/dev/ref/settings/#template-dirs
        'OPTIONS': {
            # https://docs.djangoproject.com/en/dev/ref/settings/#template-debug
            'debug': DEBUG,
            # https://docs.djangoproject.com/en/dev/ref/settings/#template-loaders
            # https://docs.djangoproject.com/en/dev/ref/templates/api/#loader-types
            'loaders': ['django.template.loaders.filesystem.Loader', 'django.template.loaders.app_directories.Loader'],
            # https://docs.djangoproject.com/en/dev/ref/settings/#template-context-processors
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.template.context_processors.i18n',
                'django.template.context_processors.media',
                'django.template.context_processors.static',
                'django.template.context_processors.tz',
                'django.contrib.messages.context_processors.messages',
                'sekizai.context_processors.sekizai',
            ],
        },
    }
]

# EMAIL
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#email-backend
EMAIL_BACKEND = env('DJANGO_EMAIL_BACKEND', default='django.core.mail.backends.smtp.EmailBackend')

# ADMIN
# ------------------------------------------------------------------------------
# Django Admin URL.
ADMIN_URL = 'admin/'
# https://docs.djangoproject.com/en/dev/ref/settings/#admins
ADMINS = [("""Alternativshik""", 'alternativshik@gmail.com')]
# https://docs.djangoproject.com/en/dev/ref/settings/#managers
MANAGERS = ADMINS

LOGIN_URL = f'{ADMIN_URL}/login/'
