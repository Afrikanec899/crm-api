import csv
import datetime
import os

from django.conf import settings
from django.core.management.base import BaseCommand

from core.models.core import LeadgenLead


class Command(BaseCommand):
    help = ''

    def add_arguments(self, parser):
        parser.add_argument(
            '-i', '--in', action='store', dest='infile', required=True, type=str, help='File to import'
        )
        parser.add_argument(
            '-o', '--out', action='store', dest='outfile', required=True, type=str, help='File to export'
        )

    def handle(self, *args, **options):
        with open(options['outfile'], 'w') as outfile:
            writer = csv.writer(outfile, delimiter=';', quoting=csv.QUOTE_ALL)
            writer.writerow(['first_name', 'last_name', 'phone', 'email', 'zip', 'city', 'country', 'address'])
            with open(options['infile'], 'r') as infile:
                datareader = csv.DictReader(infile, delimiter=';')
                for row in datareader:
                    print(row)
                    item = LeadgenLead.objects.filter(email=row['EMAIL']).first()
                    if item:
                        LeadgenLead.objects.filter(email=row['EMAIL']).update(ipaddress=row['IP_ADDRESS'])
                        writer.writerow(
                            [
                                item.first_name,
                                item.last_name,
                                item.phone,
                                item.email,
                                item.zip,
                                item.city,
                                item.country,
                                item.address,
                            ]
                        )
                    else:
                        writer.writerow(
                            [None, None, None, row['EMAIL'], None, None, None, None,]
                        )
