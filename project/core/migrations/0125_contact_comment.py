# Generated by Django 2.2.8 on 2019-12-19 14:43

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0124_auto_20191219_1432'),
    ]

    operations = [
        migrations.AddField(
            model_name='contact',
            name='comment',
            field=models.TextField(blank=True, null=True),
        ),
    ]
