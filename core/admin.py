from django.contrib import admin, messages
from .models import ExchangeRate, SupplierProductRequestImage, Category, Product, ProductImage, Order, SupplierProductRequest


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 3

class SupplierProductRequestImageInline(admin.TabularInline):
    model = SupplierProductRequestImage
    extra = 4

@admin.register(ExchangeRate)
class ExchangeRateAdmin(admin.ModelAdmin):
    list_display = ("rmb_to_zmw", "markup_percentage", "updated_at")


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name",)


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "category",
        "source_platform",
        "supplier_name",
        "rmb_price",
        "is_available",
        "is_featured",
        "created_at",
    )

    list_filter = (
        "category",
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

    inlines = [ProductImageInline]


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "product",
        "status",
        "deposit_confirmed",
        "balance_paid",
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
        "order_date",
    )


from .models import ProductImage, SupplierProductRequestImage

@admin.action(description="Approve selected requests and create products")
def approve_supplier_requests(modeladmin, request, queryset):
    default_category = Category.objects.first()

    for supplier_request in queryset:
        if supplier_request.is_approved:
            continue

        # 1. Create product
        product = Product.objects.create(
            name=supplier_request.product_name,
            description=supplier_request.description,
            rmb_price=supplier_request.rmb_price,
            category=default_category,
            source_platform="other",  # default
            source_link="",           # empty
            supplier_name=supplier_request.supplier_name,
            supplier_contact=supplier_request.supplier_contact,
            is_available=True,
            is_featured=True,
        )

        # 2. Copy images from supplier request → product images
        images = SupplierProductRequestImage.objects.filter(
            supplier_request=supplier_request
        )

        for img in images:
            ProductImage.objects.create(
                product=product,
                image=img.image
            )

        # 3. OPTIONAL: set main image
        if images.exists():
            product.image = images.first().image
            product.save()

        # 4. mark request
        supplier_request.is_reviewed = True
        supplier_request.is_approved = True
        supplier_request.admin_note = "Approved and images moved to product."
        supplier_request.save()

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
    list_filter = ("source_platform", "is_reviewed", "is_approved")
    search_fields = ("product_name", "supplier_name", "supplier_contact", "source_link")
    actions = [approve_supplier_requests]
    inlines = [SupplierProductRequestImageInline]