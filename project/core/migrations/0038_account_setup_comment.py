# Generated by Django 2.2 on 2019-09-26 11:44

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0037_auto_20190926_1140'),
    ]

    operations = [
        migrations.AddField(
            model_name='account',
            name='setup_comment',
            field=models.CharField(blank=True, max_length=1024, null=True, verbose_name='Comment for setuper'),
        ),
    ]
