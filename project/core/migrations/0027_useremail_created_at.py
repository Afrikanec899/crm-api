# Generated by Django 2.2 on 2019-08-28 11:10

import datetime
from django.db import migrations, models
from django.utils.timezone import utc


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0026_useremail_phone'),
    ]

    operations = [
        migrations.AddField(
            model_name='useremail',
            name='created_at',
            field=models.DateTimeField(auto_now_add=True, default=datetime.datetime(2019, 8, 28, 11, 10, 57, 246738, tzinfo=utc), verbose_name='Date added'),
            preserve_default=False,
        ),
    ]
