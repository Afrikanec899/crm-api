# Generated by Django 3.1.7 on 2021-03-11 11:15

import django.core.serializers.json
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0466_contact_has_leads'),
    ]

    operations = [
        migrations.AddField(
            model_name='contact',
            name='fake_email',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='contact',
            name='postback_data',
            field=models.JSONField(blank=True, encoder=django.core.serializers.json.DjangoJSONEncoder, null=True),
        ),
        migrations.AddField(
            model_name='contact',
            name='raw_data',
            field=models.JSONField(blank=True, encoder=django.core.serializers.json.DjangoJSONEncoder, null=True),
        ),
    ]
