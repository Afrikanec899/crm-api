from .base import *  # noqa
from .base import env

# GENERAL
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#debug
DEBUG = True
# https://docs.djangoproject.com/en/dev/ref/settings/#secret-key
SECRET_KEY = env('DJANGO_SECRET_KEY', default='QRjssRIZeHFcBLyuyRpxHZLg2QiAIC3ukx97c3F7WLFWvvNsxnALg8WvLfquU4cz')
# https://docs.djangoproject.com/en/dev/ref/settings/#allowed-hosts

INTERNAL_IPS = ['127.0.0.1']
ALLOWED_HOSTS = ['*']

ADMIN_URL = 'admin/'

SHORTIFY_URL = env('SHORTIFY_URL', default='http://0.0.0.0')
SHORTIFY_API_KEY = env('SHORTIFY_API_KEY', default='QRjssRIZeHFcBLyuyRpxHZLg2QiAIC3ukx97c3F7WLFWvvNsxnALg8WvLfquU4cz')

CORS_ORIGIN_ALLOW_ALL = True


SWAGGER_SETTINGS = {
    'LOGIN_URL': '/admin/login/',
    'LOGOUT_URL': '/admin/logout/',
    'REFETCH_SCHEMA_WITH_AUTH': True,
    'PERSIST_AUTH': True,
    'SECURITY_DEFINITIONS': {'Bearer': {'type': 'apiKey', 'name': 'Authorization', 'in': 'header'}},
}

# CACHES
# ------------------------------------------------------------------------------
CACHES = {
    'default': {
        'BACKEND': 'django_redis.cache.RedisCache',
        'LOCATION': env('REDIS_URL', default='redis://127.0.0.1:6379/0'),
        'OPTIONS': {
            'CLIENT_CLASS': 'django_redis.client.DefaultClient',
            # Mimicing memcache behavior.
            # http://niwinz.github.io/django-redis/latest/#_memcached_exceptions_behavior
            'IGNORE_EXCEPTIONS': True,
        },
    }
}

# TEMPLATES
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#templates
TEMPLATES[0]['OPTIONS']['debug'] = DEBUG  # noqa F405

# EMAIL
# ------------------------------------------------------------------------------
# # https://docs.djangoproject.com/en/dev/ref/settings/#default-from-email
DEFAULT_FROM_EMAIL = env('DJANGO_DEFAULT_FROM_EMAIL', default='Sweetecom Team <support@sweetecom.com>')
# # https://docs.djangoproject.com/en/dev/ref/settings/#server-email
SERVER_EMAIL = env('DJANGO_SERVER_EMAIL', default=DEFAULT_FROM_EMAIL)
# # https://docs.djangoproject.com/en/dev/ref/settings/#email-subject-prefix
EMAIL_SUBJECT_PREFIX = env('DJANGO_EMAIL_SUBJECT_PREFIX', default='[Sweetecom Team]')

TELEGRAM_BOT_TOKEN = '221948935:AAF_82LMKlYzM-aktZmjSNFUIoHl1ozxzJE'

REST_FRAMEWORK["DEFAULT_AUTHENTICATION_CLASSES"] = (  # noqa F405
    "rest_framework.authentication.SessionAuthentication",
    'knox.auth.TokenAuthentication',
)

DATABASES = {"default": env.db("DATABASE_URL", default="postgres:///crm_v2")}
DATABASES["default"]["ATOMIC_REQUESTS"] = False

# EMAIL
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#email-backend
EMAIL_BACKEND = env('DJANGO_EMAIL_BACKEND', default='django.core.mail.backends.console.EmailBackend')
# https://docs.djangoproject.com/en/dev/ref/settings/#email-host
EMAIL_HOST = 'localhost'
# https://docs.djangoproject.com/en/dev/ref/settings/#email-port
EMAIL_PORT = 1025
MNLTH_SITE_PASS = env('MNLTH_SITE_PASS', default='')
MNLTH_LOGIN = env('MNLTH_LOGIN', default='')
MNLTH_PASSWD = env('MNLTH_PASSWD', default='')
# django-debug-toolbar
# ------------------------------------------------------------------------------
# https://django-debug-toolbar.readthedocs.io/en/latest/installation.html#prerequisites
# INSTALLED_APPS += ['silk']  # noqa F405
# INSTALLED_APPS += ['debug_toolbar']  # noqa F405
# https://django-debug-toolbar.readthedocs.io/en/latest/installation.html#middleware
# MIDDLEWARE += ['silk.middleware.SilkyMiddleware']  # noqa F405
# MIDDLEWARE += ['debug_toolbar.middleware.DebugToolbarMiddleware']  # noqa F405

# https://django-debug-toolbar.readthedocs.io/en/latest/configuration.html#debug-toolbar-config
# DEBUG_TOOLBAR_CONFIG = {
#     'DISABLE_PANELS': ['debug_toolbar.panels.redirects.RedirectsPanel'],
#     'SHOW_TEMPLATE_CONTEXT': True,
# }

# http://docs.celeryproject.org/en/latest/userguide/configuration.html#std:setting-broker_url

CELERY_BROKER_URL = env('REDIS_URL', default='redis://127.0.0.1:6379/0')
# https://django-debug-toolbar.readthedocs.io/en/latest/installation.html#internal-ips
if env('USE_DOCKER', default='no') == 'yes':
    import socket

    hostname, _, ips = socket.gethostbyname_ex(socket.gethostname())
    INTERNAL_IPS += [ip[:-1] + '1' for ip in ips]


LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {'format': '%(levelname)s %(asctime)s %(module)s %(process)d %(thread)d %(message)s'},
        'simple': {'format': '%(asctime)s %(levelname)s %(message)s'},
    },
    'filters': {'require_debug_true': {'()': 'django.utils.log.RequireDebugTrue'}},
    'handlers': {
        'console': {
            'level': 'INFO',
            'filters': ['require_debug_true'],
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
        'mail_admins': {'level': 'ERROR', 'class': 'django.utils.log.AdminEmailHandler', 'include_html': True},
        'celery': {'level': 'DEBUG', 'class': 'logging.StreamHandler', 'formatter': 'verbose'},
        'sentry': {
            'level': 'ERROR',  # To capture more than ERROR, change to WARNING, INFO, etc.
            'class': 'raven.contrib.django.raven_compat.handlers.SentryHandler',
            # 'tags': {'custom-tag': 'x'},
        },
    },
    'loggers': {
        '': {'handlers': ['console', 'sentry'], 'level': 'ERROR', 'propagate': True},
        # 'celery': {'handlers': ['console'], 'level': 'INFO', 'propagate': True},
        # 'celery.task': {'handlers': ['console'], 'level': 'ERROR', 'propagate': False},
        # 'django': {'handlers': ['console'], 'level': 'INFO', 'propagate': True},
        # 'django.request': {'handlers': ['console', 'mail_admins'], 'level': 'ERROR', 'propagate': False},
    },
}
