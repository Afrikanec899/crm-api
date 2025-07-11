import csv
import datetime
import os

from django.conf import settings
from django.core.management.base import BaseCommand

from unidecode import unidecode

from core.models.core import Country, LeadgenLead

COUNTRY_PHONE = {'FR': '+33', 'IT': '+39', 'DK': '+45', 'BE': '+32', 'ES': '+34', 'FI': '+358'}


class Command(BaseCommand):
    help = ''

    def add_arguments(self, parser):
        parser.add_argument('-i', '--in', action='store', dest='in', required=True, type=str, help='File to import')
        parser.add_argument('-o', '--out', action='store', dest='outfile', required=True, type=str, help='Output file')

    def handle(self, *args, **options):
        with open(options['in']) as f:
            lines = csv.DictReader(f, delimiter=';')
            with open(options['outfile'], 'w', newline='') as csvfile:
                writer = csv.writer(csvfile, delimiter=';', quoting=csv.QUOTE_ALL)
                writer.writerow(['name', 'email', 'phone', 'processed_phone', 'url'])
                for line in lines:
                    if line.get('email'):
                        lead = LeadgenLead.objects.filter(email=line['email']).first()
                        if lead:
                            cleared_name = unidecode(lead.full_name)
                            writer.writerow(
                                [cleared_name, lead.email, lead.phone, lead.clear_phone,]
                            )
        print('Done')
