# Generated by Django 2.2.8 on 2019-12-05 12:20

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0086_auto_20191205_1212'),
    ]

    operations = [
        migrations.RenameField(
            model_name='adaccount',
            old_name='balance',
            new_name='amount_spent',
        ),
        migrations.AddField(
            model_name='adaccount',
            name='campaign_id',
            field=models.IntegerField(blank=True, null=True, verbose_name='Tracker campaign ID'),
        ),
    ]
