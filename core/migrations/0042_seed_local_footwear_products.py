from decimal import Decimal

from django.db import migrations


PRODUCTS = [
    {
        "name": "Footwear Model W51",
        "description": "Comfortable footwear model W51, available in multiple colours and sizes 37–41.",
        "cost": "150.00",
        "stock": 30,
        "sizes": "37, 38, 39, 40, 41",
        "colors": "White, Grey, Black",
        "image": "products/customer/w51-clean.png",
        "sku": "LOC-W51-SEED",
        "slug": "footwear-model-w51",
    },
    {
        "name": "Footwear Model S10",
        "description": "Comfortable footwear model S10, available in multiple colours and sizes 39–44.",
        "cost": "100.00",
        "stock": 30,
        "sizes": "39, 40, 41, 42, 43, 44",
        "colors": "Blue, Blue and Orange, Green",
        "image": "products/customer/s10-clean.png",
        "sku": "LOC-S10-SEED",
        "slug": "footwear-model-s10",
    },
    {
        "name": "Footwear Model NF107",
        "description": "Comfortable footwear model NF107, available in multiple colours and sizes 36–41.",
        "cost": "190.00",
        "stock": 24,
        "sizes": "36, 37, 38, 39, 40, 41",
        "colors": "Green, Black",
        "image": "products/customer/nf107-clean.png",
        "sku": "LOC-NF107-SEED",
        "slug": "footwear-model-nf107",
    },
    {
        "name": "Footwear Model K663",
        "description": "Comfortable footwear model K663, available in multiple colours and sizes 37–42.",
        "cost": "100.00",
        "stock": 30,
        "sizes": "37, 38, 39, 40, 41, 42",
        "colors": "Grey, Black, Pink",
        "image": "products/customer/k663-clean.png",
        "sku": "LOC-K663-SEED",
        "slug": "footwear-model-k663",
    },
    {
        "name": "Footwear Model 1619-3",
        "description": "Comfortable footwear model 1619-3, available in multiple colours and sizes 37–42.",
        "cost": "60.00",
        "stock": 36,
        "sizes": "37, 38, 39, 40, 41, 42",
        "colors": "White and Black, Black and Brown, Brown",
        "image": "products/customer/1619-3-clean.png",
        "sku": "LOC-1619-3-SEED",
        "slug": "footwear-model-1619-3",
    },
]


def seed_local_footwear(apps, schema_editor):
    Product = apps.get_model("core", "Product")
    Category = apps.get_model("core", "Category")
    category, _ = Category.objects.get_or_create(
        name="Shoes & Footwear",
        defaults={"slug": "shoes-footwear"},
    )
    for item in PRODUCTS:
        product = Product.objects.filter(name=item["name"]).order_by("pk").first()
        values = {
            "description": item["description"],
            "category": category,
            "rmb_price": Decimal(item["cost"]),
            "image": item["image"],
            "product_type": "local",
            "status": "active",
            "stock_quantity": item["stock"],
            "size_options": item["sizes"],
            "color_options": item["colors"],
            "is_available": True,
            "is_featured": True,
            "source_platform": "other",
            "supplier_name": "admin",
        }
        if product:
            for field, value in values.items():
                setattr(product, field, value)
            product.save()
        else:
            Product.objects.create(
                name=item["name"], sku=item["sku"], slug=item["slug"], **values
            )


class Migration(migrations.Migration):
    dependencies = [("core", "0041_supplierproductrequest_converted_product")]

    operations = [migrations.RunPython(seed_local_footwear, migrations.RunPython.noop)]
