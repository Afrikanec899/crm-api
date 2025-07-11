import csv
from itertools import islice
from pprint import pprint

from django.core.management.base import BaseCommand

import dns.resolver
import requests

from core.utils import func_attempts


class Command(BaseCommand):
    help = ''

    def add_arguments(self, parser):
        parser.add_argument(
            '-i', '--input', action='store', dest='infile', required=True, type=str, help='File to check'
        )
        parser.add_argument(
            '-o', '--out', action='store', dest='outfile', required=True, type=str, help='File to output'
        )

    def handle(self, *args, **options):
        with open(options['infile'], 'r') as f:
            with open(options['outfile'], 'w') as csv_file:
                writer = csv.writer(csv_file, delimiter=',')
                writer.writerow(['email', 'domain', 'has mail', 'has site', 'has A record'])

            while True:
                lines = list(islice(f, 300))
                if not lines:
                    break

                for line in lines:
                    has_MX_record = False
                    has_A_record = False
                    has_site = False
                    domain = line.split('@')[1].split(':')[0]
                    print('Checking ', domain)
                    try:
                        MX_record = func_attempts(
                            dns.resolver.resolve, domain, 'MX', attempts=2, raise_on_no_answer=False
                        )
                        if MX_record:
                            has_MX_record = True

                            A_record = func_attempts(
                                dns.resolver.resolve, domain, 'A', attempts=2, raise_on_no_answer=False
                            )
                            if A_record:
                                has_A_record = True
                                try:
                                    site_data = requests.head(url=f'http://{domain}/', timeout=10)
                                    if site_data.status_code == 200:
                                        has_site = True
                                    elif site_data.status_code in [301, 302]:
                                        location = site_data.headers['Location']
                                        if domain in location:
                                            has_site = True
                                except Exception as e:
                                    pass
                            # if has_site:
                            with open(options['outfile'], 'a') as csv_file:
                                writer = csv.writer(csv_file, delimiter=',')
                                writer.writerow(
                                    [line.strip(), domain, has_MX_record, has_site, has_A_record,]
                                )
                                # print(list(data for data in has_site))
                        print(
                            f'Domain {domain} has_MX: {has_MX_record}, has_site: {has_site}, has_A_record: {has_A_record}'
                        )

                        # for rdata in answers:
                        #     print('Host', rdata.exchange, 'has preference', rdata.preference)
                    except dns.resolver.NXDOMAIN as e:
                        pass
                    except Exception as e:
                        pass
        #
        # answers = dns.resolver.resolve('google.com', 'MX')
        # for rdata in answers:
        #     print('Host', rdata.exchange, 'has preference', rdata.preference)
