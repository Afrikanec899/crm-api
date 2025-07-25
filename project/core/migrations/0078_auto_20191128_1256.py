# Generated by Django 2.2.7 on 2019-11-28 12:56

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0077_auto_20191128_1238'),
    ]

    operations = [
        migrations.AddField(
            model_name='campaigndaystat',
            name='command',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='core.Command'),
        ),
        migrations.AddField(
            model_name='userdaystat',
            name='command',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='core.Command'),
        ),
        migrations.AlterUniqueTogether(
            name='campaigndaystat',
            unique_together={('command', 'user', 'date', 'campaign_id')},
        ),
    ]
