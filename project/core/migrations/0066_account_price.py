# Generated by Django 2.2.6 on 2019-10-24 13:09

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0065_auto_20191024_1259'),
    ]

    operations = [
        migrations.AddField(
            model_name='account',
            name='price',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=8, verbose_name='Account price'),
        ),
    ]
