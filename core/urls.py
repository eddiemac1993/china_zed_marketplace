from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

urlpatterns = [
    # Home
    path("", views.home, name="home"),

    # Auth
    path("register/", views.register_view, name="register"),
    path("login/", auth_views.LoginView.as_view(template_name="core/login.html"), name="login"),
    path("logout/", views.logout_view, name="logout"),

    # Profile
    path("profile/", views.profile_view, name="profile"),

    # Products (UPDATED → use slug instead of ID)
    path("product/<slug:slug>/", views.product_detail, name="product_detail"),
    path("product/<slug:slug>/order/", views.place_order_view, name="place_order"),

    # Supplier
    path("supplier/submit-product/", views.supplier_submit_product, name="supplier_submit_product"),

    # Orders
    path("order/<int:order_id>/", views.order_detail_view, name="order_detail"),
    path("order/<int:order_id>/receipt/", views.receipt_view, name="receipt"),
    path("order/<int:order_id>/receipt/pdf/", views.receipt_pdf_view, name="receipt_pdf"),

    # Policy
    path("order-policy/", views.order_policy, name="order_policy"),
]