# Generated by Django 2.2.10 on 2020-02-21 09:41

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0243_auto_20200221_0749'),
    ]

    operations = [
        migrations.AddField(
            model_name='businessmanager',
            name='shared_at',
            field=models.DateTimeField(blank=True, null=True, verbose_name='Shared at'),
        ),
    ]
