import base64
import io
import random
import uuid
from pprint import pprint

from django.conf import settings
from django.core.management.base import BaseCommand

from PIL import Image
from unidecode import unidecode

from XCardAPI.api import XCardAPI


class Command(BaseCommand):
    help = ''

    def handle(self, *args, **options):
        from faker import Faker

        faker = Faker(locale='pl_PL')
        gender = random.choice(['male', 'female'])

        first_name = getattr(faker, f'first_name_{gender}')()
        last_name = getattr(faker, f'last_name_{gender}')()

        params = {
            'product_id': 'ccPurchaseCardMCEUR',
            'currency': 'EUR',
            'external_id': str(uuid.uuid4()),
            'first_name': first_name,
            'last_name': last_name,
            'gender': 'M' if gender == 'male' else 'F',
            'date_of_birth': faker.date_of_birth(minimum_age=21),
            'address1': f'{faker.street_name()} {faker.building_number()}',
            'city': faker.city(),
            'post_code': faker.postcode(),
            'country_code': 'PL',
            'mobile_country': '48',
            'mobile_number': faker.phone_number().replace('+48', '').replace(' ', ''),
            'email': faker.email(),
            'name_on_card': unidecode(f'{first_name} {last_name}').upper(),
            'state': faker.region(),
        }

        # pprint(params)

        api = XCardAPI(
            login='',
            password='',
            partner_id='',
            ca_certs='.certs/client.cert',
            cert_file='.certs/server.cert',
            key_file='.certs/client.key',
            key_password='',
            is_dev=settings.DEBUG,
        )

        # response = api.create_virtual_card(
        #     **params
        # )
        # print(response.data())

        # response = api.echo('CALL ME MAY BE!')
        # print(response.call_execution_time())
        # response = api.get_account_balance()
        # print(response.data())
        # response = api.get_virtual_card_details(265830310)
        # pprint(response.data())
        response = api.get_virtual_card_pan(265830310)
        # pprint(response.data())

        import pytesseract

        image_string = base64.b64decode(response.data()['panimage'])
        buf = io.BytesIO(image_string)
        img = Image.open(buf)
        # Upscale
        img = img.resize((img.size[0] * 4, img.size[1] * 4), Image.BICUBIC)
        # and grayscale
        img = img.convert('LA')
        # OCR
        text = pytesseract.image_to_string(img)
        print(text.lower().split('pan:')[1].split('\n')[0].strip().replace(' ', ''))
