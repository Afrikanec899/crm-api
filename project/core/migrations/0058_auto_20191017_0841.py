# Generated by Django 2.2 on 2019-10-17 08:41

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0057_auto_20191009_0929'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='account',
            name='ban_reason',
        ),
        migrations.RemoveField(
            model_name='account',
            name='reason',
        ),
        migrations.RemoveField(
            model_name='account',
            name='setup_comment',
        ),
        migrations.RemoveField(
            model_name='account',
            name='track_link',
        ),
    ]
