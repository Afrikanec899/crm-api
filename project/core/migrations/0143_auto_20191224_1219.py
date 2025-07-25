# Generated by Django 2.2.9 on 2019-12-24 12:19

from django.db import migrations
from django.utils import timezone

ACTIVE = 0
LOGOUT = 10
SURFING = 50
WARMING = 60
NEW = 100


def fill_status_log(apps, *args, **kwargs):
    now = timezone.now()
    Account = apps.get_model('core', 'Account')
    AccountStatusLog = apps.get_model('core', 'AccountStatusLog')
    for account in Account.objects.all().exclude(status=20):
        if account.status == ACTIVE:
            start_at = account.active_at or now
        elif account.status == LOGOUT:
            start_at = account.logout_at or now
        elif account.status == SURFING:
            start_at = account.surfing_at or now
        elif account.status == WARMING:
            start_at = account.warming_at or now
        elif account.status == NEW:
            start_at = account.created_at or now
        else:
            start_at = now
        AccountStatusLog.objects.create(account=account, start_at=start_at, status=account.status)


class Migration(migrations.Migration):
    dependencies = [
        ('core', '0142_accountstatuslog'),
    ]

    operations = [
        migrations.RunPython(fill_status_log),
    ]
