from django.conf import settings

from core.models import Category
from core.views import get_user_cart, is_approved_supplier


def site_chrome(request):
    categories = Category.objects.all().order_by("name")
    cart_count = 0
    if request.user.is_authenticated:
        cart_count = get_user_cart(request.user).total_items()
    return {
        "google_oauth_enabled": getattr(settings, "GOOGLE_OAUTH_ENABLED", False),
        "nav_categories": categories,
        "nav_cart_count": cart_count,
        "is_approved_supplier": is_approved_supplier(request.user),
    }
