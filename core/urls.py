from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

urlpatterns = [
    path("", views.home, name="home"),

    path("register/", views.register_view, name="register"),
    path("login/", auth_views.LoginView.as_view(template_name="core/login.html"), name="login"),
    path("logout/", views.logout_view, name="logout"),

    path("profile/", views.profile_view, name="profile"),

    path("product/<int:product_id>/", views.product_detail, name="product_detail"),
    path("product/<int:product_id>/order/", views.place_order_view, name="place_order"),

    path("supplier/submit-product/", views.supplier_submit_product, name="supplier_submit_product"),
    path("order/<int:order_id>/receipt/pdf/", views.receipt_pdf_view, name="receipt_pdf"),
    path("order/<int:order_id>/receipt/", views.receipt_view, name="receipt"),
    path("order-policy/", views.order_policy, name="order_policy"),
    path("order/<int:order_id>/", views.order_detail_view, name="order_detail"),
]