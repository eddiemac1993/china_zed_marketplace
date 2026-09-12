from django.db import migrations


def restore_stocked_products(apps, schema_editor):
    Product = apps.get_model("core", "Product")
    Product.objects.using(schema_editor.connection.alias).filter(
        show_on_homepage=True, is_available=True, is_deleted=False,
        product_type="local", stock_quantity__gt=0, status="out_of_stock",
    ).update(status="active")


class Migration(migrations.Migration):
    dependencies = [("core", "0054_searchhistory")]
    operations = [migrations.RunPython(restore_stocked_products, migrations.RunPython.noop)]
