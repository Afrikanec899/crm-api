# Generated by Django 3.0.8 on 2020-08-03 09:58

from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0358_flowdaystat_payment'),
    ]

    operations = [
        migrations.AlterField(
            model_name='userrequest',
            name='updated_at',
            field=models.DateTimeField(default=django.utils.timezone.now, verbose_name='Done datetime'),
        ),
    ]
