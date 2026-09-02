from decimal import Decimal
import tempfile
from urllib.parse import parse_qs, urlparse

from django.contrib.auth.models import User
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.files.storage import FileSystemStorage
from django.test import TestCase, override_settings
from django.urls import reverse

from core.models import (
    CartItem, Category, Order, OrderItem, Product, ProductColor,
    ProductImage, ProductVariant, Size, StockMovement,
)


@override_settings(ALLOWED_HOSTS=["testserver"], SECURE_SSL_REDIRECT=False)
class StructuredVariantTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("buyer", password="pass")
        self.category = Category.objects.create(name="Shoes")
        self.product = Product.objects.create(
            name="Private cost sandal", description="Sandal", category=self.category,
            rmb_price=Decimal("60"), product_type="local", stock_quantity=5,
            status="active", is_available=True,
            external_image_url="https://example.com/sandal.jpg",
        )

    def test_supplier_cost_is_not_public_and_draft_is_hidden(self):
        response = self.client.get(reverse("home"))
        self.assertNotContains(response, "origin price")
        self.assertNotContains(response, "¥60")
        detail = self.client.get(reverse("product_detail", args=[self.product.slug]))
        self.assertNotContains(detail, "origin price")
        self.product.status = "draft"
        self.product.save(update_fields=["status", "updated_at"])
        self.assertEqual(self.client.get(reverse("product_detail", args=[self.product.slug])).status_code, 404)

    def test_whatsapp_message_contains_product_link(self):
        link = self.product.whatsapp_link()
        self.assertIn("api.whatsapp.com/send/", link)
        message = parse_qs(urlparse(link).query)["text"][0]
        self.assertIn(f"View product: {settings.SITE_URL}/product/{self.product.slug}/", message)

    def test_color_size_variant_is_added_as_separate_cart_line(self):
        brown = ProductColor.objects.create(product=self.product, name="Brown", code="brown", is_default=True)
        black = ProductColor.objects.create(product=self.product, name="Black", code="black")
        size = Size.objects.create(name="37", code="37", sort_order=37)
        brown_variant = ProductVariant.objects.create(product=self.product, color=brown, size=size, stock_quantity=4, cost_price=60, cost_currency="ZMW")
        black_variant = ProductVariant.objects.create(product=self.product, color=black, size=size, stock_quantity=2, cost_price=60, cost_currency="ZMW")
        self.client.force_login(self.user)
        self.client.post(reverse("add_to_cart", args=[self.product.slug]), {"variant_id": brown_variant.id, "quantity": 1})
        self.client.post(reverse("add_to_cart", args=[self.product.slug]), {"variant_id": black_variant.id, "quantity": 1})
        items = CartItem.objects.filter(cart__user=self.user)
        self.assertEqual(items.count(), 2)
        self.assertSetEqual(set(items.values_list("variant_id", flat=True)), {brown_variant.id, black_variant.id})

    def test_out_of_stock_variant_cannot_be_added(self):
        color = ProductColor.objects.create(product=self.product, name="Black", code="black")
        size = Size.objects.create(name="38", code="38", sort_order=38)
        variant = ProductVariant.objects.create(product=self.product, color=color, size=size, stock_quantity=0)
        self.client.force_login(self.user)
        self.client.post(reverse("add_to_cart", args=[self.product.slug]), {"variant_id": variant.id})
        self.assertFalse(CartItem.objects.filter(cart__user=self.user).exists())

    def test_customer_image_wins_and_original_is_preserved(self):
        field = ProductImage._meta.get_field("original_image")
        original_storage = field.storage
        with tempfile.TemporaryDirectory() as private_dir:
            field.storage = FileSystemStorage(location=private_dir)
            try:
                original = SimpleUploadedFile("supplier.jpg", b"supplier-original", content_type="image/jpeg")
                customer = SimpleUploadedFile("clean.jpg", b"customer-clean", content_type="image/jpeg")
                image = ProductImage.objects.create(product=self.product, original_image=original, customer_image=customer, visibility="public")
                self.assertIn("products/customer/", image.public_url())
                self.assertTrue(image.original_image.name)
            finally:
                field.storage = original_storage

    def test_variant_stock_reduction_is_snapshot_safe_and_records_movement(self):
        size = Size.objects.create(name="39", code="39", sort_order=39)
        variant = ProductVariant.objects.create(product=self.product, size=size, stock_quantity=3, cost_price=60, cost_currency="ZMW")
        order = Order.objects.create(user=self.user, customer_phone="+260971234567")
        OrderItem.objects.create(order=order, product=self.product, variant=variant, product_name=self.product.name, quantity=2, unit_price=100, line_total=200)
        order.reduce_local_stock()
        variant.refresh_from_db()
        self.assertEqual(variant.stock_quantity, 1)
        self.assertTrue(StockMovement.objects.filter(product=self.product, variant=variant, movement_type="sale", quantity=-2).exists())
        item = order.items.get()
        self.assertEqual(item.variant_sku, variant.sku)
        self.assertEqual(item.size_name, "39")
