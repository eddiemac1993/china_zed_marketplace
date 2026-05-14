from django.db import models
from django.contrib.auth.models import User
from decimal import Decimal, ROUND_HALF_UP
from datetime import timedelta
from django.utils import timezone
from django.utils.text import slugify


def money(value):
    return Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


class ExchangeRate(models.Model):
    rmb_to_zmw = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("3.20"))
    markup_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("35.00"))
    is_active = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self):
        return f"1 RMB = K{self.rmb_to_zmw} | Markup {self.markup_percentage}%"


class Category(models.Model):
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


class Product(models.Model):
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

    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=230, unique=True, blank=True)
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True)

    description = models.TextField()
    rmb_price = models.DecimalField(max_digits=12, decimal_places=2)

    image = models.ImageField(upload_to="products/", blank=True, null=True)

    product_type = models.CharField(
        max_length=20,
        choices=PRODUCT_TYPE_CHOICES,
        default="preorder"
    )

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

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.name)
            slug = base_slug
            counter = 1

            while Product.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1

            self.slug = slug

        super().save(*args, **kwargs)

    @staticmethod
    def active_exchange_rate():
        return ExchangeRate.objects.filter(is_active=True).order_by("-updated_at").first()

    def kwacha_base_price(self):
        rate = self.active_exchange_rate()
        rmb_rate = rate.rmb_to_zmw if rate else Decimal("3.20")
        return money(self.rmb_price * rmb_rate)

    def selling_price(self):
        rate = self.active_exchange_rate()
        markup = rate.markup_percentage if rate else Decimal("35.00")

        base_price = self.kwacha_base_price()
        return money(base_price + (base_price * markup / Decimal("100")))

    def deposit_amount(self):
        return money(self.selling_price() * Decimal("0.20"))

    def balance_amount(self):
        return money(self.selling_price() * Decimal("0.80"))

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


class ProductImage(models.Model):
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="gallery_images"
    )
    image = models.ImageField(upload_to="products/gallery/")
    caption = models.CharField(max_length=100, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Image for {self.product.name}"


class Cart(models.Model):
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="cart"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def total_price(self):
        return money(sum(item.line_total() for item in self.items.all()))

    def deposit_amount(self):
        return money(self.total_price() * Decimal("0.20"))

    def balance_amount(self):
        return money(self.total_price() * Decimal("0.80"))

    def total_items(self):
        return sum(item.quantity for item in self.items.all())

    def is_empty(self):
        return self.items.count() == 0

    def clear(self):
        self.items.all().delete()

    def __str__(self):
        return f"Cart - {self.user.username}"


class CartItem(models.Model):
    cart = models.ForeignKey(
        Cart,
        on_delete=models.CASCADE,
        related_name="items"
    )
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


class SupplierProductRequest(models.Model):
    SOURCE_CHOICES = [
        ("taobao", "Taobao"),
        ("1688", "1688"),
        ("alibaba", "Alibaba"),
        ("wechat", "WeChat Supplier"),
        ("other", "Other"),
    ]

    supplier_name = models.CharField(max_length=150)
    supplier_contact = models.CharField(max_length=100, blank=True)

    product_name = models.CharField(max_length=200)
    description = models.TextField()

    source_platform = models.CharField(max_length=20, choices=SOURCE_CHOICES, default="other")
    source_link = models.URLField(blank=True)

    rmb_price = models.DecimalField(max_digits=12, decimal_places=2)
    image = models.ImageField(upload_to="supplier_requests/", blank=True, null=True)

    is_reviewed = models.BooleanField(default=False)
    is_approved = models.BooleanField(default=False)
    admin_note = models.TextField(blank=True)

    submitted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-submitted_at"]

    def __str__(self):
        return self.product_name


class SupplierProductRequestImage(models.Model):
    supplier_request = models.ForeignKey(
        SupplierProductRequest,
        on_delete=models.CASCADE,
        related_name="images"
    )
    image = models.ImageField(upload_to="supplier_requests/gallery/")
    caption = models.CharField(max_length=100, blank=True)

    def __str__(self):
        return f"Image for {self.supplier_request.product_name}"


class Order(models.Model):
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

    user = models.ForeignKey(User, on_delete=models.CASCADE)

    # models.py — Order model fields
    total_price    = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    deposit_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    balance_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))

    payment_proof = models.ImageField(upload_to="payment_proofs/", blank=True, null=True)
    payment_proof_uploaded_at = models.DateTimeField(blank=True, null=True)
    exchange_rate_used = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    markup_used = models.DecimalField(max_digits=5, decimal_places=2, blank=True, null=True)

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

    def save(self, *args, **kwargs):
        rate = Product.active_exchange_rate()

        if rate:
            if not self.exchange_rate_used:
                self.exchange_rate_used = rate.rmb_to_zmw
            if not self.markup_used:
                self.markup_used = rate.markup_percentage

        today = timezone.now().date()

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
        self.deposit_amount = money(self.total_price * Decimal("0.20"))
        self.balance_amount = money(self.total_price * Decimal("0.80"))
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
        return self.items.filter(product_type="local").exists()

    def has_preorder_items(self):
        return self.items.filter(product_type="preorder").exists()

    def __str__(self):
        return f"Order #{self.id} - {self.user.username}"


class OrderItem(models.Model):
    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name="items"
    )

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