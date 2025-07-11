import csv
import datetime
import os

from django.conf import settings
from django.core.management.base import BaseCommand

from core.models.core import Country, LeadgenLead

COUNTRY_PHONE = {'FR': '+33', 'IT': '+39', 'DK': '+45', 'BE': '+32', 'ES': '+34', 'FI': '+358'}


class Command(BaseCommand):
    help = ''

    def add_arguments(self, parser):
        parser.add_argument('-d', '--dir', action='store', dest='dir', required=True, type=str, help='Dir to import')

    def handle(self, *args, **options):
        country, _ = Country.objects.get_or_create(code='DK', defaults={'name': 'Dansk'})
        offer = 'nas1'
        for file in os.listdir(options['dir']):
            print(file)
            date = file.split('.')[0]
            date = datetime.datetime.strptime(date, '%Y_%m_%d').astimezone(settings.TZ)
            with open(os.path.join(options['dir'], file)) as f:
                lines = csv.DictReader(f, delimiter=',')
                try:
                    batch = []
                    for x, line in enumerate(lines):
                        if x % 100 == 0:
                            print(x)
                        phone = line['Phone']
                        if phone:
                            phone = phone.replace(' ', '')
                            phone = phone.replace('-', '')
                            prefix = COUNTRY_PHONE[country.code]
                            if not phone.startswith(prefix):
                                if phone.startswith('0033') or phone.startswith('0330'):
                                    phone = phone[4:]
                                    phone = f'{prefix}{phone}'
                                elif phone.startswith('+0'):
                                    phone = phone[2:]
                                    phone = f'{prefix}{phone}'
                                elif phone.startswith('0'):
                                    phone = phone[1:]
                                    phone = f'{prefix}{phone}'
                                elif phone.startswith('33'):
                                    phone = f'+{phone}'
                                elif phone.startswith('+'):
                                    phone = phone
                                else:
                                    phone = f'+33{phone}'

                            data = {
                                'phone': phone,
                                'email': line['E-mail'],
                                'first_name': line["First name"],
                                'last_name': line["Last name"],
                                'city': line['City'],
                                'zip': line['Zip Code'],
                                'address': line['Address'],
                                'name': f'{line["First name"]} {line["Last name"]}',
                            }
                            # print(data)
                            lead = LeadgenLead(
                                created_at=date,
                                raw_data=line,
                                country=country,
                                country_code=country.code,
                                offer=offer,
                                **data,
                            )
                            batch.append(lead)
                            if len(batch) >= 500:
                                LeadgenLead.objects.bulk_create(batch)
                                batch = []

                    if batch:
                        LeadgenLead.objects.bulk_create(batch)

                except Exception as e:
                    print(x)
                    print(e)
        print('Imported ')
