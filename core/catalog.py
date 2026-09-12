from django.db.models import Q
from .models import Product


def homepage_products():
    """One visibility rule for every customer-facing homepage product feed."""
    return Product.objects.filter(
        Q(product_type="local", stock_quantity__gt=0)
        | (Q(product_type="preorder") & (Q(available_quantity__isnull=True) | Q(available_quantity__gt=0))),
        show_on_homepage=True,
        is_available=True,
        status="active",
        is_deleted=False,
    )
