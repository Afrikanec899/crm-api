# Generated by Django 3.1 on 2020-09-03 08:06

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0385_auto_20200903_0727'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='businessshareurl',
            options={'ordering': ('-created_at',)},
        ),
    ]
