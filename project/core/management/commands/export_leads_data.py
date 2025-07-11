import csv
import os
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from core.models.core import LeadgenLead


class Command(BaseCommand):
    help = ''

    def handle(self, *args, **options):
        answered_leads = LeadgenLead.objects.filter(answers__isnull=False).exclude()
        print('Total answers ', answered_leads.count())
        base_directory = os.path.join(settings.MEDIA_ROOT, 'exports')
        Path(base_directory).mkdir(parents=True, exist_ok=True)

        for lead in answered_leads:
            for answer in lead.answers[:1]:
                filename = f'answered_gender_{answer.get("gender", "unknown")}_age_{answer.get("age", "unknown")}_family_{answer.get("family_count", "unknown")}.csv'
                full_path = os.path.join(base_directory, filename)
                with open(full_path, 'a', newline='') as csvfile:
                    writer = csv.writer(csvfile, delimiter=';', quoting=csv.QUOTE_ALL)
                    writer.writerow(
                        [
                            lead.uuid,
                            lead.name,
                            lead.email,
                            lead.phone,
                            answer.get('gender'),
                            answer.get('age'),
                            answer.get('family_count'),
                            answer.get('whant_ps5') or answer.get('want_ps5'),
                        ]
                    )
                    # writer.writerow(['uuid', 'name', 'email', 'phone', 'gender', 'age', 'family_count'])
