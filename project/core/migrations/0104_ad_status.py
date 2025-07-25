# Generated by Django 2.2.8 on 2019-12-12 11:14

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0103_remove_ad_status'),
    ]

    operations = [
        migrations.AddField(
            model_name='ad',
            name='status',
            field=models.CharField(choices=[('ACTIVE', 'Active'), ('PAUSED', 'Paused'), ('DELETED', 'Deleted'), ('ARCHIVED', 'Archived')], default='ACTIVE', max_length=12, verbose_name='Ad account status'),
        ),
    ]
