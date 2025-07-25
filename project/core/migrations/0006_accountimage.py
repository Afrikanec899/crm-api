# Generated by Django 2.1.7 on 2019-03-07 08:10

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0005_account_comment'),
    ]

    operations = [
        migrations.CreateModel(
            name='AccountImage',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('file', models.ImageField(upload_to='core.models.account_images_path', verbose_name='File')),
                ('created', models.DateTimeField(auto_now_add=True, verbose_name='Created date')),
                ('account', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='images', to='core.Account')),
            ],
        ),
    ]
