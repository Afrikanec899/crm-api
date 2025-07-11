import csv
import logging
import os
from pathlib import Path

from django.conf import settings
from django.db.models import F
from django.http.request import QueryDict
from django.utils import timezone
from django.utils.text import slugify

import requests
import short_url

from api.v1.filters import LeadgenLeadFilter
from project.celery_app import app

from ..models.core import LeadgenLead, Link, LinkGroup
from ..utils import ALPHABET, func_attempts
from .helpers import create_broadcast_file

logger = logging.getLogger(__name__)


@app.task(bind=True, autoretry_for=(Exception,), retry_kwargs={'max_retries': 3, 'countdown': 2})
def create_links(self, group_id):
    group = LinkGroup.objects.get(id=group_id)
    batch_size = 1000
    group_links = 0
    groups = 1
    base_name = group.name
    created_groups = [group.pk]
    try:
        # Если есть бродкаст - создаем из кликнутых
        if group.broadcast is not None:
            clicked_links = group.broadcast.get_clicked_links().values_list('leadgen_lead_id', flat=True)
            leads = LeadgenLead.objects.filter(id__in=clicked_links)
        else:
            filter_params = QueryDict('', mutable=True)
            filter_params.update(group.filter_data)
            leads = LeadgenLeadFilter(
                filter_params, queryset=LeadgenLead.objects.filter(phone__isnull=False).exclude(phone='')
            ).qs

        if leads.count() > group.max_links:
            name = f'{base_name} {groups}'
            LinkGroup.objects.filter(pk=group.id).update(status=LinkGroup.PROCESSING, status_comment=None, name=name)
        else:
            LinkGroup.objects.filter(pk=group.id).update(status=LinkGroup.PROCESSING, status_comment=None)

        if leads.exists():
            batch = []
            data = []
            exported_leads = []
            for lead in leads:
                exported_leads.append(lead.id)
                url = lead.create_link(base_url=group.base_url, keyword=group.name, network=group.network)
                link = Link(user=group.user, group=group, leadgen_lead=lead, url=url)
                group_links += 1
                if group.max_links and group_links > group.max_links:
                    groups += 1
                    group.pk = None
                    group.name = f'{base_name} {groups}'
                    group.status = LinkGroup.PROCESSING
                    group.created_at = timezone.now()
                    group.save()
                    created_groups.append(group.pk)
                    group_links = 0

                batch.append(link)
                if len(batch) >= batch_size:
                    Link.objects.bulk_create(batch)
                    LeadgenLead.objects.filter(id__in=exported_leads).update(exported_at=timezone.now())
                    exported_leads = []
                    data = []
                    batch = []

            if data or batch:
                Link.objects.bulk_create(batch)
                LeadgenLead.objects.filter(id__in=exported_leads).update(exported_at=timezone.now())

        for group in LinkGroup.objects.filter(id__in=created_groups):
            create_broadcast_file(group)

    except Exception as e:
        print(e)
        LinkGroup.objects.filter(pk=group.id).update(status=LinkGroup.ERROR, status_comment=e)


@app.task(bind=True, autoretry_for=(Exception,), retry_kwargs={'max_retries': 3, 'countdown': 2})
def process_click_stats(self, data):
    encoder = short_url.UrlEncoder(alphabet=ALPHABET)

    for stat in data:
        try:
            link = Link.objects.get(id=encoder.decode_url(stat['key']))
            link.clicks = F('clicks') + stat['clicks']
            link.save(update_fields=['clicks'])

            LinkGroup.objects.filter(id=link.group_id).update(total_clicks=F('total_clicks') + stat['clicks'])
        except Exception as e:
            logger.error(e, exc_info=True)


@app.task(bind=True, autoretry_for=(Exception,), retry_kwargs={'max_retries': 3, 'countdown': 2})
def process_lander_data(self, data):
    lead = LeadgenLead.objects.filter(uuid=data['uuid']).first()
    if lead:
        if lead.answers is None:
            lead.answers = []
        lead.answers.append(data['data'])

        lead.save(update_fields=['answers'])


@app.task(bind=True, autoretry_for=(Exception,), retry_kwargs={'max_retries': 3, 'countdown': 2})
def fill_shortify_cache_task(self, group_id):
    links = Link.objects.filter(group_id=group_id).prefetch_related('leadgen_lead')
    if links.exists():
        headers = {'X-API-Key': settings.SHORTIFY_API_KEY}
        data = []
        batch_size = 1000
        for link in links:
            data.append({'key': link.key, 'url': link.url})
            if len(data) >= batch_size:
                func_attempts(requests.post, f'{settings.SHORTIFY_URL}/update_cache', headers=headers, json=data)
                data = []
        if data:
            func_attempts(requests.post, f'{settings.SHORTIFY_URL}/update_cache', headers=headers, json=data)
