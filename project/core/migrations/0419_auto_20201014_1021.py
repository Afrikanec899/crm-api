# Generated by Django 3.1.2 on 2020-10-14 10:21

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0418_auto_20201014_1020'),
    ]

    operations = [
        migrations.AddField(
            model_name='adaccounttransaction',
            name='end_at_ts',
            field=models.PositiveIntegerField(blank=True, db_index=True, null=True, verbose_name='Billing end timestamp'),
        ),
        migrations.AddField(
            model_name='adaccounttransaction',
            name='start_at_ts',
            field=models.PositiveIntegerField(blank=True, db_index=True, null=True, verbose_name='Billing start timestamp'),
        ),
    ]
