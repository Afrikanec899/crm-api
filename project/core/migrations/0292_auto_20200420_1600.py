# Generated by Django 3.0.5 on 2020-04-20 16:00

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0291_businessmanager_banned'),
    ]

    operations = [
        migrations.AlterField(
            model_name='adaccount',
            name='business',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='adaccounts', to='core.BusinessManager'),
        ),
    ]
