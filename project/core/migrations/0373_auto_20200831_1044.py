# Generated by Django 3.1 on 2020-08-31 10:44

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0372_auto_20200831_1035'),
    ]

    operations = [
        migrations.AddField(
            model_name='leadgenlead',
            name='country_code',
            field=models.CharField(blank=True, max_length=2, null=True, verbose_name='Country code'),
        ),
        migrations.AlterField(
            model_name='leadgenlead',
            name='country',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='core.country'),
        ),
    ]
