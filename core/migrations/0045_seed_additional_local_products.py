from decimal import Decimal

from django.db import migrations


PRODUCTS = [
    {
        "name": "Women's Slide Sandals Model 3996-2", "category": "Shoes & Footwear",
        "cost": "65.00", "stock": 36, "sizes": "37, 38, 39, 40, 41, 42",
        "colors": "Black, Brown, White", "code": "3996-2",
    },
    {
        "name": "Women's Straight-Leg Jeans Model 2610", "category": "Fashion & Clothing",
        "cost": "90.00", "stock": 10, "sizes": "30, 31, 32, 33, 34, 35, 36",
        "colors": "Brown", "code": "2610",
    },
    {
        "name": "Women's Wide-Leg Trousers Model W-003", "category": "Fashion & Clothing",
        "cost": "60.00", "stock": 1, "sizes": "M, L, XL, 2XL, 3XL, 4XL",
        "colors": "Grey", "code": "w003",
    },
    {
        "name": "Women's Leopard Sandals Model 771-21", "category": "Shoes & Footwear",
        "cost": "38.00", "stock": 36, "sizes": "36, 37, 38, 39, 40",
        "colors": "Tan Leopard, Brown Leopard, Grey Leopard", "code": "771-21",
    },
    {
        "name": "Women's T-Shirt Model W-006", "category": "Fashion & Clothing",
        "cost": "38.00", "stock": 12, "sizes": "M, L, XL, 2XL",
        "colors": "Red, White, Black", "code": "w006",
    },
    {
        "name": "Cargo Jeans Model 2707", "category": "Fashion & Clothing",
        "cost": "100.00", "stock": 10, "sizes": "29, 30, 31, 32, 33, 34",
        "colors": "Grey", "code": "2707",
    },
    {
        "name": "Straight-Leg Jeans Model 2608", "category": "Fashion & Clothing",
        "cost": "90.00", "stock": 10, "sizes": "30, 31, 32, 33, 34, 35, 36",
        "colors": "Brown", "code": "2608",
    },
    {
        "name": "Women's Double-Strap Slides Model 1818-01", "category": "Shoes & Footwear",
        "cost": "60.00", "stock": 36, "sizes": "37, 38, 39, 40, 41, 42",
        "colors": "White, Brown, Black", "code": "1818-01",
    },
    {
        "name": "Casual Sneakers Model 0569", "category": "Shoes & Footwear",
        "cost": "90.00", "stock": 30, "sizes": "39, 40, 41, 42, 43, 44, 45",
        "colors": "Black, White and Black, White and Green", "code": "0569",
    },
    {
        "name": "Women's Buckle Sandals Model 1619-2", "category": "Shoes & Footwear",
        "cost": "60.00", "stock": 36, "sizes": "37, 38, 39, 40, 41, 42",
        "colors": "White and Black, Brown and Black", "code": "1619-2",
    },
    {
        "name": "Women's Cross-Strap Sandals Model M2601-2", "category": "Shoes & Footwear",
        "cost": "40.00", "stock": 36, "sizes": "36, 37, 38, 39, 40, 41",
        "colors": "White, Cream, Brown, Black", "code": "m2601-2",
    },
    {
        "name": "Women's Double-Buckle Slides Model 1818-15", "category": "Shoes & Footwear",
        "cost": "60.00", "stock": 36, "sizes": "37, 38, 39, 40, 41, 42",
        "colors": "Navy, Brown, White", "code": "1818-15",
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
    dependencies = [("core", "0044_seed_local_clothing_and_sandals")]

    operations = [migrations.RunPython(seed_products, migrations.RunPython.noop)]
