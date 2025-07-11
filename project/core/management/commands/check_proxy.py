import datetime
import json
from pprint import pprint

from django.core.management.base import BaseCommand
from django.template.loader import render_to_string

from haproxystats import HAProxyServer
from redis import Redis

from core.models import User
from core.models.core import Notification

redis = Redis(host='redis', db=0, decode_responses=True)


class Command(BaseCommand):
    help = ''

    def handle(self, *args, **options):
        haproxy = HAProxyServer('proxy.holyaff.com:9999/stats', user='alter', password='holyrac6vDcLz')
        # print(haproxy.last_update)
        pprint(json.loads(haproxy.to_json()))
        for b in haproxy.backends:
            #     print('%s: %s' % (b.name, b.status))
            for l in b.listeners:
                print(l.name, l.status, l.lastchg)
                if 'up' not in l.status.lower() and l.lastchg > 30 * 5:
                    print(l)
                    sent = redis.get(f'down_alert_{l.name}')
                    if not sent:
                        redis.setex(f'down_alert_{l.name}', 3600, 1)
                        message = render_to_string(
                            'core/proxy_down.html',
                            {'proxy_name': l.name, 'duration': str(datetime.timedelta(seconds=l.lastchg))},
                        )
                        data = {'message': message}

                        recipient = User.objects.get(id=1)
                        Notification.create(
                            recipient=recipient,
                            level=Notification.CRITICAL,
                            category=Notification.PROXY,
                            data=data,
                            sender=None,
                        )
                else:
                    sent = redis.get(f'down_alert_{l.name}')
                    if sent:
                        redis.delete(f'down_alert_{l.name}')
                        message = render_to_string(
                            'core/proxy_up.html',
                            {'proxy_name': l.name, 'duration': str(datetime.timedelta(seconds=l.lastchg))},
                        )
                        data = {'message': message}

                        recipient = User.objects.get(id=1)
                        Notification.create(
                            recipient=recipient,
                            level=Notification.CRITICAL,
                            category=Notification.PROXY,
                            data=data,
                            sender=None,
                        )
