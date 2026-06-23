from decimal import Decimal

from django.db import migrations, models


def update_twenty_percent_rates(apps, schema_editor):
    ExchangeRate = apps.get_model("core", "ExchangeRate")
    ExchangeRate.objects.filter(deposit_percentage=Decimal("20.00")).update(
        deposit_percentage=Decimal("35.00")
    )


def restore_twenty_percent_rates(apps, schema_editor):
    ExchangeRate = apps.get_model("core", "ExchangeRate")
    ExchangeRate.objects.filter(deposit_percentage=Decimal("35.00")).update(
        deposit_percentage=Decimal("20.00")
    )


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0016_productreview_stockmovement_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="exchangerate",
            name="deposit_percentage",
            field=models.DecimalField(
                decimal_places=2, default=Decimal("35.00"), max_digits=5
            ),
        ),
        migrations.RunPython(update_twenty_percent_rates, restore_twenty_percent_rates),
    ]
