# Generated by Django 2.2.9 on 2019-12-20 09:32

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0128_action'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='account',
            name='comment',
        ),
        migrations.RemoveField(
            model_name='account',
            name='domain',
        ),
        migrations.RemoveField(
            model_name='account',
            name='server',
        ),
    ]
