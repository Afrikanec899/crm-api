# Generated by Django 3.1.1 on 2020-10-12 10:45

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0413_auto_20201012_0953'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='adaccount',
            name='adspixels',
        ),
        migrations.AddField(
            model_name='adaccount',
            name='deleted_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
