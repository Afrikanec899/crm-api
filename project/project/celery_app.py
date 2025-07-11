import os

from django.conf import settings

from celery import Celery

if not settings.configured:
    #     set the default Django settings module for the 'celery' program.
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'project.settings.local')

app = Celery('project')
# Using a string here means the worker don't have to serialize
# the configuration object to child processes.
# - namespace='CELERY' means all celery-related configuration keys
#   should have a `CELERY_` prefix.
app.config_from_object('django.conf:settings', namespace='CELERY')


if not settings.DEBUG:
    app.conf.task_routes = {
        "*.notify_telegram": {"queue": 'tg_notifications'},
        "*.send_welcome_message": {"queue": 'tg_notifications'},
        "*.notify*": {"queue": 'notifications'},
        "*.tracker.*": {"queue": 'tracker'},
        "*.facebook.load_bills": {"queue": 'facebook_bills'},
        "*.facebook.load_account_transactions_task": {"queue": 'facebook_bills'},
        "*.facebook.load_account_payment_methods_task": {"queue": 'facebook_bills'},
        "*.facebook.load_payment_methods": {"queue": 'facebook_bills'},
        "*.facebook.check_ad_comments": {"queue": 'facebook_comments'},
        "*.facebook.check_account_page_comments": {"queue": 'facebook_comments'},
        "*.facebook.get_fb_businesses": {"queue": 'facebook_businesses'},
        "*.facebook.get_fb_adaccounts_task": {"queue": 'facebook_adaccounts'},
        "*.facebook.get_account_adaccounts_task": {"queue": 'facebook_adaccounts'},
        "*.facebook.get_fb_ads_task": {"queue": 'facebook_ads'},
        "*.facebook.get_accounts_ads_task": {"queue": 'facebook_ads'},
        "*.facebook.load_account_businesses_task": {"queue": 'facebook_businesses'},
        "*.facebook.get_fb_day_stats_task": {"queue": 'facebook_stats'},
        "*.facebook.get_fb_account_day_stats_task": {"queue": 'facebook_stats'},
        "*.facebook.*": {"queue": 'facebook'},
        "*.share_mla_profile": {"queue": 'mla'},
        "*.create_mla_profile": {"queue": 'mla'},
        "*.create_empty_mla_profiles": {"queue": 'mla'},
        "create_ads": {"queue": 'automation'},
        "*.create_links": {"queue": 'shortify'},
        "*.process_click_stats": {"queue": 'shortify'},
        "*.fill_shortify_cache_task": {"queue": 'shortify'},
        "*.contacts.*": {"queue": 'contacts'},
    }

app.conf.task_acks_late = True
app.conf.worker_hijack_root_logger = False
app.conf.worker_prefetch_multiplier = 1
app.conf.task_send_sent_event = False
app.conf.task_track_started = False
app.conf.worker_max_tasks_per_child = 10
app.conf.worker_pool_restarts = True
app.conf.broker_heartbeat = 0
app.conf.task_ignore_result = True
app.conf.worker_send_task_events = False
app.conf.result_backend = None

# Load task modules from all registered Django app configs.
app.autodiscover_tasks()
