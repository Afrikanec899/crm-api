# Generated by Django 2.2 on 2019-09-27 12:53

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0044_auto_20190927_1230'),
    ]

    operations = [
        migrations.AlterField(
            model_name='account',
            name='created_by',
            field=models.ForeignKey(default=1, on_delete=django.db.models.deletion.DO_NOTHING, related_name='created_accounts', to=settings.AUTH_USER_MODEL),
            preserve_default=False,
        ),
    ]
