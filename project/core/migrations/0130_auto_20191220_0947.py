# Generated by Django 2.2.9 on 2019-12-20 09:47

from django.db import migrations, models
import django_fsm


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0129_auto_20191220_0932'),
    ]

    operations = [
        migrations.AddField(
            model_name='account',
            name='country_code',
            field=models.CharField(default='UA', max_length=2),
        ),
        migrations.AddField(
            model_name='account',
            name='fb_id',
            field=models.BigIntegerField(blank=True, null=True, verbose_name='FB ID'),
        ),
        migrations.AlterField(
            model_name='account',
            name='status',
            field=django_fsm.FSMIntegerField(choices=[(100, 'New'), (0, 'Active'), (20, 'Banned'), (10, 'Logged out'), (30, 'On verification'), (40, 'Inactive'), (50, 'Surfing'), (60, 'Warming'), (65, 'Setup'), (70, 'Ready to use')], default=100, protected=True, verbose_name='Account status'),
        ),
    ]
