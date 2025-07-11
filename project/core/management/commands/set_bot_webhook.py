from django.conf import settings
from django.core.management.base import BaseCommand

import telebot


class Command(BaseCommand):
    help = ''

    def handle(self, *args, **options):
        bot = telebot.TeleBot(settings.TELEGRAM_BOT_TOKEN)
        bot.set_webhook(
            'https://api.holyaff.com/api/v1/webhook/bpQ6K3zGnuh66TPU/', allowed_updates=['message', 'callback_query']
        )
        print(bot.get_webhook_info())
