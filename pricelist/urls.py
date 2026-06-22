from django.urls import path
from . import views

app_name = "pricelist"

urlpatterns = [
    path("", views.price_list_index, name="index"),
    path("<int:pk>/", views.price_list_view, name="detail"),
]