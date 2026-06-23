from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

urlpatterns = [
    # Home
    path("", views.home, name="home"),
    path("about/", views.about, name="about"),
    path("terms/", views.terms, name="terms"),
    path("privacy/", views.privacy, name="privacy"),

    # Auth
    path("register/", views.register_view, name="register"),
    path("register/check-email/", views.registration_pending_view, name="registration_pending"),
    path("activate/<uidb64>/<token>/", views.activate_account_view, name="activate_account"),
    path("login/", auth_views.LoginView.as_view(template_name="core/login.html"), name="login"),
    path("logout/", views.logout_view, name="logout"),

    # Profile
    path("profile/", views.profile_view, name="profile"),

    # Products
    path("product/<slug:slug>/", views.product_detail, name="product_detail"),
    path("product/<slug:slug>/order/", views.place_order_view, name="place_order"),

    # =========================
    # CART SYSTEM
    # =========================

    # View cart
    path("cart/", views.cart_view, name="cart"),

    # Add to cart
    path("cart/add/<slug:slug>/", views.add_to_cart_view, name="add_to_cart"),

    # Update quantity (increase/decrease)
    path("cart/update/<int:item_id>/", views.update_cart_item_view, name="update_cart_item"),

    # Remove item
    path("cart/remove/<int:item_id>/", views.remove_cart_item_view, name="remove_cart_item"),

    # Clear entire cart
    path("cart/clear/", views.clear_cart_view, name="clear_cart"),

    # Checkout cart → create order
    path("cart/checkout/", views.checkout_cart_view, name="checkout_cart"),

    # =========================
    # ORDERS
    # =========================

    path("order/<int:order_id>/", views.order_detail_view, name="order_detail"),
    path("order/<int:order_id>/receipt/", views.receipt_view, name="receipt"),
    path("order/<int:order_id>/receipt/pdf/", views.receipt_pdf_view, name="receipt_pdf"),

    # =========================
    # SUPPLIER
    # =========================

    path("supplier/submit-product/", views.supplier_submit_product, name="supplier_submit_product"),

    # =========================
    # POLICY
    # =========================

    path("order-policy/", views.order_policy, name="order_policy"),

    path(
        "order/<int:order_id>/upload-payment-proof/",
        views.upload_payment_proof_view,
        name="upload_payment_proof"
    ),

    path(
        "product/<slug:slug>/save-image/",
        views.save_product_image_view,
        name="save_product_image"
    ),
]
