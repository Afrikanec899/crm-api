# Generated by Django 3.1.5 on 2021-01-27 13:04

from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0451_auto_20210127_1245'),
    ]

    operations = [
        migrations.AddField(
            model_name='finaccount',
            name='updated_at',
            field=models.DateTimeField(default=django.utils.timezone.now),
        ),
    ]
