import logging

from django.conf import settings
from django.core.mail import EmailMessage

# from django.db import transaction
from django.db import transaction
from django.utils import timezone

import telebot
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from redis import Redis

from core.models.core import Notification
from project.celery_app import app

redis = Redis(host='redis', db=0, decode_responses=True)
logger = logging.getLogger('celery.task')

bot = telebot.TeleBot(settings.TELEGRAM_BOT_TOKEN)


@app.task(bind=True, autoretry_for=(Exception,), retry_kwargs={'max_retries': 5, 'countdown': 2})
def send_welcome_message(self, chat_id):
    bot.send_message(chat_id, 'Welcome to HolyAff CRM!', parse_mode='HTML', timeout=3)


@app.task(bind=True)  # , autoretry_for=(Exception,), retry_kwargs={'max_retries': 5, 'countdown': 2})
def notify_telegram(self, notification_id: int) -> None:
    with transaction.atomic():
        # notification = Notification.objects.get(id=notification_id)
        notification = Notification.objects.select_for_update().get(id=notification_id)
        bot.send_message(
            notification.recipient.telegram_id,
            notification.data['message'],
            parse_mode='HTML',
            timeout=3,
            reply_markup=notification.data.get('keyboard', None),
        )
        notification.sended_telegram_at = timezone.now()
        notification.save(update_fields=['sended_telegram_at'])


@app.task(bind=True, autoretry_for=(Exception,), retry_kwargs={'max_retries': 5, 'countdown': 2})
def notify_email(self, notification_id: int) -> None:
    with transaction.atomic():
        # notification = Notification.objects.get(id=notification_id)
        notification = Notification.objects.select_for_update().get(id=notification_id)
        if notification.recipient.email:
            msg = EmailMessage(
                subject=f'HolyAff CRM {notification.get_level_display()} Notification',
                from_email="HolyAff CRM <support@sweetecom.com>",
                to=[notification.recipient.email],
                body=notification.data['message'],
            )
            msg.send()
            notification.sended_email_at = timezone.now()
            notification.save(update_fields=['sended_email_at'])


@app.task(bind=True, autoretry_for=(Exception,), retry_kwargs={'max_retries': 5, 'countdown': 2})
def notify_websocket(self, notification_id: int) -> None:
    with transaction.atomic():
        notification = Notification.objects.select_for_update().get(id=notification_id)
        layer = get_channel_layer()
        layer.group_send(
            f'notifications_{notification.recipient_id}',
            {
                "type": "notification",
                "level": notification.level,
                'category': notification.category,
                'message': notification.data['message'],
            },
        )
        notification.sended_at = timezone.now()
        notification.save(update_fields=['sended_at'])
