import random
import time

from django.conf import settings
from django.core.management.base import BaseCommand

import telebot
from facebook_business import FacebookAdsApi
from facebook_business.adobjects.business import Business
from facebook_business.adobjects.user import User as FBUser
from faker import Faker


class Command(BaseCommand):
    help = ''

    def handle(self, *args, **options):
        bot = telebot.TeleBot(settings.TELEGRAM_BOT_TOKEN)
        # Set webhook
        bot.remove_webhook()
        # bot.set_webhook(url='https://20fbe8c6dae0.ngrok.io/api/v1/webhook/', allowed_updates=['message'])
        bot.set_webhook(url='https://api.holyaff.com/api/v1/webhook/bpQ6K3zGnuh66TPU/', allowed_updates=['message'])
