from .models import ExchangeRate, SupplierProductRequestImage, Category, Product, ProductImage, Order, SupplierProductRequest
from django.contrib import admin, messages

from .models import (
    ExchangeRate,
    Category,
    Product,
    ProductImage,
    Cart,
    CartItem,
    Order,
    OrderItem,
    SupplierProductRequest,
    SupplierProductRequestImage,
)


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 3


class SupplierProductRequestImageInline(admin.TabularInline):
    model = SupplierProductRequestImage
    extra = 4


class CartItemInline(admin.TabularInline):
    model = CartItem
    extra = 0
    readonly_fields = ("line_total",)


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = (
        "product_name",
        "unit_price",
        "line_total",
        "product_type",
    )


@admin.register(ExchangeRate)
class ExchangeRateAdmin(admin.ModelAdmin):
    list_display = (
        "rmb_to_zmw",
        "markup_percentage",
        "is_active",
        "updated_at",
    )
    list_filter = ("is_active",)


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "category",
        "product_type",
        "stock_quantity",
        "source_platform",
        "supplier_name",
        "rmb_price",
        "is_available",
        "is_featured",
        "created_at",
    )

    list_filter = (
        "category",
        "product_type",
        "source_platform",
        "is_available",
        "is_featured",
    )

    search_fields = (
        "name",
        "description",
        "supplier_name",
        "supplier_contact",
        "source_link",
    )

    prepopulated_fields = {"slug": ("name",)}
    inlines = [ProductImageInline]


@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "total_items",
        "total_price",
        "deposit_amount",
        "balance_amount",
        "updated_at",
    )
    search_fields = ("user__username", "user__email")
    inlines = [CartItemInline]


@admin.action(description="Confirm selected orders and reduce local stock")
def confirm_orders_and_reduce_stock(modeladmin, request, queryset):
    success_count = 0
    error_count = 0

    for order in queryset:
        try:
            if order.status != "confirmed":
                order.status = "confirmed"
                order.save()

            order.reduce_local_stock()
            success_count += 1

        except ValueError as e:
            error_count += 1
            messages.error(request, f"Order #{order.id}: {e}")

    if success_count:
        messages.success(
            request,
            f"{success_count} order(s) confirmed and local stock reduced."
        )

    if error_count:
        messages.warning(
            request,
            f"{error_count} order(s) could not be confirmed due to stock issues."
        )


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "order_products",
        "status",
        "deposit_confirmed",
        "balance_paid",
        "stock_reduced",
        "total_price",
        "order_date",
    )

    list_editable = (
        "status",
        "deposit_confirmed",
        "balance_paid",
    )

    list_filter = (
        "status",
        "deposit_confirmed",
        "balance_paid",
        "stock_reduced",
        "order_date",
    )

    search_fields = (
        "user__username",
        "user__email",
        "customer_phone",
        "receipt_number",
        "items__product_name",
    )

    readonly_fields = (
        "total_price",
        "deposit_amount",
        "balance_amount",
        "exchange_rate_used",
        "markup_used",
        "stock_reduced",
        "order_date",
    )

    actions = [confirm_orders_and_reduce_stock]
    inlines = [OrderItemInline]

    def order_products(self, obj):
        items = obj.items.all()

        if not items:
            return "No items"

        return ", ".join(
            f"{item.quantity} x {item.product_name}"
            for item in items
        )

    order_products.short_description = "Products"


@admin.action(description="Approve selected requests and create products")
def approve_supplier_requests(modeladmin, request, queryset):
    default_category = Category.objects.first()
    created_count = 0

    for supplier_request in queryset:
        if supplier_request.is_approved:
            continue

        product = Product.objects.create(
            name=supplier_request.product_name,
            description=supplier_request.description,
            rmb_price=supplier_request.rmb_price,
            category=default_category,
            product_type="preorder",
            stock_quantity=0,
            source_platform="other",
            source_link="",
            supplier_name=supplier_request.supplier_name,
            supplier_contact=supplier_request.supplier_contact,
            is_available=True,
            is_featured=True,
        )

        images = SupplierProductRequestImage.objects.filter(
            supplier_request=supplier_request
        )

        for img in images:
            ProductImage.objects.create(
                product=product,
                image=img.image
            )

        if images.exists():
            product.image = images.first().image
            product.save()

        supplier_request.is_reviewed = True
        supplier_request.is_approved = True
        supplier_request.admin_note = "Approved and images moved to product."
        supplier_request.save()

        created_count += 1

    messages.success(
        request,
        f"{created_count} supplier request(s) approved and converted to products."
    )


@admin.register(SupplierProductRequest)
class SupplierProductRequestAdmin(admin.ModelAdmin):
    list_display = (
        "product_name",
        "supplier_name",
        "source_platform",
        "rmb_price",
        "is_reviewed",
        "is_approved",
        "submitted_at",
    )

    list_filter = (
        "source_platform",
        "is_reviewed",
        "is_approved",
    )

    search_fields = (
        "product_name",
        "supplier_name",
        "supplier_contact",
        "source_link",
    )

    actions = [approve_supplier_requests]
    inlines = [SupplierProductRequestImageInline]