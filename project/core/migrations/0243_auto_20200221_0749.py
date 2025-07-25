# Generated by Django 2.2.10 on 2020-02-21 07:49

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0242_auto_20200218_1536'),
    ]

    operations = [
        migrations.AddField(
            model_name='businessmanager',
            name='share_url',
            field=models.CharField(blank=True, max_length=512, null=True, verbose_name='Share URL'),
        ),
        migrations.AlterField(
            model_name='businessmanager',
            name='business_id',
            field=models.BigIntegerField(unique=True, verbose_name='BM id'),
        ),
    ]
