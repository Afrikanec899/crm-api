# Generated by Django 2.2 on 2019-05-31 04:05

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0022_auto_20190429_0733'),
    ]

    operations = [
        migrations.AlterField(
            model_name='account',
            name='login',
            field=models.CharField(blank=True, max_length=255, null=True, verbose_name='Login'),
        ),
        migrations.AlterField(
            model_name='account',
            name='password',
            field=models.CharField(blank=True, max_length=255, null=True, verbose_name='Password'),
        ),
    ]
