from django.db import models
from django.contrib.auth.models import User
from decimal import Decimal
from datetime import date


class ExchangeRate(models.Model):
    rmb_to_zmw = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("3.20"))
    markup_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("35.00"))
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"1 RMB = K{self.rmb_to_zmw}"


class Category(models.Model):
    name = models.CharField(max_length=100)

    def __str__(self):
        return self.name


class Product(models.Model):
    name = models.CharField(max_length=200)
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True)
    description = models.TextField()
    rmb_price = models.DecimalField(max_digits=12, decimal_places=2)
    image = models.ImageField(upload_to="products/", blank=True, null=True)
    is_available = models.BooleanField(default=True)
    delivery_range = models.CharField(max_length=100, default="14 to 30 days")
    SOURCE_CHOICES = [
        ("taobao", "Taobao"),
        ("1688", "1688"),
        ("alibaba", "Alibaba"),
        ("wechat", "WeChat Supplier"),
        ("other", "Other"),
    ]

    source_platform = models.CharField(
        max_length=20,
        choices=SOURCE_CHOICES,
        default="other"
    )

    source_link = models.URLField(blank=True)

    supplier_name = models.CharField(max_length=150, blank=True)
    supplier_contact = models.CharField(max_length=100, blank=True)
    supplier_note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    is_featured = models.BooleanField(default=False)

    def kwacha_base_price(self):
        rate = ExchangeRate.objects.first()
        if not rate:
            return self.rmb_price * Decimal("3.20")
        return self.rmb_price * rate.rmb_to_zmw

    def selling_price(self):
        rate = ExchangeRate.objects.first()
        markup = Decimal("35.00")
        if rate:
            markup = rate.markup_percentage

        base_price = self.kwacha_base_price()
        return base_price + (base_price * markup / Decimal("100"))

    def deposit_amount(self):
        return self.selling_price() * Decimal("0.20")

    def balance_amount(self):
        return self.selling_price() * Decimal("0.80")

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
    product = models.ForeignKey(Product, on_delete=models.CASCADE)

    total_price = models.DecimalField(max_digits=12, decimal_places=2)
    deposit_amount = models.DecimalField(max_digits=12, decimal_places=2)
    balance_amount = models.DecimalField(max_digits=12, decimal_places=2)
    deposit_confirmed = models.BooleanField(default=False)
    balance_paid = models.BooleanField(default=False)
    payment_note = models.TextField(blank=True)
    order_date = models.DateTimeField(auto_now_add=True)
    estimated_arrival_start = models.DateField()
    estimated_arrival_end = models.DateField()
    arrival_date = models.DateField(blank=True, null=True)

    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default="pending")
    receipt_number = models.CharField(max_length=30, blank=True, null=True, unique=True)

    customer_phone = models.CharField(max_length=20)
    customer_note = models.TextField(blank=True)
    
    def is_delayed(self):
        active_statuses = ["pending", "confirmed", "purchased", "shipped", "in_transit"]

        if self.status in active_statuses and date.today() > self.estimated_arrival_end:
            return True

        return False
    
    def __str__(self):
        return f"{self.user.username} - {self.product.name}"
    
