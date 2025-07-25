# Generated by Django 3.0.5 on 2020-04-22 11:10

from django.conf import settings
import django.contrib.postgres.fields.jsonb
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0295_merge_20200421_0614'),
    ]

    operations = [
        migrations.AlterField(
            model_name='businessmanager',
            name='can_create_ad_account',
            field=models.BooleanField(default=False, verbose_name='Can create ad account'),
        ),
        migrations.CreateModel(
            name='Rule',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=64)),
                ('evaluation_spec', django.contrib.postgres.fields.jsonb.JSONField()),
                ('schedule_spec', django.contrib.postgres.fields.jsonb.JSONField()),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'abstract': False,
            },
        ),
    ]
