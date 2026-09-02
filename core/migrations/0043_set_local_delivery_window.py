from django.db import migrations


def set_local_delivery_window(apps, schema_editor):
    Product = apps.get_model("core", "Product")
    Product.objects.filter(product_type="local").update(
        delivery_min_days=1,
        delivery_max_days=10,
    )


class Migration(migrations.Migration):
    dependencies = [("core", "0042_seed_local_footwear_products")]

    operations = [migrations.RunPython(set_local_delivery_window, migrations.RunPython.noop)]
