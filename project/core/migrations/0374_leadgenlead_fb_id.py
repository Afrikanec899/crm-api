# Generated by Django 3.1 on 2020-08-31 10:58

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0373_auto_20200831_1044'),
    ]

    operations = [
        migrations.AddField(
            model_name='leadgenlead',
            name='fb_id',
            field=models.BigIntegerField(default=0),
            preserve_default=False,
        ),
    ]
