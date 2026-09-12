from decimal import Decimal
from django.db import migrations, models


def set_active_discount(apps, schema_editor):
    apps.get_model("core", "ExchangeRate").objects.using(schema_editor.connection.alias).filter(
        is_active=True, is_deleted=False,
    ).update(wholesale_discount_percentage=Decimal("23.00"))


class Migration(migrations.Migration):
    dependencies = [("core", "0055_restore_stocked_homepage_products")]
    operations = [
        migrations.AlterField(
            model_name="exchangerate", name="wholesale_discount_percentage",
            field=models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("23.00"),
                help_text="Discount off the retail price applied per unit once the wholesale quantity is reached."),
        ),
        migrations.RunPython(set_active_discount, migrations.RunPython.noop),
    ]
