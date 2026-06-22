from django.contrib import admin
from .models import PriceList, PriceListItem


class PriceListItemInline(admin.TabularInline):
    model = PriceListItem
    extra = 1


@admin.register(PriceList)
class PriceListAdmin(admin.ModelAdmin):
    list_display = ("title", "client_name", "reference_no", "date", "total_amount")
    search_fields = ("title", "client_name", "reference_no")
    list_filter = ("date",)
    inlines = [PriceListItemInline]


@admin.register(PriceListItem)
class PriceListItemAdmin(admin.ModelAdmin):
    list_display = ("item_name", "quantity", "unit_price", "where_to_buy", "total_price")
    search_fields = ("item_name", "where_to_buy")