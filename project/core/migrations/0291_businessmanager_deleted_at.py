# Generated by Django 3.0.5 on 2020-04-20 14:31

from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0290_auto_20200417_1038'),
    ]

    operations = [
        migrations.AddField(
            model_name='businessmanager',
            name='deleted_at',
            field=models.DateTimeField(default=django.utils.timezone.now, verbose_name='Deleted at'),
        ),
    ]
