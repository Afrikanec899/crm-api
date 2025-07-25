# Generated by Django 3.0.5 on 2020-04-13 09:42

import creditcards.models
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0282_auto_20200410_0733'),
    ]

    operations = [
        migrations.AddField(
            model_name='accountlog',
            name='card_number',
            field=creditcards.models.CardNumberField(blank=True, db_index=True, max_length=25, null=True, verbose_name='Credit card number'),
        ),
        migrations.AlterField(
            model_name='accountlog',
            name='log_type',
            field=models.PositiveSmallIntegerField(choices=[(0, 'Status'), (1, 'Manager'), (2, 'Card')], db_index=True, default=0),
        ),
        migrations.AlterField(
            model_name='adaccounttransaction',
            name='charge_type',
            field=models.CharField(max_length=32, verbose_name='Charge type'),
        ),
        migrations.AlterField(
            model_name='adaccounttransaction',
            name='payment_option',
            field=models.CharField(max_length=32, verbose_name='Payment option'),
        ),
        migrations.AlterField(
            model_name='adaccounttransaction',
            name='product_type',
            field=models.CharField(blank=True, max_length=32, null=True, verbose_name='Product type'),
        ),
        migrations.AlterField(
            model_name='adaccounttransaction',
            name='status',
            field=models.CharField(max_length=32, verbose_name='Payment status'),
        ),
        migrations.AlterField(
            model_name='adaccounttransaction',
            name='transaction_type',
            field=models.CharField(blank=True, max_length=32, null=True, verbose_name='Transaction type'),
        ),
        migrations.AlterField(
            model_name='adaccounttransaction',
            name='vat_invoice_id',
            field=models.CharField(blank=True, max_length=32, null=True, verbose_name='VAT invoice ID'),
        ),
    ]
