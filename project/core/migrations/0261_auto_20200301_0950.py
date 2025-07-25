# Generated by Django 2.2.10 on 2020-03-01 09:50

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0260_useraccountdaystat_cost'),
    ]

    operations = [
        migrations.AddField(
            model_name='adaccountdaystat',
            name='clicks',
            field=models.PositiveIntegerField(default=0, verbose_name='clicks'),
        ),
        migrations.AlterField(
            model_name='adaccountdaystat',
            name='adaccount',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='core.AdAccount'),
        ),
        migrations.AlterField(
            model_name='adaccountdaystat',
            name='date',
            field=models.DateField(db_index=True),
        ),
        migrations.AlterField(
            model_name='campaigndaystat',
            name='campaign',
            field=models.ForeignKey(default=1, on_delete=django.db.models.deletion.PROTECT, to='core.Campaign'),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name='campaigndaystat',
            name='date',
            field=models.DateField(db_index=True),
        ),
        migrations.AlterField(
            model_name='useraccountdaystat',
            name='profit',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=10, verbose_name='Profit'),
        ),
    ]
