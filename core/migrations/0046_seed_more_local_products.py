from decimal import Decimal

from django.db import migrations


PRODUCTS = [
    {
        "name": "Women's Platform Sandals Model L818-3", "category": "Shoes & Footwear",
        "cost": "68.00", "stock": 36, "sizes": "37, 38, 39, 40, 41, 42",
        "colors": "Black, Brown, White", "code": "l818-3",
    },
    {
        "name": "Men's Triple-Buckle Slides Model 018-A008", "category": "Shoes & Footwear",
        "cost": "40.00", "stock": 36, "sizes": "40, 41, 42, 43, 44, 45",
        "colors": "Brown", "code": "018-a008",
    },
    {
        "name": "Women's Triple-Buckle Sandals Model 1901-7", "category": "Shoes & Footwear",
        "cost": "60.00", "stock": 36, "sizes": "37, 38, 39, 40, 41, 42",
        "colors": "Dark Brown, Black, Tan", "code": "1901-7",
    },
    {
        "name": "Women's Colour-Block Sandals Model 1901-5", "category": "Shoes & Footwear",
        "cost": "55.00", "stock": 36, "sizes": "37, 38, 39, 40, 41, 42",
        "colors": "Black and Brown, Black and Beige", "code": "1901-5",
    },
    {
        "name": "Patterned Slide Sandals Model 018-A002", "category": "Shoes & Footwear",
        "cost": "40.00", "stock": 36, "sizes": "40, 41, 42, 43, 44, 45",
        "colors": "Tan, Black, Dark Brown", "code": "018-a002",
    },
    {
        "name": "H-Style Slide Sandals Model 018-A003", "category": "Shoes & Footwear",
        "cost": "40.00", "stock": 36, "sizes": "40, 41, 42, 43, 44, 45",
        "colors": "Black, Brown, Dark Brown", "code": "018-a003",
    },
    {
        "name": "Printed T-Shirt Model W-004", "category": "Fashion & Clothing",
        "cost": "48.00", "stock": 12, "sizes": "M, L, XL, 2XL",
        "colors": "Pink, Black, White", "code": "w004",
    },
    {
        "name": "Women's Platform Sandals Model L818-1", "category": "Shoes & Footwear",
        "cost": "65.00", "stock": 36, "sizes": "37, 38, 39, 40, 41, 42",
        "colors": "Black, Brown, White", "code": "l818-1",
    },
]


def seed_products(apps, schema_editor):
    Product = apps.get_model("core", "Product")
    ProductImage = apps.get_model("core", "ProductImage")
    Category = apps.get_model("core", "Category")

    for item in PRODUCTS:
        category_slug = item["category"].lower().replace("&", "and").replace(" ", "-")
        category, _ = Category.objects.get_or_create(
            name=item["category"], defaults={"slug": category_slug}
        )
        code = item["code"]
        customer_image = f"products/customer/{code}-clean.png"
        values = {
            "description": (
                f"Quality {item['name'].lower()}, available in {item['colors'].lower()} "
                f"and sizes {item['sizes']}."
            ),
            "category": category,
            "rmb_price": Decimal(item["cost"]),
            "image": customer_image,
            "product_type": "local",
            "status": "active",
            "stock_quantity": item["stock"],
            "size_options": item["sizes"],
            "color_options": item["colors"],
            "is_available": True,
            "is_featured": True,
            "delivery_min_days": 1,
            "delivery_max_days": 10,
            "source_platform": "other",
            "supplier_name": "admin",
        }
        product = Product.objects.filter(name=item["name"]).order_by("pk").first()
        if product:
            for field, value in values.items():
                setattr(product, field, value)
            product.save()
        else:
            product = Product.objects.create(
                name=item["name"], sku=f"LOC-{code.upper()}-SEED",
                slug=item["name"].lower().replace("'", "").replace(" ", "-"), **values
            )

        ProductImage.objects.update_or_create(
            product=product, is_primary=True,
            defaults={
                "original_image": f"products/originals/{code}.jpeg",
                "customer_image": customer_image,
                "processing_status": "ready",
                "visibility": "public",
                "position": 0,
                "alt_text": item["name"],
            },
        )


class Migration(migrations.Migration):
    dependencies = [("core", "0045_seed_additional_local_products")]

    operations = [migrations.RunPython(seed_products, migrations.RunPython.noop)]
