# Generated by Django 3.1 on 2020-08-19 09:06

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0363_auto_20200811_0901'),
    ]

    operations = [
        migrations.AddField(
            model_name='accountpayment',
            name='amount_uah',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True, verbose_name='UAH Amount'),
        ),
    ]
