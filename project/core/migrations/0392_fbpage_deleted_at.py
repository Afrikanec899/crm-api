# Generated by Django 3.1 on 2020-09-14 10:31

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0391_auto_20200908_0925'),
    ]

    operations = [
        migrations.AddField(
            model_name='fbpage',
            name='deleted_at',
            field=models.DateTimeField(blank=True, default=None, null=True, verbose_name='Deleted at'),
        ),
    ]
