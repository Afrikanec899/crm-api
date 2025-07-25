# Generated by Django 2.2 on 2019-09-26 13:24

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0038_account_setup_comment'),
    ]

    operations = [
        migrations.AlterField(
            model_name='account',
            name='status',
            field=models.PositiveSmallIntegerField(choices=[(100, 'New'), (0, 'Active'), (20, 'Banned'), (10, 'Logged out'), (30, 'On verification'), (40, 'Inactive'), (50, 'Surfing'), (60, 'Warming'), (65, 'Setup'), (70, 'Ready to use')], default=100, verbose_name='Account status'),
        ),
    ]
