# Generated by Django 2.2.9 on 2019-12-23 10:56

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0138_auto_20191223_1031'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='tag',
            name='user',
        ),
    ]
