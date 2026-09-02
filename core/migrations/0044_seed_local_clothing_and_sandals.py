from decimal import Decimal

from django.db import migrations


PRODUCTS = [
    {
        "name": "Plain T-Shirt Model W-001",
        "description": "Plain crew-neck short-sleeve T-shirt available in black, dark green and maroon. Sizes M to XXL.",
        "category": "Fashion & Clothing",
        "cost": "35.00",
        "stock": 12,
        "sizes": "M, L, XL, XXL",
        "colors": "Black, Dark Green, Maroon",
        "image": "products/customer/w001-clean.png",
        "sku": "LOC-W001-SEED",
        "slug": "plain-t-shirt-model-w-001",
    },
    {
        "name": "Plain T-Shirt Model M-013",
        "description": "Plain crew-neck short-sleeve T-shirt available in black and white. Sizes M to XXL.",
        "category": "Fashion & Clothing",
        "cost": "48.00",
        "stock": 1,
        "sizes": "M, L, XL, XXL",
        "colors": "Black, White",
        "image": "products/customer/m013-clean.png",
        "sku": "LOC-M013-SEED",
        "slug": "plain-t-shirt-model-m-013",
    },
    {
        "name": "Women’s Sandals Model G-77",
        "description": "Strappy women’s flat sandals available in white, black, cream and brown. Sizes 37 to 42.",
        "category": "Shoes & Footwear",
        "cost": "70.00",
        "stock": 36,
        "sizes": "37, 38, 39, 40, 41, 42",
        "colors": "White, Black, Cream, Brown",
        "image": "products/customer/g77-clean.png",
        "sku": "LOC-G77-SEED",
        "slug": "womens-sandals-model-g-77",
    },
    {
        "name": "Women’s T-Shirt Model W-008",
        "description": "Women’s short-sleeve printed T-shirt available in black, white and red. Sizes M to 2XL.",
        "category": "Fashion & Clothing",
        "cost": "38.00",
        "stock": 12,
        "sizes": "M, L, XL, 2XL",
        "colors": "Black, White, Red",
        "image": "products/customer/w008-clean.png",
        "sku": "LOC-W008-SEED",
        "slug": "womens-t-shirt-model-w-008",
    },
    {
        "name": "Women’s Joggers Model W-002",
        "description": "Comfortable grey drawstring jogger pants with pockets and elastic cuffs. Sizes M to 4XL.",
        "category": "Fashion & Clothing",
        "cost": "70.00",
        "stock": 1,
        "sizes": "M, L, XL, 2XL, 3XL, 4XL",
        "colors": "Grey",
        "image": "products/customer/w002-clean.png",
        "sku": "LOC-W002-SEED",
        "slug": "womens-joggers-model-w-002",
    },
]


def seed_products(apps, schema_editor):
    Product = apps.get_model("core", "Product")
    Category = apps.get_model("core", "Category")
    for item in PRODUCTS:
        category_slug = item["category"].lower().replace("&", "and").replace(" ", "-")
        category, _ = Category.objects.get_or_create(
            name=item["category"], defaults={"slug": category_slug}
        )
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
            Product.objects.create(
                name=item["name"], sku=item["sku"], slug=item["slug"], **values
            )


class Migration(migrations.Migration):
    dependencies = [("core", "0043_set_local_delivery_window")]

    operations = [migrations.RunPython(seed_products, migrations.RunPython.noop)]
