import datetime
import json
from pprint import pprint

import requests
from django.core.management.base import BaseCommand
from django.db.models import Count, Q
from django.utils import timezone

from core.models.core import Account, AccountLog, User, UserRequest
from core.tasks import create_empty_mla_profiles


class Command(BaseCommand):
    help = ''

    def add_arguments(self, parser):
        parser.add_argument("-d", "--days", action="store", dest="days", type=int, help="Days", default=0)

    def handle(self, *args, **options):
        # create_empty_mla_profiles(1, 1)
        api_url = 'http://localhost:45000/api/v2/profile'
        profiles = requests.get(api_url, timeout=30).json()
        print(len(profiles))
        # pprint(profiles, indent=4)
        groups = {}
        for p in profiles:
            if p.get('group'):
                if p['group'] not in groups.keys():
                    groups[p['group']] = p['name']

        pprint(groups)

        # status = requests.post(f'{api_url}/ceeab90c-4dab-434b-afa8-d8f70b2f5ae2', json={'name': 'UA 7797 380963816658 test'})
        # pprint(status)

        # pprint(requests.get(f'{api_url}/ceeab90c-4dab-434b-afa8-d8f70b2f5ae2').json())
        # pprint(profiles)
