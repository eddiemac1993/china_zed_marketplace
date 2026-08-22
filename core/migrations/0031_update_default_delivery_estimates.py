from django.db import migrations


def update_delivery_estimates(apps, schema_editor):
    Product = apps.get_model("core", "Product")
    Product.objects.filter(delivery_min_days=14, delivery_max_days=30).update(
        delivery_min_days=24, delivery_max_days=60
    )

    CustomerProductRequest = apps.get_model("core", "CustomerProductRequest")
    CustomerProductRequest.objects.filter(estimated_delivery_days="14-30 days").update(
        estimated_delivery_days="24-60 days"
    )


def revert_delivery_estimates(apps, schema_editor):
    Product = apps.get_model("core", "Product")
    Product.objects.filter(delivery_min_days=24, delivery_max_days=60).update(
        delivery_min_days=14, delivery_max_days=30
    )

    CustomerProductRequest = apps.get_model("core", "CustomerProductRequest")
    CustomerProductRequest.objects.filter(estimated_delivery_days="24-60 days").update(
        estimated_delivery_days="14-30 days"
    )


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0030_alter_customerproductrequest_estimated_delivery_days_and_more"),
    ]

    operations = [
        migrations.RunPython(update_delivery_estimates, revert_delivery_estimates),
    ]
