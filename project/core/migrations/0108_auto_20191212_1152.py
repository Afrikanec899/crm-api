# Generated by Django 2.2.8 on 2019-12-12 11:52

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0107_ad_adaccount'),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name='ad',
            unique_together={('account', 'adaccount', 'ad_id')},
        ),
    ]
