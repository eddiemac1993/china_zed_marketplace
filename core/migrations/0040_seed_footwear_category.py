from django.db import migrations


def add_footwear_category(apps, schema_editor):
    Category = apps.get_model("core", "Category")
    Category.objects.get_or_create(name="Shoes & Footwear", defaults={"slug": "shoes-footwear"})


class Migration(migrations.Migration):
    dependencies = [("core", "0039_variant_uniqueness")]

    operations = [migrations.RunPython(add_footwear_category, migrations.RunPython.noop)]
