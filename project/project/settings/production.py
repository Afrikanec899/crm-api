from .base import *  # noqa
from .base import env

# GENERAL
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#secret-key
SECRET_KEY = env('DJANGO_SECRET_KEY')
# https://docs.djangoproject.com/en/dev/ref/settings/#allowed-hosts
ALLOWED_HOSTS = ['*']  # env.list('DJANGO_ALLOWED_HOSTS', default=['example.com'])

API_DOMAIN = 'api.holyaff.com'
GOOGLE_API_KEY = env.str('GOOGLE_API_KEY')

TELEGRAM_BOT_TOKEN = env('TELEGRAM_BOT_TOKEN')

MNLTH_SITE_PASS = env('MNLTH_SITE_PASS')
MNLTH_LOGIN = env('MNLTH_LOGIN')
MNLTH_PASSWD = env('MNLTH_PASSWD')

# DATABASES
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#databases
DATABASES = {'default': env.db('DATABASE_URL')}  # noqa F405
DATABASES['default']['CONN_MAX_AGE'] = env.int('CONN_MAX_AGE', default=60)  # noqa F405
DATABASES['default']['DISABLE_SERVER_SIDE_CURSORS'] = True

# http://docs.celeryproject.org/en/latest/userguide/configuration.html#std:setting-broker_url
# CELERY_BROKER_USER = env('RABBITMQ_DEFAULT_USER')
# CELERY_BROKER_PASSWORD = env('RABBITMQ_DEFAULT_PASS')
# CELERY_BROKER_VHOST = env('RABBITMQ_DEFAULT_VHOST')
#
# CELERY_BROKER_URL = f'amqp://{CELERY_BROKER_USER}:{CELERY_BROKER_PASSWORD}@rabbitmq:5672/{CELERY_BROKER_VHOST}'

CELERY_BROKER_URL = env('REDIS_URL')

# CACHES
# ------------------------------------------------------------------------------
CACHES = {
    'default': {
        'BACKEND': 'django_redis.cache.RedisCache',
        'LOCATION': env('REDIS_URL'),
        'OPTIONS': {
            'CLIENT_CLASS': 'django_redis.client.DefaultClient',
            # Mimicing memcache behavior.
            # http://niwinz.github.io/django-redis/latest/#_memcached_exceptions_behavior
            'IGNORE_EXCEPTIONS': True,
        },
    }
}
SESSION_ENGINE = 'django.contrib.sessions.backends.cache'

# SECURITY
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#secure-proxy-ssl-header
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
# https://docs.djangoproject.com/en/dev/ref/settings/#secure-ssl-redirect
# SECURE_SSL_REDIRECT = env.bool('DJANGO_SECURE_SSL_REDIRECT', default=True)
# https://docs.djangoproject.com/en/dev/ref/settings/#session-cookie-secure
SESSION_COOKIE_SECURE = True
# # https://docs.djangoproject.com/en/dev/ref/settings/#session-cookie-httponly
# SESSION_COOKIE_HTTPONLY = True
# # https://docs.djangoproject.com/en/dev/ref/settings/#csrf-cookie-secure
# CSRF_COOKIE_SECURE = True
# # https://docs.djangoproject.com/en/dev/ref/settings/#csrf-cookie-httponly
# CSRF_COOKIE_HTTPONLY = True
#
# CSRF_USE_SESSIONS = True
#
# # https://docs.djangoproject.com/en/dev/topics/security/#ssl-https
# # https://docs.djangoproject.com/en/dev/ref/settings/#secure-hsts-seconds
#
# # TODO: set this to 60 seconds first and then to 518400 once you prove the former works
# SECURE_HSTS_SECONDS = 60
# # https://docs.djangoproject.com/en/dev/ref/settings/#secure-hsts-include-subdomains
# SECURE_HSTS_INCLUDE_SUBDOMAINS = env.bool('DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS', default=True)
# # https://docs.djangoproject.com/en/dev/ref/settings/#secure-hsts-preload
# SECURE_HSTS_PRELOAD = env.bool('DJANGO_SECURE_HSTS_PRELOAD', default=True)
# # https://docs.djangoproject.com/en/dev/ref/middleware/#x-content-type-options-nosniff
# SECURE_CONTENT_TYPE_NOSNIFF = env.bool('DJANGO_SECURE_CONTENT_TYPE_NOSNIFF', default=True)
# # https://docs.djangoproject.com/en/dev/ref/settings/#secure-browser-xss-filter
# SECURE_BROWSER_XSS_FILTER = True

# TEMPLATES
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#templates
TEMPLATES[0]['OPTIONS']['loaders'] = [  # noqa F405
    (
        'django.template.loaders.cached.Loader',
        ['django.template.loaders.filesystem.Loader', 'django.template.loaders.app_directories.Loader'],
    )
]

SHORTIFY_URL = env('SHORTIFY_URL')
SHORTIFY_API_KEY = env('SHORTIFY_API_KEY')

# EMAIL
# ------------------------------------------------------------------------------
# # https://docs.djangoproject.com/en/dev/ref/settings/#default-from-email
DEFAULT_FROM_EMAIL = env('DJANGO_DEFAULT_FROM_EMAIL', default='Sweetecom Team <support@sweetecom.com>')
# # https://docs.djangoproject.com/en/dev/ref/settings/#server-email
SERVER_EMAIL = env('DJANGO_SERVER_EMAIL', default=DEFAULT_FROM_EMAIL)
# # https://docs.djangoproject.com/en/dev/ref/settings/#email-subject-prefix
EMAIL_SUBJECT_PREFIX = env('DJANGO_EMAIL_SUBJECT_PREFIX', default='[Sweetecom Team]')

# Anymail (Mailgun)
# ------------------------------------------------------------------------------
# https://anymail.readthedocs.io/en/stable/installation/#installing-anymail
INSTALLED_APPS += ['anymail']  # noqa F405
EMAIL_BACKEND = 'anymail.backends.mailgun.EmailBackend'
# https://anymail.readthedocs.io/en/stable/installation/#anymail-settings-reference
ANYMAIL = {'MAILGUN_API_KEY': env('MAILGUN_API_KEY'), 'MAILGUN_SENDER_DOMAIN': env('MAILGUN_DOMAIN')}

# ADMIN
# ------------------------------------------------------------------------------
# Django Admin URL regex.
ADMIN_URL = env('DJANGO_ADMIN_URL')

CORS_ORIGIN_ALLOW_ALL = True
# CORS_ORIGIN_WHITELIST = ('https://crm.sweetecom.com',)
# Gunicorn
# ------------------------------------------------------------------------------
INSTALLED_APPS += ['gunicorn']  # noqa F405

# Silk profiling
# INSTALLED_APPS += ['silk']  # noqa F405
# MIDDLEWARE += ['silk.middleware.SilkyMiddleware']  # noqa F405

# SILKY_AUTHENTICATION = True  # User must login
# SILKY_AUTHORISATION = True  # User must have permissions
# SILKY_META = True

# LOGGING
# ------------------------------------------------------------------------------
# See: https://docs.djangoproject.com/en/dev/ref/settings/#logging
# A sample logging configuration. The only tangible logging
# performed by this configuration is to send an email to
# the site admins on every HTTP 500 error when DEBUG=False.
# See https://docs.djangoproject.com/en/dev/topics/logging for
# more details on how to customize your logging configuration.


LOGGING = {
    'version': 1,
    'disable_existing_loggers': True,
    'root': {'level': 'WARNING', 'handlers': ['sentry']},
    'formatters': {
        'verbose': {'format': '%(levelname)s %(asctime)s %(module)s %(process)d %(thread)d %(message)s'},
        'simple': {'format': '%(asctime)s %(levelname)s %(message)s'},
    },
    'filters': {'require_debug_true': {'()': 'django.utils.log.RequireDebugTrue'}},
    'handlers': {
        'console': {
            'level': 'INFO',
            # 'filters': ['require_debug_true'],
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
        'mail_admins': {'level': 'ERROR', 'class': 'django.utils.log.AdminEmailHandler', 'include_html': True},
        'celery': {'level': 'DEBUG', 'class': 'logging.StreamHandler', 'formatter': 'verbose'},
        'sentry': {
            'level': 'ERROR',  # To capture more than ERROR, change to WARNING, INFO, etc.
            'class': 'raven.contrib.django.raven_compat.handlers.SentryHandler',
            'tags': {'custom-tag': 'crm_api'},
        },
    },
    'loggers': {
        '': {'handlers': ['sentry', 'console'], 'level': 'ERROR'},
        'raven': {'level': 'DEBUG', 'handlers': ['console'], 'propagate': False},
        'sentry.errors': {'level': 'DEBUG', 'handlers': ['console'], 'propagate': False},
        'celery': {'handlers': ['console'], 'level': 'INFO', 'propagate': True},
        'celery.task': {'handlers': ['console'], 'level': 'ERROR', 'propagate': False},
        'django': {'handlers': ['console'], 'level': 'INFO', 'propagate': True},
        'django.request': {'handlers': ['console'], 'level': 'ERROR', 'propagate': False},
    },
}
