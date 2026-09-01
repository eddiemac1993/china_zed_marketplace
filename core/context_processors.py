from django.conf import settings

from core.models import Category
from core.views import get_user_cart, is_approved_supplier


def site_chrome(request):
    categories = Category.objects.all().order_by("name")
    cart_count = 0
    saved_product_ids = []
    if request.user.is_authenticated:
        cart_count = get_user_cart(request.user).total_items()
        saved_product_ids = list(request.user.wishlist_items.values_list("product_id", flat=True))
    return {
        "google_oauth_enabled": getattr(settings, "GOOGLE_OAUTH_ENABLED", False),
        "nav_categories": categories,
        "nav_cart_count": cart_count,
        "nav_saved_count": len(saved_product_ids),
        "saved_product_ids": saved_product_ids,
        "is_approved_supplier": is_approved_supplier(request.user),
    }
