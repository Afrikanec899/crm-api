# Generated by Django 3.1 on 2020-08-27 07:27

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0367_auto_20200827_0722'),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name='pageleadgen',
            unique_together={('page', 'leadgen', 'leadform_id')},
        ),
    ]
