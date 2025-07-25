# Generated by Django 3.1.5 on 2021-01-27 09:30

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0445_auto_20210127_0852'),
    ]

    operations = [
        migrations.AlterField(
            model_name='action',
            name='action_object_repr',
            field=models.CharField(blank=True, db_index=True, max_length=255, null=True, verbose_name='Action object repr'),
        ),
        migrations.AlterField(
            model_name='action',
            name='target_object_repr',
            field=models.CharField(blank=True, db_index=True, max_length=255, null=True, verbose_name='Target repr'),
        ),
        migrations.AlterField(
            model_name='action',
            name='verb',
            field=models.CharField(db_index=True, max_length=255),
        ),
    ]
