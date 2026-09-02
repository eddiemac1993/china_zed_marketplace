from django.db import migrations, models
import django.db.models.deletion
from datetime import timedelta


def link_existing_draft_products(apps, schema_editor):
    SupplierProductRequest = apps.get_model("core", "SupplierProductRequest")
    Product = apps.get_model("core", "Product")
    used_product_ids = set(
        SupplierProductRequest.objects.exclude(converted_product__isnull=True)
        .values_list("converted_product_id", flat=True)
    )

    for submission in SupplierProductRequest.objects.filter(is_approved=True, converted_product__isnull=True):
        candidates = Product.objects.filter(
            name=submission.product_name,
            status="draft",
            created_at__gte=submission.created_at,
            created_at__lte=submission.created_at + timedelta(minutes=10),
        ).exclude(pk__in=used_product_ids)
        if submission.source_link:
            candidates = candidates.filter(source_link=submission.source_link)
        candidate_ids = list(candidates.values_list("pk", flat=True)[:2])
        if len(candidate_ids) == 1:
            submission.converted_product_id = candidate_ids[0]
            submission.save(update_fields=["converted_product"])
            used_product_ids.add(candidate_ids[0])


class Migration(migrations.Migration):
    dependencies = [("core", "0040_seed_footwear_category")]

    operations = [
        migrations.AddField(
            model_name="supplierproductrequest",
            name="converted_product",
            field=models.OneToOneField(
                blank=True,
                help_text="Draft product created from this approved submission.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="supplier_request",
                to="core.product",
            ),
        ),
        migrations.RunPython(link_existing_draft_products, migrations.RunPython.noop),
    ]
