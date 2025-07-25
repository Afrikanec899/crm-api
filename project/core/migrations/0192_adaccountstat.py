# Generated by Django 2.2.9 on 2020-01-22 09:38

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0191_remove_accountlog_duration'),
    ]

    operations = [
        migrations.CreateModel(
            name='AdAccountStat',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField()),
                ('spend_diff', models.DecimalField(decimal_places=2, default=0, max_digits=10, verbose_name='Spend')),
                ('account', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='core.Account')),
                ('adaccount', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='core.AdAccount')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'unique_together': {('user', 'account', 'adaccount', 'created_at')},
            },
        ),
    ]
