# Generated by Django 2.2.9 on 2020-01-21 12:32

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0190_accountlog_duration'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='accountlog',
            name='duration',
        ),
    ]
