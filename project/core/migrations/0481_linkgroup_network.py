# Generated by Django 3.1.8 on 2021-05-10 08:59

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0480_user_mla_group_id'),
    ]

    operations = [
        migrations.AddField(
            model_name='linkgroup',
            name='network',
            field=models.CharField(choices=[('default', 'Default'), ('wlt', 'WLT')], default='default', max_length=32),
        ),
    ]
