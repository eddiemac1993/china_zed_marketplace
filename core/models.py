from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from django.utils.text import slugify
from decimal import Decimal, ROUND_HALF_UP
from datetime import timedelta
import uuid

DEFAULT_DEPOSIT_PERCENTAGE = Decimal("35.00")


def money(value):
    return Decimal(value or 0).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


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
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self):
        return f"1 RMB = K{self.rmb_to_zmw} | Markup {self.markup_percentage}%"


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
    rmb_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        help_text="For local products, use this field as the buying/local cost price."
    )

    image = models.ImageField(upload_to="products/", blank=True, null=True)

    product_type = models.CharField(max_length=20, choices=PRODUCT_TYPE_CHOICES, default="preorder")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="active")

    stock_quantity = models.PositiveIntegerField(default=0)

    is_available = models.BooleanField(default=True)
    is_featured = models.BooleanField(default=False)

    delivery_min_days = models.PositiveIntegerField(default=14)
    delivery_max_days = models.PositiveIntegerField(default=30)

    source_platform = models.CharField(max_length=20, choices=SOURCE_CHOICES, default="other")
    source_link = models.URLField(blank=True)

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

    def balance_amount(self):
        return money(self.selling_price() - self.deposit_amount())

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
        phone = "260969274458"
        message = (
            f"Hello, I want to ask about this product:%0A"
            f"Product: {self.name}%0A"
            f"Price: K{self.selling_price()}%0A"
            f"Deposit: K{self.deposit_amount()}%0A"
            f"Balance: K{self.balance_amount()}"
        )
        return f"https://wa.me/{phone}?text={message}"

    def __str__(self):
        return self.name


class ProductImage(TimeStampedModel):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="gallery_images")
    image = models.ImageField(upload_to="products/gallery/")
    caption = models.CharField(max_length=100, blank=True)

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
    quantity = models.PositiveIntegerField(default=1)

    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("cart", "product")
        ordering = ["-added_at"]

    def line_total(self):
        return money(self.product.selling_price() * self.quantity)

    def can_order_quantity(self):
        if self.product.product_type == "local":
            return self.quantity <= self.product.stock_quantity
        return True

    def __str__(self):
        return f"{self.quantity} x {self.product.name}"


class SupplierProductRequest(TimeStampedModel):
    SOURCE_CHOICES = Product.SOURCE_CHOICES
    PRODUCT_TYPE_CHOICES = Product.PRODUCT_TYPE_CHOICES

    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)

    supplier_name = models.CharField(max_length=150)
    supplier_contact = models.CharField(max_length=100, blank=True)

    product_name = models.CharField(max_length=200)
    description = models.TextField()

    product_type = models.CharField(max_length=20, choices=PRODUCT_TYPE_CHOICES, default="preorder")
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True)

    stock_quantity = models.PositiveIntegerField(default=0)

    source_platform = models.CharField(max_length=20, choices=SOURCE_CHOICES, default="other")
    source_link = models.URLField(blank=True)

    rmb_price = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
    local_price = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)

    image = models.ImageField(upload_to="supplier_requests/", blank=True, null=True)

    is_reviewed = models.BooleanField(default=False)
    is_approved = models.BooleanField(default=False)

    admin_note = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]

    def is_local(self):
        return self.product_type == "local"

    def is_preorder(self):
        return self.product_type == "preorder"

    def display_price(self):
        if self.product_type == "local":
            return f"K{self.local_price or Decimal('0.00')}"
        return f"¥{self.rmb_price or Decimal('0.00')}"

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

    order_date = models.DateTimeField(auto_now_add=True)

    estimated_arrival_start = models.DateField(blank=True, null=True)
    estimated_arrival_end = models.DateField(blank=True, null=True)
    arrival_date = models.DateField(blank=True, null=True)

    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default="pending")
    receipt_number = models.CharField(max_length=30, blank=True, null=True, unique=True)

    customer_phone = models.CharField(max_length=20)
    customer_note = models.TextField(blank=True)

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
        total = sum(item.line_total for item in self.items.all())

        self.total_price = money(total)

        percentage = self.deposit_percentage_used or DEFAULT_DEPOSIT_PERCENTAGE
        self.deposit_amount = money(self.total_price * (percentage / Decimal("100")))
        self.balance_amount = money(self.total_price - self.deposit_amount)

        self.save()

    def reduce_local_stock(self):
        if self.stock_reduced:
            return

        for item in self.items.all():
            product = item.product

            if product.product_type == "local":
                if product.stock_quantity < item.quantity:
                    raise ValueError(f"Not enough stock for {product.name}")

                product.stock_quantity -= item.quantity
                product.save()

        self.stock_reduced = True
        self.save()

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

    product_name = models.CharField(max_length=200)
    quantity = models.PositiveIntegerField(default=1)

    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    line_total = models.DecimalField(max_digits=12, decimal_places=2)

    product_type = models.CharField(max_length=20, default="preorder")

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def save(self, *args, **kwargs):
        if not self.product_name:
            self.product_name = self.product.name

        if not self.unit_price:
            self.unit_price = self.product.selling_price()

        self.line_total = money(self.unit_price * self.quantity)
        self.product_type = self.product.product_type

        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.quantity} x {self.product_name}"


class StockMovement(TimeStampedModel):
    MOVEMENT_CHOICES = [
        ("in", "Stock In"),
        ("out", "Stock Out"),
        ("adjustment", "Adjustment"),
        ("sale", "Sale"),
        ("return", "Return"),
    ]

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="stock_movements")
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
