# Generated by Django 2.2.11 on 2020-04-10 07:33

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0281_auto_20200410_0624'),
    ]

    operations = [
        migrations.AlterField(
            model_name='adaccount',
            name='payment_cycle',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True, verbose_name='Payment cycle'),
        ),
    ]
