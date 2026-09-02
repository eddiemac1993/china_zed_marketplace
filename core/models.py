from django.db import models
from django.conf import settings
from django.contrib.auth.models import User
from django.utils import timezone
from django.utils.text import slugify
from decimal import Decimal, ROUND_HALF_UP
from datetime import timedelta
import uuid
from urllib.parse import urlencode
from .storage import PrivateProductStorage

private_product_storage = PrivateProductStorage()

DEFAULT_DEPOSIT_PERCENTAGE = Decimal("35.00")
DEFAULT_COLLECTION_FEE_PERCENTAGE = Decimal("2.00")
DEFAULT_DIRECT_DELIVERY_FEE_PERCENTAGE = Decimal("5.00")

DELIVERY_METHOD_CHOICES = [
    ("collection", "Collect from a Centre"),
    ("direct", "Direct to Address"),
]


def money(value):
    return Decimal(value or 0).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def delivery_fee_percentage(delivery_method, rate=None):
    """Active % of order subtotal charged for the given delivery method."""
    if rate is None:
        rate = ExchangeRate.objects.filter(is_active=True, is_deleted=False).order_by("-updated_at").first()

    if delivery_method == "direct":
        return rate.direct_delivery_fee_percentage if rate else DEFAULT_DIRECT_DELIVERY_FEE_PERCENTAGE
    return rate.collection_fee_percentage if rate else DEFAULT_COLLECTION_FEE_PERCENTAGE


def calculate_delivery_fee(subtotal, delivery_method, rate=None):
    percentage = delivery_fee_percentage(delivery_method, rate=rate)
    return money(Decimal(subtotal or 0) * (percentage / Decimal("100"))), percentage


def calculate_biker_payout(delivery_fee, rate=None):
    if rate is None:
        rate = ExchangeRate.objects.filter(is_active=True, is_deleted=False).order_by("-updated_at").first()
    percentage = rate.biker_fee_share_percentage if rate else Decimal("70.00")
    return money(Decimal(delivery_fee or 0) * (percentage / Decimal("100"))), percentage


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_deleted = models.BooleanField(default=False)

    class Meta:
        abstract = True


class ExchangeRate(TimeStampedModel):
    rmb_to_zmw = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("3.20"))
    markup_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("35.00"))
    local_markup_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("80.00"))
    deposit_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=DEFAULT_DEPOSIT_PERCENTAGE)
    collection_fee_percentage = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal("2.00"),
        help_text="Delivery fee (% of order subtotal) when the customer collects from a centre.",
    )
    direct_delivery_fee_percentage = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal("5.00"),
        help_text="Delivery fee (% of order subtotal) when the order is delivered directly to the customer's address.",
    )
    biker_fee_share_percentage = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal("70.00"),
        help_text="Share of the delivery fee (%) paid out to the biker who completes a direct delivery.",
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self):
        return f"1 RMB = K{self.rmb_to_zmw} | Markup {self.markup_percentage}%"


class CollectionCentre(TimeStampedModel):
    name = models.CharField(max_length=150)
    town = models.CharField(max_length=100)
    address = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = "collection centre"
        verbose_name_plural = "collection centres"
        ordering = ["town", "name"]

    def __str__(self):
        return f"{self.name} ({self.town})"


class Biker(TimeStampedModel):
    VEHICLE_CHOICES = [
        ("motorbike", "Motorbike"),
        ("bicycle", "Bicycle"),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="biker_profile")
    full_name = models.CharField(max_length=150)
    phone = models.CharField(max_length=20)
    vehicle_type = models.CharField(max_length=20, choices=VEHICLE_CHOICES)
    home_centre = models.ForeignKey(CollectionCentre, on_delete=models.PROTECT, related_name="bikers")
    id_number = models.CharField(max_length=50, blank=True, help_text="National ID or driver's licence number, for vetting.")

    is_approved = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True, help_text="Bikers can be paused without losing their history.")
    approved_at = models.DateTimeField(blank=True, null=True)
    total_deliveries = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["-created_at"]

    def can_accept_jobs(self):
        return self.is_approved and self.is_active

    def __str__(self):
        return f"{self.full_name} ({self.get_vehicle_type_display()}) - {self.home_centre.name}"


class Category(TimeStampedModel):
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=120, unique=True, blank=True)

    class Meta:
        verbose_name_plural = "Categories"
        ordering = ["name"]

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class Product(TimeStampedModel):
    SOURCE_CHOICES = [
        ("aliexpress", "AliExpress"),
        ("taobao", "Taobao"),
        ("1688", "1688"),
        ("alibaba", "Alibaba"),
        ("wechat", "WeChat Supplier"),
        ("other", "Other"),
    ]

    PRODUCT_TYPE_CHOICES = [
        ("preorder", "Pre-order from China"),
        ("local", "Available in Zambia"),
    ]

    STATUS_CHOICES = [
        ("draft", "Draft"),
        ("active", "Active"),
        ("out_of_stock", "Out of Stock"),
        ("archived", "Archived"),
    ]

    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    sku = models.CharField(max_length=60, unique=True, blank=True)

    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=230, unique=True, blank=True)
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True)

    description = models.TextField()
    original_product_name = models.TextField(blank=True)
    original_description = models.TextField(blank=True)
    source_product_id = models.CharField(max_length=120, blank=True)
    source_currency = models.CharField(max_length=12, blank=True)
    displayed_price_min = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
    displayed_price_max = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
    original_displayed_price = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
    variant_data = models.JSONField(default=dict, blank=True)
    rmb_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        help_text="For local products, use this field as the buying/local cost price."
    )

    image = models.ImageField(upload_to="products/", blank=True, null=True)
    external_image_url = models.URLField(blank=True)
    external_gallery_urls = models.TextField(
        blank=True,
        help_text="One external product image URL per line.",
    )

    product_type = models.CharField(max_length=20, choices=PRODUCT_TYPE_CHOICES, default="preorder")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="active")

    stock_quantity = models.PositiveIntegerField(default=0)
    available_quantity = models.PositiveIntegerField(
        blank=True,
        null=True,
        help_text="Optional supplier availability for pre-order products.",
    )
    size_options = models.CharField(
        max_length=255,
        blank=True,
        help_text="Comma-separated sizes, for example: S, M, L, XL or 50 inch, 55 inch.",
    )
    color_options = models.CharField(
        max_length=255,
        blank=True,
        help_text="Comma-separated colors, for example: Black, White, Blue.",
    )

    is_available = models.BooleanField(default=True)
    is_featured = models.BooleanField(default=False)

    delivery_min_days = models.PositiveIntegerField(default=24)
    delivery_max_days = models.PositiveIntegerField(default=60)

    source_platform = models.CharField(max_length=20, choices=SOURCE_CHOICES, default="other")
    source_link = models.URLField(blank=True)
    imported_from_link = models.BooleanField(default=False, help_text="Imported from an external marketplace link.")

    supplier_name = models.CharField(max_length=150, blank=True)
    supplier_contact = models.CharField(max_length=100, blank=True)
    supplier_note = models.TextField(blank=True)

    views_count = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["slug"]),
            models.Index(fields=["product_type"]),
            models.Index(fields=["status"]),
            models.Index(fields=["created_at"]),
        ]

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.name)
            slug = base_slug
            counter = 1

            while Product.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1

            self.slug = slug

        if not self.sku:
            prefix = "LOC" if self.product_type == "local" else "CHN"
            self.sku = f"{prefix}-{uuid.uuid4().hex[:8].upper()}"

        if self.product_type == "local" and self.stock_quantity <= 0:
            self.status = "out_of_stock"

        if self.imported_from_link and self.product_type == "preorder":
            self.delivery_min_days = 14
            self.delivery_max_days = 60

        super().save(*args, **kwargs)

    @staticmethod
    def active_exchange_rate():
        return ExchangeRate.objects.filter(is_active=True, is_deleted=False).order_by("-updated_at").first()

    def kwacha_base_price(self):
        rate = self.active_exchange_rate()
        rmb_rate = rate.rmb_to_zmw if rate else Decimal("3.20")
        return money(self.rmb_price * rmb_rate)

    def selling_price(self):
        rate = self.active_exchange_rate()

        if self.product_type == "local":
            local_markup = rate.local_markup_percentage if rate else Decimal("80.00")
            final_price = Decimal(self.rmb_price) * (Decimal("1") + (local_markup / Decimal("100")))
            return money(final_price)

        markup = rate.markup_percentage if rate else Decimal("35.00")
        exchange_rate = rate.rmb_to_zmw if rate else Decimal("3.20")

        zmw_price = Decimal(self.rmb_price) * Decimal(exchange_rate)
        final_price = zmw_price * (Decimal("1") + (Decimal(markup) / Decimal("100")))

        return money(final_price)

    def deposit_amount(self):
        rate = self.active_exchange_rate()
        percentage = rate.deposit_percentage if rate else DEFAULT_DEPOSIT_PERCENTAGE
        return money(self.selling_price() * (percentage / Decimal("100")))

    def is_order_ready(self):
        """Return whether this listing has enough information to be purchased."""
        has_image = bool(self.display_image_url())
        has_core_details = bool(
            self.name.strip()
            and self.description.strip()
            and self.category_id
            and self.rmb_price
            and self.rmb_price > 0
            and has_image
        )
        if self.product_type == "local":
            return has_core_details and self.stock_quantity > 0
        return has_core_details

    def rmb_display(self):
        try:
            return int(round(float(self.rmb_price)))
        except (TypeError, ValueError):
            return None

    def current_rmb_rate(self):
        rate = self.active_exchange_rate()
        return rate.rmb_to_zmw if rate else Decimal("3.20")

    def balance_amount(self):
        return money(self.selling_price() - self.deposit_amount())

    def full_resolution_external_image_url(self, url):
        """Remove AliExpress thumbnail transforms while preserving other hosts."""
        url = (url or "").strip()
        if self.source_platform != "aliexpress":
            return url

        for extension in (".jpg", ".jpeg", ".png", ".webp"):
            marker = f"{extension}_"
            if marker in url:
                return url.split(marker, 1)[0] + extension
        return url

    def display_image_url(self):
        approved_primary = self.gallery_images.filter(
            color__isnull=True, visibility="public", is_primary=True,
        ).first()
        if approved_primary and approved_primary.public_url():
            return approved_primary.public_url()
        # Preserve the legacy external/uploaded cover behavior for old products.
        if self.external_image_url:
            return self.full_resolution_external_image_url(self.external_image_url)
        if self.image:
            return self.image.url
        return ""

    def display_gallery_urls(self):
        urls = []
        main_url = self.display_image_url()
        if main_url:
            urls.append(main_url)
        urls.extend(
            url for url in (img.public_url() for img in self.gallery_images.filter(color__isnull=True))
            if url
        )
        urls.extend(
            self.full_resolution_external_image_url(line)
            for line in self.external_gallery_urls.splitlines()
            if line.strip()
        )
        return list(dict.fromkeys(urls))

    def structured_variants(self):
        return self.variants.filter(is_active=True, is_deleted=False).select_related("color", "size")

    def uses_structured_variants(self):
        variants = self.structured_variants()
        return variants.exclude(color__isnull=True, size__isnull=True).exists() or variants.count() > 1

    def color_gallery_urls(self, color):
        urls = [img.public_url() for img in self.gallery_images.filter(color=color)]
        urls = [url for url in urls if url]
        return urls or self.display_gallery_urls()

    def size_option_list(self):
        return [item.strip() for item in self.size_options.split(",") if item.strip()]

    def color_option_list(self):
        return [item.strip() for item in self.color_options.split(",") if item.strip()]

    def availability_label(self):
        if self.product_type == "local":
            return self.stock_status()
        if self.available_quantity is not None:
            return f"Supplier availability: {self.available_quantity}"
        return "Availability confirmed before purchase"

    def delivery_range(self):
        return f"{self.delivery_min_days} to {self.delivery_max_days} days"

    def is_local_stock(self):
        return self.product_type == "local"

    def in_stock(self):
        if self.product_type == "local":
            return self.stock_quantity > 0
        return True

    def stock_status(self):
        if self.product_type == "preorder":
            return "Pre-order"

        if self.stock_quantity > 0:
            return f"In stock: {self.stock_quantity}"

        return "Out of stock"

    def whatsapp_link(self):
        phone = "260766491002"
        message = (
            "Hello, I want to ask about this product:\n"
            f"Product: {self.name}\n"
            f"Price: K{self.selling_price()}\n"
            f"Deposit: K{self.deposit_amount()}\n"
            f"Balance: K{self.balance_amount()}\n"
            f"View product: {settings.SITE_URL}/product/{self.slug}/"
        )
        return f"https://api.whatsapp.com/send/?{urlencode({'phone': phone, 'text': message, 'type': 'phone_number', 'app_absent': '0'})}"

    def __str__(self):
        return self.name


class ProductColor(TimeStampedModel):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="colors")
    name = models.CharField(max_length=80)
    code = models.SlugField(max_length=90)
    hex_value = models.CharField(max_length=7, blank=True)
    position = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    is_default = models.BooleanField(default=False)
    source_option_id = models.CharField(max_length=120, blank=True)

    class Meta:
        ordering = ["position", "name"]
        constraints = [models.UniqueConstraint(fields=["product", "code"], name="unique_product_color_code")]

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.product.name} - {self.name}"


class Size(models.Model):
    name = models.CharField(max_length=80)
    code = models.SlugField(max_length=90, unique=True)
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["sort_order", "name"]

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class ProductVariant(TimeStampedModel):
    CURRENCY_CHOICES = [("RMB", "RMB"), ("ZMW", "ZMW"), ("USD", "USD")]
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="variants")
    color = models.ForeignKey(ProductColor, on_delete=models.PROTECT, null=True, blank=True, related_name="variants")
    size = models.ForeignKey(Size, on_delete=models.PROTECT, null=True, blank=True, related_name="variants")
    sku = models.CharField(max_length=100, unique=True, blank=True)
    supplier_sku = models.CharField(max_length=120, blank=True)
    cost_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    cost_currency = models.CharField(max_length=3, choices=CURRENCY_CHOICES, default="RMB")
    selling_price_override = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    stock_quantity = models.PositiveIntegerField(default=0)
    supplier_available_quantity = models.PositiveIntegerField(null=True, blank=True)
    track_inventory = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)
    is_default = models.BooleanField(default=False)

    class Meta:
        ordering = ["product", "color__position", "size__sort_order", "sku"]
        constraints = [
            models.UniqueConstraint(fields=["product", "color", "size"], name="unique_product_color_size"),
            models.UniqueConstraint(fields=["product"], condition=models.Q(color__isnull=True, size__isnull=True), name="unique_default_product_variant"),
            models.UniqueConstraint(fields=["product", "color"], condition=models.Q(color__isnull=False, size__isnull=True), name="unique_product_color_only_variant"),
            models.UniqueConstraint(fields=["product", "size"], condition=models.Q(color__isnull=True, size__isnull=False), name="unique_product_size_only_variant"),
        ]

    def save(self, *args, **kwargs):
        if not self.sku:
            parts = [self.product.sku]
            if self.color_id:
                parts.append((self.color.code or "CLR")[:12].upper())
            if self.size_id:
                parts.append((self.size.code or "SIZE")[:12].upper())
            if len(parts) == 1:
                parts.append("DEFAULT")
            base = "-".join(parts)
            candidate = base
            counter = 2
            while ProductVariant.objects.filter(sku=candidate).exclude(pk=self.pk).exists():
                candidate = f"{base}-{counter}"
                counter += 1
            self.sku = candidate
        super().save(*args, **kwargs)

    def selling_price(self):
        if self.selling_price_override is not None:
            return money(self.selling_price_override)
        if self.cost_price is None:
            return self.product.selling_price()
        rate = self.product.active_exchange_rate()
        if self.cost_currency == "ZMW":
            markup = rate.local_markup_percentage if rate else Decimal("80.00")
            return money(self.cost_price * (Decimal("1") + markup / Decimal("100")))
        if self.cost_currency == "RMB":
            exchange = rate.rmb_to_zmw if rate else Decimal("3.20")
            markup = rate.markup_percentage if rate else Decimal("35.00")
            return money(self.cost_price * exchange * (Decimal("1") + markup / Decimal("100")))
        return self.product.selling_price()

    def in_stock(self):
        return not self.track_inventory or self.stock_quantity > 0

    def __str__(self):
        options = " / ".join(filter(None, [self.color.name if self.color_id else "", self.size.name if self.size_id else ""]))
        return f"{self.product.name} - {options or 'Default'}"


class ProductImage(TimeStampedModel):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="gallery_images")
    image = models.ImageField(upload_to="products/gallery/", blank=True, null=True)
    color = models.ForeignKey(ProductColor, on_delete=models.SET_NULL, null=True, blank=True, related_name="images")
    variant = models.ForeignKey(ProductVariant, on_delete=models.SET_NULL, null=True, blank=True, related_name="images")
    original_image = models.ImageField(storage=private_product_storage, upload_to="products/originals/", blank=True, null=True)
    customer_image = models.ImageField(upload_to="products/customer/", blank=True, null=True)
    processing_status = models.CharField(max_length=20, choices=[("original", "Original"), ("ready", "Ready"), ("rejected", "Rejected")], default="original")
    visibility = models.CharField(max_length=20, choices=[("private", "Private"), ("public", "Public")], default="public")
    is_primary = models.BooleanField(default=False)
    position = models.PositiveIntegerField(default=0)
    caption = models.CharField(max_length=100, blank=True)
    alt_text = models.CharField(max_length=160, blank=True)
    crop_data = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["position", "created_at"]

    def public_url(self):
        if self.visibility != "public":
            return ""
        if self.customer_image:
            return self.customer_image.url
        return self.image.url if self.image else ""

    def save(self, *args, **kwargs):
        if self.pk:
            previous = ProductImage.objects.filter(pk=self.pk).only("original_image").first()
            if previous and previous.original_image and self.original_image.name != previous.original_image.name:
                self.original_image = previous.original_image
        super().save(*args, **kwargs)
        if self.is_primary:
            ProductImage.objects.filter(product=self.product, color=self.color, is_primary=True).exclude(pk=self.pk).update(is_primary=False)

    def __str__(self):
        return f"Image for {self.product.name}"


class Cart(TimeStampedModel):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="cart")

    def total_price(self):
        return money(sum(item.line_total() for item in self.items.all()))

    def deposit_amount(self):
        return money(self.total_price() * (DEFAULT_DEPOSIT_PERCENTAGE / Decimal("100")))

    def balance_amount(self):
        return money(self.total_price() - self.deposit_amount())

    def total_items(self):
        return sum(item.quantity for item in self.items.all())

    def is_empty(self):
        return self.items.count() == 0

    def clear(self):
        self.items.all().delete()

    def __str__(self):
        return f"Cart - {self.user.username}"


class CartItem(models.Model):
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    variant = models.ForeignKey(ProductVariant, on_delete=models.PROTECT, null=True, blank=True, related_name="cart_items")
    quantity = models.PositiveIntegerField(default=1)
    requested_size = models.CharField(max_length=80, blank=True)
    requested_color = models.CharField(max_length=120, blank=True)

    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["cart", "product", "requested_size", "requested_color"], condition=models.Q(variant__isnull=True), name="unique_legacy_cart_product_variant"),
            models.UniqueConstraint(fields=["cart", "variant"], condition=models.Q(variant__isnull=False), name="unique_cart_structured_variant"),
        ]
        ordering = ["-added_at"]

    def line_total(self):
        price = self.variant.selling_price() if self.variant_id else self.product.selling_price()
        return money(price * self.quantity)

    def unit_price(self):
        return self.variant.selling_price() if self.variant_id else self.product.selling_price()

    def display_image_url(self):
        if self.variant_id and self.variant.color_id:
            urls = self.product.color_gallery_urls(self.variant.color)
            if urls:
                return urls[0]
        return self.product.display_image_url()

    def can_order_quantity(self):
        if self.variant_id and self.variant.track_inventory:
            return self.quantity <= self.variant.stock_quantity
        if self.product.product_type == "local":
            return self.quantity <= self.product.stock_quantity
        return True

    def __str__(self):
        return f"{self.quantity} x {self.product.name}"


class WishlistItem(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="wishlist_items")
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="wishlist_items")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["user", "product"], name="unique_user_wishlist_product"),
        ]

    def __str__(self):
        return f"{self.user.username} saved {self.product.name}"


class CustomerProfile(TimeStampedModel):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="customer_profile")
    phone = models.CharField(max_length=20, blank=True)
    photo = models.ImageField(upload_to="profile_photos/", blank=True, null=True)

    def is_complete(self):
        return bool(self.user.first_name.strip() and self.user.last_name.strip() and self.phone.strip() and self.photo)

    def completion_percentage(self):
        fields = [self.user.first_name.strip(), self.user.last_name.strip(), self.phone.strip(), self.photo]
        return int(sum(bool(value) for value in fields) / len(fields) * 100)

    def __str__(self):
        return f"Profile for {self.user.username}"


class SupplierProductRequest(TimeStampedModel):
    SOURCE_CHOICES = Product.SOURCE_CHOICES
    PRODUCT_TYPE_CHOICES = Product.PRODUCT_TYPE_CHOICES

    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)

    submitted_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="supplier_submissions",
        help_text="The approved supplier account that submitted this product.",
    )

    supplier_name = models.CharField(max_length=150)
    supplier_contact = models.CharField(max_length=100, blank=True)

    product_name = models.CharField(max_length=200)
    description = models.TextField()
    original_product_name = models.TextField(blank=True)
    original_description = models.TextField(blank=True)
    source_product_id = models.CharField(max_length=120, blank=True)
    source_currency = models.CharField(max_length=12, blank=True)
    displayed_price_min = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
    displayed_price_max = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
    original_displayed_price = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
    imported_store_name = models.CharField(max_length=200, blank=True)
    imported_variant_data = models.JSONField(default=dict, blank=True)
    selected_color = models.CharField(max_length=120, blank=True)
    selected_size = models.CharField(max_length=120, blank=True)
    selected_other_variants = models.TextField(blank=True)
    price_confirmed = models.BooleanField(default=False)
    import_status = models.CharField(max_length=20, choices=[("manual", "Manual"), ("partial", "Partial import"), ("complete", "Complete import")], default="manual")
    imported_image_paths = models.JSONField(default=list, blank=True)

    product_type = models.CharField(max_length=20, choices=PRODUCT_TYPE_CHOICES, default="preorder")
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True)

    stock_quantity = models.PositiveIntegerField(default=0)

    source_platform = models.CharField(max_length=20, choices=SOURCE_CHOICES, default="other")
    source_link = models.URLField(blank=True)

    rmb_price = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
    local_price = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)

    image = models.ImageField(upload_to="supplier_requests/", blank=True, null=True)
    external_image_url = models.URLField(blank=True)
    external_gallery_urls = models.TextField(blank=True, help_text="Imported image URLs, one per line.")

    is_reviewed = models.BooleanField(default=False)
    is_approved = models.BooleanField(default=False)

    admin_note = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]
        permissions = [
            ("can_submit_products", "Can submit products as an approved supplier"),
        ]

    def is_local(self):
        return self.product_type == "local"

    def is_preorder(self):
        return self.product_type == "preorder"

    def display_price(self):
        if self.product_type == "local":
            return f"K{self.local_price or Decimal('0.00')}"
        return f"¥{self.rmb_price or Decimal('0.00')}"

    def review_status(self):
        """Simple label for the supplier's own submission list."""
        if not self.is_reviewed:
            return "pending"
        return "approved" if self.is_approved else "rejected"

    def __str__(self):
        return f"{self.product_name} ({self.get_product_type_display()})"


class SupplierProductRequestImage(TimeStampedModel):
    supplier_request = models.ForeignKey(
        SupplierProductRequest,
        on_delete=models.CASCADE,
        related_name="images"
    )
    image = models.ImageField(upload_to="supplier_requests/gallery/")
    caption = models.CharField(max_length=100, blank=True)

    def __str__(self):
        return f"Image for {self.supplier_request.product_name}"


class CustomerProductRequest(TimeStampedModel):
    PLATFORM_CHOICES = [
        ("aliexpress", "AliExpress"),
        ("alibaba", "Alibaba"),
        ("taobao", "Taobao"),
        ("temu", "Temu"),
        ("1688", "1688"),
        ("shein", "Shein"),
        ("other", "Other"),
    ]

    STATUS_CHOICES = [
        ("new", "New"),
        ("reviewing", "Reviewing"),
        ("quoted", "Quoted"),
        ("ordered", "Ordered"),
        ("unavailable", "Unavailable"),
        ("closed", "Closed"),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="product_requests")
    product_name = models.CharField(max_length=200, blank=True)
    product_link = models.URLField()
    source_platform = models.CharField(max_length=20, choices=PLATFORM_CHOICES, default="other")
    notes = models.TextField(blank=True)
    screenshot = models.ImageField(upload_to="customer_product_requests/", blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="new")
    quoted_price = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
    quoted_deposit = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
    estimated_delivery_days = models.CharField(max_length=40, blank=True, default="24-60 days")
    quoted_at = models.DateTimeField(blank=True, null=True)
    customer_message = models.TextField(blank=True)
    customer_notified_at = models.DateTimeField(blank=True, null=True)
    admin_note = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["created_at"]),
        ]

    def __str__(self):
        label = self.product_name or self.product_link
        return f"{label} - {self.user.username}"

    def save(self, *args, **kwargs):
        if self.quoted_price and not self.quoted_deposit:
            self.quoted_deposit = money(self.quoted_price * (DEFAULT_DEPOSIT_PERCENTAGE / Decimal("100")))

        if self.status == "quoted" and self.quoted_price and not self.quoted_at:
            self.quoted_at = timezone.now()

        super().save(*args, **kwargs)


class Order(TimeStampedModel):
    STATUS_CHOICES = [
        ("pending", "Pending Confirmation"),
        ("confirmed", "Confirmed"),
        ("purchased", "Purchased in China"),
        ("shipped", "Shipped"),
        ("in_transit", "In Transit"),
        ("arrived", "Arrived in Zambia"),
        ("ready", "Ready for Collection / Delivery"),
        ("successful", "Successful"),
        ("delayed", "Delayed"),
        ("cancelled", "Cancelled"),
    ]

    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)

    user = models.ForeignKey(User, on_delete=models.CASCADE)

    tracking_code = models.CharField(max_length=30, unique=True, blank=True)

    total_price = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    deposit_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    balance_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))

    payment_proof = models.ImageField(upload_to="payment_proofs/", blank=True, null=True)
    payment_proof_uploaded_at = models.DateTimeField(blank=True, null=True)

    exchange_rate_used = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    markup_used = models.DecimalField(max_digits=5, decimal_places=2, blank=True, null=True)
    deposit_percentage_used = models.DecimalField(max_digits=5, decimal_places=2, blank=True, null=True)

    deposit_confirmed = models.BooleanField(default=False)
    balance_paid = models.BooleanField(default=False)
    payment_note = models.TextField(blank=True)

    AVAILABILITY_CHOICES = [
        ("not_required", "Not required"),
        ("awaiting_deposit", "Awaiting deposit"),
        ("checking", "Checking with supplier"),
        ("options_sent", "Available options sent to customer"),
        ("accepted", "Customer accepted"),
        ("cancelled", "Customer cancelled"),
    ]
    REFUND_CHOICES = [
        ("not_required", "Not required"),
        ("due", "Full deposit refund due"),
        ("completed", "Full deposit refunded"),
    ]
    availability_status = models.CharField(max_length=24, choices=AVAILABILITY_CHOICES, default="not_required")
    availability_due_at = models.DateTimeField(blank=True, null=True)
    availability_message = models.TextField(blank=True)
    availability_notified_at = models.DateTimeField(blank=True, null=True)
    refund_status = models.CharField(max_length=20, choices=REFUND_CHOICES, default="not_required")
    refund_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    refund_completed_at = models.DateTimeField(blank=True, null=True)

    order_date = models.DateTimeField(auto_now_add=True)

    estimated_arrival_start = models.DateField(blank=True, null=True)
    estimated_arrival_end = models.DateField(blank=True, null=True)
    arrival_date = models.DateField(blank=True, null=True)

    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default="pending")
    receipt_number = models.CharField(max_length=30, blank=True, null=True, unique=True)

    customer_phone = models.CharField(max_length=20)
    customer_note = models.TextField(blank=True)

    delivery_method = models.CharField(max_length=20, choices=DELIVERY_METHOD_CHOICES, default="collection")
    collection_centre = models.ForeignKey(
        CollectionCentre, on_delete=models.SET_NULL, null=True, blank=True, related_name="orders",
    )
    delivery_address = models.TextField(blank=True)
    delivery_fee = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    delivery_fee_percentage_used = models.DecimalField(max_digits=5, decimal_places=2, blank=True, null=True)

    stock_reduced = models.BooleanField(default=False)

    class Meta:
        ordering = ["-order_date"]
        indexes = [
            models.Index(fields=["tracking_code"]),
            models.Index(fields=["status"]),
            models.Index(fields=["order_date"]),
        ]

    def save(self, *args, **kwargs):
        rate = Product.active_exchange_rate()

        if rate:
            if not self.exchange_rate_used:
                self.exchange_rate_used = rate.rmb_to_zmw
            if not self.markup_used:
                self.markup_used = rate.markup_percentage
            if not self.deposit_percentage_used:
                self.deposit_percentage_used = rate.deposit_percentage

        today = timezone.now().date()

        if not self.tracking_code:
            year = timezone.now().year
            short_code = uuid.uuid4().hex[:6].upper()
            self.tracking_code = f"CZM-{year}-{short_code}"

        if not self.estimated_arrival_start:
            self.estimated_arrival_start = today + timedelta(days=14)

        if not self.estimated_arrival_end:
            self.estimated_arrival_end = today + timedelta(days=30)

        if self.status == "arrived" and not self.arrival_date:
            self.arrival_date = today

        super().save(*args, **kwargs)

    def recalculate_totals(self):
        items_total = sum(item.line_total for item in self.items.all())

        self.total_price = money(items_total) + money(self.delivery_fee)

        percentage = self.deposit_percentage_used or DEFAULT_DEPOSIT_PERCENTAGE
        self.deposit_amount = money(self.total_price * (percentage / Decimal("100")))
        self.balance_amount = money(self.total_price - self.deposit_amount)

        self.save()

    def delivery_summary(self):
        if self.delivery_method == "direct":
            return self.delivery_address or "Direct to address"
        if self.collection_centre:
            return f"Collect from {self.collection_centre.name} ({self.collection_centre.town})"
        return "Collect from centre"

    def reduce_local_stock(self):
        if self.stock_reduced:
            return
        from django.db import transaction
        with transaction.atomic():
            locked_order = Order.objects.select_for_update().get(pk=self.pk)
            if locked_order.stock_reduced:
                return
            for item in locked_order.items.select_related("product", "variant"):
                product = item.product
                if product.product_type != "local":
                    continue
                if item.variant_id:
                    variant = ProductVariant.objects.select_for_update().get(pk=item.variant_id)
                    if variant.track_inventory and variant.stock_quantity < item.quantity:
                        raise ValueError(f"Not enough stock for {product.name} ({variant.sku})")
                    if variant.track_inventory:
                        variant.stock_quantity -= item.quantity
                        variant.save(update_fields=["stock_quantity", "updated_at"])
                        StockMovement.objects.create(product=product, variant=variant, movement_type="sale", quantity=-item.quantity, note=f"Order {locked_order.tracking_code}")
                    product.stock_quantity = sum(v.stock_quantity for v in product.variants.filter(is_active=True, is_deleted=False, track_inventory=True))
                    product.save(update_fields=["stock_quantity", "status", "updated_at"])
                else:
                    product = Product.objects.select_for_update().get(pk=product.pk)
                    if product.stock_quantity < item.quantity:
                        raise ValueError(f"Not enough stock for {product.name}")
                    product.stock_quantity -= item.quantity
                    product.save(update_fields=["stock_quantity", "status", "updated_at"])
                    StockMovement.objects.create(product=product, movement_type="sale", quantity=-item.quantity, note=f"Order {locked_order.tracking_code}")
            locked_order.stock_reduced = True
            locked_order.save(update_fields=["stock_reduced", "updated_at"])
            self.stock_reduced = True

    def is_delayed(self):
        active_statuses = ["pending", "confirmed", "purchased", "shipped", "in_transit"]

        if self.status in active_statuses and self.estimated_arrival_end:
            return timezone.now().date() > self.estimated_arrival_end

        return False

    def progress_percentage(self):
        flow = [
            "pending",
            "confirmed",
            "purchased",
            "shipped",
            "in_transit",
            "arrived",
            "ready",
            "successful",
        ]

        if self.status in flow:
            return int(((flow.index(self.status) + 1) / len(flow)) * 100)

        if self.status == "cancelled":
            return 0

        if self.status == "delayed":
            return 50

        return 0

    def amount_paid(self):
        paid = Decimal("0.00")

        if self.deposit_confirmed:
            paid += self.deposit_amount

        if self.balance_paid:
            paid += self.balance_amount

        return money(paid)

    def amount_remaining(self):
        return money(self.total_price - self.amount_paid())

    def has_local_items(self):
        return self.items.filter(product__product_type="local").exists()

    def has_preorder_items(self):
        return self.items.filter(product__product_type="preorder").exists()

    def __str__(self):
        return f"Order {self.tracking_code} - {self.user.username}"


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")

    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    variant = models.ForeignKey(ProductVariant, on_delete=models.PROTECT, null=True, blank=True, related_name="order_items")

    product_name = models.CharField(max_length=200)
    quantity = models.PositiveIntegerField(default=1)

    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    line_total = models.DecimalField(max_digits=12, decimal_places=2)

    product_type = models.CharField(max_length=20, default="preorder")
    requested_size = models.CharField(max_length=80, blank=True)
    requested_color = models.CharField(max_length=120, blank=True)
    product_sku = models.CharField(max_length=60, blank=True)
    variant_sku = models.CharField(max_length=100, blank=True)
    color_name = models.CharField(max_length=120, blank=True)
    size_name = models.CharField(max_length=80, blank=True)
    selected_image = models.CharField(max_length=500, blank=True)
    availability_status = models.CharField(max_length=20, choices=[
        ("not_required", "Not required"),
        ("pending", "Pending verification"),
        ("available", "Available"),
        ("alternative", "Alternative offered"),
        ("unavailable", "Unavailable"),
    ], default="not_required")
    available_sizes = models.CharField(max_length=500, blank=True)
    available_colors = models.CharField(max_length=500, blank=True)
    available_quantity = models.PositiveIntegerField(blank=True, null=True)
    availability_note = models.TextField(blank=True)
    availability_checked_at = models.DateTimeField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def save(self, *args, **kwargs):
        if not self.product_name:
            self.product_name = self.product.name
        if not self.product_sku:
            self.product_sku = self.product.sku
        if self.variant_id:
            self.variant_sku = self.variant_sku or self.variant.sku
            self.color_name = self.color_name or (self.variant.color.name if self.variant.color_id else "")
            self.size_name = self.size_name or (self.variant.size.name if self.variant.size_id else "")
            self.requested_color = self.requested_color or self.color_name
            self.requested_size = self.requested_size or self.size_name

        if not self.unit_price:
            self.unit_price = self.product.selling_price()

        self.line_total = money(self.unit_price * self.quantity)
        self.product_type = self.product.product_type

        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.quantity} x {self.product_name}"


class OrderCheckpoint(TimeStampedModel):
    CHECKPOINT_CHOICES = [
        ("placed", "Order Placed"),
        ("confirmed", "Confirmed"),
        ("purchased", "Purchased in China"),
        ("departed_origin", "Departed China"),
        ("arrived_origin_port", "Arrived at Origin Port"),
        ("in_transit", "In Transit (Sea/Air Freight)"),
        ("arrived_zambia_port", "Arrived in Zambia"),
        ("arrived_hub", "Arrived at Regional Hub"),
        ("en_route_destination", "En Route to Destination Town"),
        ("arrived_centre", "Arrived at Collection Centre"),
        ("biker_assigned", "Delivery Biker Assigned"),
        ("out_for_delivery", "Out for Delivery"),
        ("delivered", "Delivered"),
        ("ready_for_collection", "Ready for Collection"),
        ("collected", "Collected by Customer"),
        ("delayed", "Delayed"),
        ("other", "Other"),
    ]

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="checkpoints")
    checkpoint_type = models.CharField(max_length=30, choices=CHECKPOINT_CHOICES)
    location_note = models.CharField(max_length=200, blank=True, help_text="e.g. \"Choma Market Centre\"")
    message = models.TextField(blank=True, help_text="Optional note shown to the customer.")
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    notify_customer = models.BooleanField(default=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"Order #{self.order_id} - {self.get_checkpoint_type_display()}"


class DeliveryJob(TimeStampedModel):
    STATUS_CHOICES = [
        ("available", "Available"),
        ("accepted", "Accepted"),
        ("picked_up", "Picked Up"),
        ("delivered", "Delivered"),
        ("cancelled", "Cancelled"),
    ]

    order = models.OneToOneField(Order, on_delete=models.CASCADE, related_name="delivery_job")
    centre = models.ForeignKey(CollectionCentre, on_delete=models.PROTECT, related_name="delivery_jobs")
    biker = models.ForeignKey(Biker, on_delete=models.SET_NULL, null=True, blank=True, related_name="jobs")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="available")

    biker_fee_percentage_used = models.DecimalField(max_digits=5, decimal_places=2, blank=True, null=True)
    biker_payout_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))

    accepted_at = models.DateTimeField(blank=True, null=True)
    picked_up_at = models.DateTimeField(blank=True, null=True)
    delivered_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Job for Order #{self.order_id} ({self.get_status_display()})"


class StockMovement(TimeStampedModel):
    MOVEMENT_CHOICES = [
        ("in", "Stock In"),
        ("out", "Stock Out"),
        ("adjustment", "Adjustment"),
        ("sale", "Sale"),
        ("return", "Return"),
    ]

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="stock_movements")
    variant = models.ForeignKey(ProductVariant, on_delete=models.SET_NULL, null=True, blank=True, related_name="stock_movements")
    movement_type = models.CharField(max_length=20, choices=MOVEMENT_CHOICES)
    quantity = models.IntegerField()
    note = models.TextField(blank=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.product.name} - {self.movement_type} - {self.quantity}"


class ProductReview(TimeStampedModel):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="reviews")
    user = models.ForeignKey(User, on_delete=models.CASCADE)

    rating = models.PositiveSmallIntegerField(default=5)
    comment = models.TextField(blank=True)

    is_approved = models.BooleanField(default=True)

    class Meta:
        ordering = ["-created_at"]
        unique_together = ("product", "user")

    def __str__(self):
        return f"{self.product.name} - {self.rating}/5"


class Advertisement(TimeStampedModel):
    HOUR_CHOICES = [(i, f"{i:02d}:00 – {i:02d}:59") for i in range(24)]

    advertiser_name = models.CharField(max_length=150)
    headline = models.CharField(max_length=100)
    subtext = models.CharField(max_length=160, blank=True)

    image = models.ImageField(upload_to="ads/", blank=True, null=True)

    cta_text = models.CharField(max_length=30, default="Visit")
    cta_url = models.URLField()

    hour_slot = models.PositiveSmallIntegerField(
        choices=HOUR_CHOICES,
        blank=True,
        null=True,
        help_text="Optional old-style hourly slot."
    )

    display_from = models.DateTimeField(blank=True, null=True)
    display_until = models.DateTimeField(blank=True, null=True)

    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["hour_slot", "-created_at"]

    def is_currently_active(self):
        now = timezone.now()

        if not self.is_active:
            return False

        if self.display_from and now < self.display_from:
            return False

        if self.display_until and now > self.display_until:
            return False

        if self.hour_slot is not None and now.hour != self.hour_slot:
            return False

        return True

    def __str__(self):
        slot = f"Slot {self.hour_slot:02d}h" if self.hour_slot is not None else "Flexible Slot"
        return f"[{slot}] {self.advertiser_name} — {self.headline}"

class BroadcastNotification(models.Model):
    title = models.CharField(max_length=120)
    message = models.TextField()
    url = models.CharField(max_length=500, blank=True, default="/", help_text="Page to open when a user taps the notification.")
    created_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="broadcast_notifications")
    created_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "broadcast notification"
        verbose_name_plural = "broadcast notifications"

    def __str__(self):
        return self.title


class MarketplaceEvent(models.Model):
    EVENT_CHOICES = [
        ("search", "Search"),
        ("zero_search", "Search with no results"),
        ("product_view", "Product view"),
        ("whatsapp_click", "WhatsApp click"),
        ("add_to_cart", "Add to cart"),
        ("completed_order", "Completed order"),
    ]

    event_type = models.CharField(max_length=30, choices=EVENT_CHOICES, db_index=True)
    user = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="marketplace_events")
    session_key = models.CharField(max_length=40, blank=True, db_index=True)
    product = models.ForeignKey(Product, null=True, blank=True, on_delete=models.SET_NULL, related_name="marketplace_events")
    order = models.ForeignKey(Order, null=True, blank=True, on_delete=models.SET_NULL, related_name="marketplace_events")
    search_query = models.CharField(max_length=200, blank=True, db_index=True)
    result_count = models.PositiveIntegerField(null=True, blank=True)
    quantity = models.PositiveIntegerField(null=True, blank=True)
    value = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    path = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["event_type", "order"], name="unique_completed_order_event"),
        ]

    def __str__(self):
        subject = self.search_query or (self.product.name if self.product_id else "")
        return f"{self.get_event_type_display()}: {subject}".strip()

