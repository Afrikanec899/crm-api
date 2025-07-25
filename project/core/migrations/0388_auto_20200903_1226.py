# Generated by Django 3.1 on 2020-09-03 12:26

from django.db import migrations, models
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0387_fbpage_is_published'),
    ]

    operations = [
        migrations.AlterField(
            model_name='adaccounttransaction',
            name='transaction_id',
            field=models.CharField(db_index=True, default=uuid.uuid4, max_length=64),
        ),
        migrations.AlterField(
            model_name='notification',
            name='category',
            field=models.CharField(choices=[('account', 'account'), ('adaccount', 'adaccount'), ('request', 'request'), ('ad', 'ad'), ('finance', 'finance'), ('system', 'system'), ('proxy', 'proxy'), ('page', 'page')], default='account', max_length=64, verbose_name='Notification category'),
        ),
        migrations.AlterIndexTogether(
            name='adaccounttransaction',
            index_together={('adaccount', 'transaction_id')},
        ),
    ]
