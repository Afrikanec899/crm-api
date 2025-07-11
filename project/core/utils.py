import datetime
import json
import logging
import random
import time
from decimal import Decimal
from typing import Optional

from django.conf import settings
from django.core.serializers.json import DjangoJSONEncoder

import requests
import telebot
from bs4 import BeautifulSoup
from drf_yasg import openapi
from faker import Faker
from unidecode import unidecode

logger = logging.getLogger(__name__)

bot = telebot.TeleBot(settings.TELEGRAM_BOT_TOKEN)

FIELDS_PARAM = openapi.Parameter(
    'fields', openapi.IN_QUERY, description="Return only selected fields", type=openapi.TYPE_STRING
)

EXPAND_PARAM = openapi.Parameter(
    'expand', openapi.IN_QUERY, description="Expand selected fields", type=openapi.TYPE_STRING
)

OMIT_PARAM = openapi.Parameter('omit', openapi.IN_QUERY, description="Omit selected fields", type=openapi.TYPE_STRING)

DATE_FROM = openapi.Parameter(
    'date_from', openapi.IN_QUERY, description="Date from", type=openapi.TYPE_STRING, format=openapi.FORMAT_DATE
)

DATE_TO = openapi.Parameter(
    'date_to', openapi.IN_QUERY, description="Date to", type=openapi.TYPE_STRING, format=openapi.FORMAT_DATE
)

FILE = openapi.Parameter('file', openapi.IN_FORM, type=openapi.TYPE_FILE, format=openapi.FORMAT_BINARY)

PK = openapi.Parameter('pk', openapi.IN_PATH, type=openapi.TYPE_INTEGER, format=openapi.FORMAT_INT32)


def send_alert(chat_id, message, force_send=False):
    if not settings.DEBUG or force_send:
        bot.send_message(chat_id, message, parse_mode='HTML')
    else:
        print(message)


def func_attempts(func, *args, **kwargs):
    attempts = kwargs.pop('attempts', 5) or 5
    sleep = kwargs.pop('sleep', 1) or 1
    backoff_factor = kwargs.pop('backoff_factor', 1) or 1

    for i in range(attempts + 1):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            print(e)
            if i == attempts:
                raise
            else:
                sleep = sleep * (i + 1) * backoff_factor
                time.sleep(sleep)
                logger.warning(f'ERROR {i + 1}: {e}')
                continue


def generate_xcard(currency='USD'):
    faker = Faker(locale='pl_PL')
    Faker.seed()
    gender = random.choice(['male', 'female'])

    first_name = getattr(faker, f'first_name_{gender}')()
    last_name = getattr(faker, f'last_name_{gender}')()

    card_data = {
        'product_id': f'ccPurchaseCardMC{currency}',
        'currency': currency,
        'first_name': first_name,
        'last_name': last_name,
        'gender': 'M' if gender == 'male' else 'F',
        'date_of_birth': faker.date_of_birth(minimum_age=21),
        'address1': f'{faker.street_name()} {faker.building_number()}',
        'city': faker.city(),
        'state': faker.region(),
        'post_code': faker.postcode(),
        'country_code': 'PL',
        'mobile_country': '48',
        'mobile_number': faker.phone_number().replace('+48', '').replace(' ', ''),
        'email': faker.email(),
        'name_on_card': unidecode(f'{first_name} {last_name}').upper(),
    }
    return card_data


# class JSONEncoder(json.JSONEncoder):
#     ''' extend json-encoder class'''
#
#     def default(self, o):
#         if isinstance(o, Decimal):
#             o = o.quantize(Decimal('.01'))
#             return str(o)
#         if isinstance(o, datetime.datetime):
#             return str(o)
#         if isinstance(o, datetime.date):
#             return str(o)
#         return json.JSONEncoder.default(self, o)  # pragma: no cover


def next_weekday(date, weekday):
    days_ahead = weekday - date.weekday()
    if days_ahead <= 0:  # Target day already happened this week
        days_ahead += 7
    return date + datetime.timedelta(days_ahead)


def dateperiod(base, end):
    numdays = (end - base).days + 1
    result = [end - datetime.timedelta(days=x) for x in range(0, numdays)]
    return result


def get_tracker_auth(login: str, password: str) -> Optional[requests.Session]:
    login_url = 'https://ap.zeustrack.io/login'
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_1) AppleWebKit/605.1.15 '
        '(KHTML, like Gecko) Version/13.0.3 Safari/605.1.15'
    }
    session = requests.Session()

    auth_page = session.get(login_url, headers=headers)
    html = auth_page.text
    soup = BeautifulSoup(html, 'html.parser')

    csrf_token = soup.find("meta", attrs={'name': "csrf-token"}).get('content')
    csrf_param = soup.find("meta", attrs={'name': "csrf-param"}).get('content')

    login_data = {csrf_param: csrf_token, 'user[email]': login, 'user[password]': password}
    request = session.post(login_url, data=login_data, headers=headers, timeout=120)
    if request.status_code == 200:
        return session
    logger.error('Cant get tracker auth', exc_info=True, extra={'status': request.status_code})
    return None


ALPHABET = 'HucLERrqGFndbykPzACovIWj0K3Je9XS51YiOVDmTfMa82g7UwpBhQxN64tZ'
