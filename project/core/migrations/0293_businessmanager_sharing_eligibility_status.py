# Generated by Django 3.0.5 on 2020-04-20 16:37

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0292_auto_20200420_1600'),
    ]

    operations = [
        migrations.AddField(
            model_name='businessmanager',
            name='sharing_eligibility_status',
            field=models.CharField(default='enabled', max_length=128),
        ),
    ]
