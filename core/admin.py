from django.contrib import admin, messages
from django.utils.html import format_html

from .models import (
    ExchangeRate,
    Category,
    Product,
    ProductImage,
    Cart,
    CartItem,
    Order,
    OrderItem,
    CustomerProductRequest,
    SupplierProductRequest,
    SupplierProductRequestImage,
    Advertisement,
    StockMovement,
    ProductReview,
)


# =========================
# INLINE ADMINS
# =========================

class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 1
    fields = ("image", "caption", "image_preview")
    readonly_fields = ("image_preview",)

    def image_preview(self, obj):
        if obj and obj.image:
            return format_html(
                '<img src="{}" style="width:90px;height:70px;object-fit:cover;border-radius:8px;" />',
                obj.image.url,
            )
        return "No image"


class SupplierProductRequestImageInline(admin.TabularInline):
    model = SupplierProductRequestImage
    extra = 1
    fields = ("image", "caption", "image_preview")
    readonly_fields = ("image_preview",)

    def image_preview(self, obj):
        if obj and obj.image:
            return format_html(
                '<img src="{}" style="width:90px;height:70px;object-fit:cover;border-radius:8px;" />',
                obj.image.url,
            )
        return "No image"


class CartItemInline(admin.TabularInline):
    model = CartItem
    extra = 0
    readonly_fields = ("line_total_display",)

    def line_total_display(self, obj):
        if not obj or not obj.pk:
            return "Save first"
        return f"K{obj.line_total()}"

    line_total_display.short_description = "Line Total"


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = (
        "product_name",
        "unit_price",
        "line_total",
        "product_type",
        "created_at",
    )


class StockMovementInline(admin.TabularInline):
    model = StockMovement
    extra = 0
    readonly_fields = ("created_at", "updated_at")
    fields = ("movement_type", "quantity", "note", "created_by", "created_at")


# =========================
# EXCHANGE RATE
# =========================

@admin.register(ExchangeRate)
class ExchangeRateAdmin(admin.ModelAdmin):
    list_display = (
        "rmb_to_zmw",
        "markup_percentage",
        "local_markup_percentage",
        "deposit_percentage",
        "is_active",
        "updated_at",
    )
    list_filter = ("is_active", "is_deleted")
    list_editable = ("is_active",)
    readonly_fields = ("created_at", "updated_at")
    ordering = ("-updated_at",)


# =========================
# CATEGORY
# =========================

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "created_at", "updated_at")
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}
    readonly_fields = ("created_at", "updated_at")
    list_filter = ("is_deleted",)


# =========================
# PRODUCT
# =========================

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = (
        "image_preview_small",
        "name",
        "sku",
        "category",
        "product_type",
        "status",
        "stock_quantity",
        "selling_price_display",
        "deposit_display",
        "source_platform",
        "is_available",
        "is_featured",
        "created_at",
    )

    list_editable = (
        "status",
        "stock_quantity",
        "is_available",
        "is_featured",
    )

    list_filter = (
        "category",
        "product_type",
        "status",
        "source_platform",
        "is_available",
        "is_featured",
        "is_deleted",
    )

    search_fields = (
        "name",
        "sku",
        "slug",
        "description",
        "supplier_name",
        "supplier_contact",
        "source_link",
    )

    readonly_fields = (
        "uuid",
        "created_at",
        "updated_at",
        "views_count",
        "selling_price_display",
        "deposit_display",
        "balance_display",
        "image_preview_large",
    )

    prepopulated_fields = {"slug": ("name",)}
    inlines = [ProductImageInline, StockMovementInline]

    fieldsets = (
        ("Basic Product Details", {
            "fields": (
                "uuid",
                "sku",
                "name",
                "slug",
                "category",
                "description",
                "image",
                "image_preview_large",
            )
        }),
        ("Pricing", {
            "fields": (
                "rmb_price",
                "selling_price_display",
                "deposit_display",
                "balance_display",
            )
        }),
        ("Product Type & Stock", {
            "fields": (
                "product_type",
                "status",
                "stock_quantity",
                "is_available",
                "is_featured",
            )
        }),
        ("Delivery", {
            "fields": (
                "delivery_min_days",
                "delivery_max_days",
            )
        }),
        ("Supplier / Source", {
            "fields": (
                "source_platform",
                "source_link",
                "supplier_name",
                "supplier_contact",
                "supplier_note",
            )
        }),
        ("System Info", {
            "fields": (
                "views_count",
                "is_deleted",
                "created_at",
                "updated_at",
            )
        }),
    )

    def image_preview_small(self, obj):
        if obj and obj.image:
            return format_html(
                '<img src="{}" style="width:50px;height:50px;object-fit:cover;border-radius:8px;" />',
                obj.image.url,
            )
        return "No image"

    image_preview_small.short_description = "Image"

    def image_preview_large(self, obj):
        if obj and obj.image:
            return format_html(
                '<img src="{}" style="max-width:320px;max-height:320px;object-fit:cover;border-radius:12px;border:1px solid #ddd;" />',
                obj.image.url,
            )
        return "No image uploaded"

    image_preview_large.short_description = "Image Preview"

    def selling_price_display(self, obj):
        if not obj or not obj.pk or obj.rmb_price is None:
            return "Save product first"
        return f"K{obj.selling_price()}"

    selling_price_display.short_description = "Selling Price"

    def deposit_display(self, obj):
        if not obj or not obj.pk or obj.rmb_price is None:
            return "Save product first"
        return f"K{obj.deposit_amount()}"

    deposit_display.short_description = "Deposit"

    def balance_display(self, obj):
        if not obj or not obj.pk or obj.rmb_price is None:
            return "Save product first"
        return f"K{obj.balance_amount()}"

    balance_display.short_description = "Balance"


# =========================
# CART
# =========================

@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "total_items",
        "total_price_display",
        "deposit_display",
        "balance_display",
        "updated_at",
    )
    search_fields = ("user__username", "user__email")
    readonly_fields = ("created_at", "updated_at")
    inlines = [CartItemInline]

    def total_price_display(self, obj):
        if not obj or not obj.pk:
            return "Save first"
        return f"K{obj.total_price()}"

    def deposit_display(self, obj):
        if not obj or not obj.pk:
            return "Save first"
        return f"K{obj.deposit_amount()}"

    def balance_display(self, obj):
        if not obj or not obj.pk:
            return "Save first"
        return f"K{obj.balance_amount()}"


# =========================
# ORDER ACTIONS
# =========================

@admin.action(description="Confirm selected orders and reduce local stock")
def confirm_orders_and_reduce_stock(modeladmin, request, queryset):
    success_count = 0
    error_count = 0

    for order in queryset:
        try:
            order.status = "confirmed"
            order.save()
            order.reduce_local_stock()
            success_count += 1
        except ValueError as e:
            error_count += 1
            messages.error(request, f"{order.tracking_code}: {e}")

    if success_count:
        messages.success(request, f"{success_count} order(s) confirmed and stock reduced.")

    if error_count:
        messages.warning(request, f"{error_count} order(s) had stock issues.")


@admin.action(description="Mark selected orders as arrived")
def mark_orders_arrived(modeladmin, request, queryset):
    count = 0

    for order in queryset:
        order.status = "arrived"
        order.save()
        count += 1

    messages.success(request, f"{count} order(s) marked as arrived.")


@admin.action(description="Mark selected orders as successful")
def mark_orders_successful(modeladmin, request, queryset):
    updated = queryset.update(status="successful")
    messages.success(request, f"{updated} order(s) marked as successful.")


# =========================
# ORDER
# =========================

@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = (
        "tracking_code",
        "user",
        "order_products",
        "status",
        "deposit_confirmed",
        "balance_paid",
        "stock_reduced",
        "total_price",
        "amount_paid_display",
        "amount_remaining_display",
        "payment_proof_status",
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
        "is_deleted",
    )

    search_fields = (
        "tracking_code",
        "receipt_number",
        "user__username",
        "user__email",
        "customer_phone",
        "items__product_name",
    )

    readonly_fields = (
        "uuid",
        "tracking_code",
        "total_price",
        "deposit_amount",
        "balance_amount",
        "exchange_rate_used",
        "markup_used",
        "deposit_percentage_used",
        "stock_reduced",
        "order_date",
        "created_at",
        "updated_at",
        "payment_proof_preview",
        "payment_proof_uploaded_at",
        "amount_paid_display",
        "amount_remaining_display",
        "progress_display",
    )

    fieldsets = (
        ("Customer", {
            "fields": (
                "uuid",
                "tracking_code",
                "user",
                "customer_phone",
                "customer_note",
            )
        }),
        ("Order Status", {
            "fields": (
                "status",
                "progress_display",
                "deposit_confirmed",
                "balance_paid",
                "stock_reduced",
            )
        }),
        ("Money", {
            "fields": (
                "total_price",
                "deposit_amount",
                "balance_amount",
                "amount_paid_display",
                "amount_remaining_display",
            )
        }),
        ("Payment Proof", {
            "fields": (
                "payment_proof",
                "payment_proof_preview",
                "payment_proof_uploaded_at",
                "payment_note",
            )
        }),
        ("Pricing Conditions Used", {
            "fields": (
                "exchange_rate_used",
                "markup_used",
                "deposit_percentage_used",
            )
        }),
        ("Delivery Tracking", {
            "fields": (
                "estimated_arrival_start",
                "estimated_arrival_end",
                "arrival_date",
            )
        }),
        ("Receipt & System", {
            "fields": (
                "receipt_number",
                "is_deleted",
                "order_date",
                "created_at",
                "updated_at",
            )
        }),
    )

    actions = [
        confirm_orders_and_reduce_stock,
        mark_orders_arrived,
        mark_orders_successful,
    ]

    inlines = [OrderItemInline]

    def order_products(self, obj):
        if not obj or not obj.pk:
            return "No items"

        items = obj.items.all()

        if not items:
            return "No items"

        return ", ".join(f"{item.quantity} x {item.product_name}" for item in items)

    order_products.short_description = "Products"

    def payment_proof_status(self, obj):
        if obj and obj.payment_proof:
            return "Uploaded"
        return "Not uploaded"

    payment_proof_status.short_description = "Proof"

    def payment_proof_preview(self, obj):
        if obj and obj.payment_proof:
            return format_html(
                '<a href="{}" target="_blank">'
                '<img src="{}" style="max-width:320px;max-height:320px;border-radius:12px;border:1px solid #ddd;" />'
                "</a>",
                obj.payment_proof.url,
                obj.payment_proof.url,
            )
        return "No payment proof uploaded"

    payment_proof_preview.short_description = "Payment Proof Preview"

    def amount_paid_display(self, obj):
        if not obj or not obj.pk:
            return "Save first"
        return f"K{obj.amount_paid()}"

    amount_paid_display.short_description = "Amount Paid"

    def amount_remaining_display(self, obj):
        if not obj or not obj.pk:
            return "Save first"
        return f"K{obj.amount_remaining()}"

    amount_remaining_display.short_description = "Remaining"

    def progress_display(self, obj):
        if not obj or not obj.pk:
            return "Save first"
        return f"{obj.progress_percentage()}%"

    progress_display.short_description = "Progress"


# =========================
# SUPPLIER REQUEST ACTION
# =========================

@admin.action(description="Approve selected supplier requests and create products")
def approve_supplier_requests(modeladmin, request, queryset):
    created_count = 0
    skipped_count = 0

    for supplier_request in queryset:
        if supplier_request.is_approved:
            skipped_count += 1
            continue

        product_price = (
            supplier_request.local_price
            if supplier_request.product_type == "local"
            else supplier_request.rmb_price
        )

        stock_quantity = (
            supplier_request.stock_quantity
            if supplier_request.product_type == "local"
            else 0
        )

        if not product_price:
            messages.error(request, f"{supplier_request.product_name} was skipped: missing price.")
            continue

        if supplier_request.product_type == "local" and stock_quantity <= 0:
            messages.error(request, f"{supplier_request.product_name} was skipped: missing stock quantity.")
            continue

        product = Product.objects.create(
            name=supplier_request.product_name,
            description=supplier_request.description,
            rmb_price=product_price,
            category=supplier_request.category,
            product_type=supplier_request.product_type,
            stock_quantity=stock_quantity,
            source_platform=supplier_request.source_platform,
            source_link=supplier_request.source_link,
            supplier_name=supplier_request.supplier_name,
            supplier_contact=supplier_request.supplier_contact,
            status="active",
            is_available=True,
            is_featured=True,
        )

        images = supplier_request.images.all()

        for img in images:
            ProductImage.objects.create(
                product=product,
                image=img.image,
                caption=img.caption,
            )

        if images.exists():
            product.image = images.first().image
            product.save()

        supplier_request.is_reviewed = True
        supplier_request.is_approved = True
        supplier_request.admin_note = "Approved and converted to product."
        supplier_request.save()

        created_count += 1

    messages.success(
        request,
        f"{created_count} request(s) converted to products. {skipped_count} already approved."
    )


# =========================
# SUPPLIER REQUEST
# =========================

@admin.register(SupplierProductRequest)
class SupplierProductRequestAdmin(admin.ModelAdmin):
    list_display = (
        "image_preview_small",
        "product_name",
        "supplier_name",
        "product_type",
        "source_platform",
        "price_display",
        "stock_quantity",
        "is_reviewed",
        "is_approved",
        "created_at",
    )

    list_editable = (
        "is_reviewed",
        "is_approved",
    )

    list_filter = (
        "product_type",
        "source_platform",
        "is_reviewed",
        "is_approved",
        "is_deleted",
    )

    search_fields = (
        "product_name",
        "supplier_name",
        "supplier_contact",
        "source_link",
        "description",
    )

    readonly_fields = (
        "uuid",
        "created_at",
        "updated_at",
        "image_preview_large",
    )

    fieldsets = (
        ("Supplier", {
            "fields": (
                "uuid",
                "supplier_name",
                "supplier_contact",
            )
        }),
        ("Product Request", {
            "fields": (
                "product_name",
                "description",
                "product_type",
                "category",
                "stock_quantity",
                "image",
                "image_preview_large",
            )
        }),
        ("Source & Price", {
            "fields": (
                "source_platform",
                "source_link",
                "rmb_price",
                "local_price",
            )
        }),
        ("Review", {
            "fields": (
                "is_reviewed",
                "is_approved",
                "admin_note",
            )
        }),
        ("System", {
            "fields": (
                "is_deleted",
                "created_at",
                "updated_at",
            )
        }),
    )

    actions = [approve_supplier_requests]
    inlines = [SupplierProductRequestImageInline]

    def image_preview_small(self, obj):
        if obj and obj.image:
            return format_html(
                '<img src="{}" style="width:50px;height:50px;object-fit:cover;border-radius:8px;" />',
                obj.image.url,
            )
        return "No image"

    image_preview_small.short_description = "Image"

    def image_preview_large(self, obj):
        if obj and obj.image:
            return format_html(
                '<img src="{}" style="max-width:320px;max-height:320px;object-fit:cover;border-radius:12px;border:1px solid #ddd;" />',
                obj.image.url,
            )
        return "No image uploaded"

    image_preview_large.short_description = "Image Preview"

    def price_display(self, obj):
        if not obj:
            return "-"
        return obj.display_price()

    price_display.short_description = "Price"


@admin.register(CustomerProductRequest)
class CustomerProductRequestAdmin(admin.ModelAdmin):
    list_display = (
        "product_label",
        "user",
        "source_platform",
        "status",
        "quoted_price",
        "created_at",
    )
    list_editable = ("status", "quoted_price")
    list_filter = ("status", "source_platform", "created_at", "is_deleted")
    search_fields = ("product_name", "product_link", "notes", "user__username", "user__email")
    readonly_fields = ("created_at", "updated_at", "screenshot_preview")
    fieldsets = (
        ("Customer", {
            "fields": ("user",)
        }),
        ("Request", {
            "fields": ("product_name", "product_link", "source_platform", "notes", "screenshot", "screenshot_preview")
        }),
        ("Admin Review", {
            "fields": ("status", "quoted_price", "admin_note")
        }),
        ("System", {
            "fields": ("is_deleted", "created_at", "updated_at")
        }),
    )

    def product_label(self, obj):
        return obj.product_name or obj.product_link

    product_label.short_description = "Product"

    def screenshot_preview(self, obj):
        if obj and obj.screenshot:
            return format_html(
                '<a href="{}" target="_blank"><img src="{}" style="max-width:320px;max-height:220px;object-fit:cover;border-radius:10px;border:1px solid #ddd;" /></a>',
                obj.screenshot.url,
                obj.screenshot.url,
            )
        return "No screenshot"

    screenshot_preview.short_description = "Screenshot Preview"


# =========================
# STOCK MOVEMENT
# =========================

@admin.register(StockMovement)
class StockMovementAdmin(admin.ModelAdmin):
    list_display = (
        "product",
        "movement_type",
        "quantity",
        "created_by",
        "created_at",
    )
    list_filter = ("movement_type", "created_at", "is_deleted")
    search_fields = ("product__name", "product__sku", "note")
    readonly_fields = ("created_at", "updated_at")


# =========================
# PRODUCT REVIEW
# =========================

@admin.register(ProductReview)
class ProductReviewAdmin(admin.ModelAdmin):
    list_display = (
        "product",
        "user",
        "rating",
        "is_approved",
        "created_at",
    )
    list_filter = ("rating", "is_approved", "created_at", "is_deleted")
    list_editable = ("is_approved",)
    search_fields = ("product__name", "user__username", "comment")
    readonly_fields = ("created_at", "updated_at")


# =========================
# ADVERTISEMENT
# =========================

@admin.register(Advertisement)
class AdvertisementAdmin(admin.ModelAdmin):
    list_display = (
        "image_preview_small",
        "advertiser_name",
        "headline",
        "hour_slot",
        "display_from",
        "display_until",
        "is_active",
        "currently_active_display",
        "created_at",
    )

    list_editable = ("is_active",)

    list_filter = (
        "hour_slot",
        "is_active",
        "display_from",
        "display_until",
        "is_deleted",
    )

    search_fields = (
        "advertiser_name",
        "headline",
        "subtext",
        "cta_url",
    )

    readonly_fields = (
        "created_at",
        "updated_at",
        "image_preview_large",
        "currently_active_display",
    )

    fieldsets = (
        ("Advertiser", {
            "fields": (
                "advertiser_name",
                "headline",
                "subtext",
                "image",
                "image_preview_large",
            )
        }),
        ("Call To Action", {
            "fields": (
                "cta_text",
                "cta_url",
            )
        }),
        ("Schedule", {
            "fields": (
                "hour_slot",
                "display_from",
                "display_until",
                "is_active",
                "currently_active_display",
            )
        }),
        ("System", {
            "fields": (
                "is_deleted",
                "created_at",
                "updated_at",
            )
        }),
    )

    def image_preview_small(self, obj):
        if obj and obj.image:
            return format_html(
                '<img src="{}" style="width:60px;height:40px;object-fit:cover;border-radius:6px;" />',
                obj.image.url,
            )
        return "No image"

    image_preview_small.short_description = "Image"

    def image_preview_large(self, obj):
        if obj and obj.image:
            return format_html(
                '<img src="{}" style="max-width:420px;max-height:240px;object-fit:cover;border-radius:12px;border:1px solid #ddd;" />',
                obj.image.url,
            )
        return "No image uploaded"

    image_preview_large.short_description = "Image Preview"

    def currently_active_display(self, obj):
        if not obj or not obj.pk:
            return "Save first"

        if obj.is_currently_active():
            return "Yes"

        return "No"

    currently_active_display.short_description = "Currently Active"


admin.site.index_template = "admin/core_index.html"
_default_admin_index = admin.site.index


def chinazed_admin_index(request, extra_context=None):
    extra_context = extra_context or {}
    extra_context["chinazed_dashboard"] = {
        "pending_orders": Order.objects.filter(status="pending").count(),
        "unpaid_deposits": Order.objects.filter(deposit_confirmed=False).count(),
        "payment_proofs": Order.objects.filter(payment_proof__isnull=False, deposit_confirmed=False).count(),
        "product_requests": CustomerProductRequest.objects.filter(status="new").count(),
        "delayed_orders": sum(1 for order in Order.objects.all() if order.is_delayed()),
    }
    return _default_admin_index(request, extra_context)


admin.site.index = chinazed_admin_index
