# Generated by Django 3.1.6 on 2021-02-15 11:09

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0452_finaccount_updated_at'),
    ]

    operations = [
        migrations.AlterField(
            model_name='user',
            name='role',
            field=models.PositiveSmallIntegerField(choices=[(0, 'Admin'), (10, 'Mediabuyer'), (20, 'Financier'), (30, 'Farmer'), (40, 'Supplier'), (80, 'Supplier Teamlead'), (50, 'Setuper'), (60, 'Manager'), (70, 'Teamlead'), (90, 'Junior')], default=10, verbose_name='User role'),
        ),
    ]
