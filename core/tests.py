from decimal import Decimal
from io import StringIO
import tempfile
from unittest.mock import patch

from django.contrib.auth.models import User
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from .forms import CustomUserRegistrationForm
from .models import (
    Cart,
    CartItem,
    CustomerProductRequest,
    ExchangeRate,
    Order,
    Product,
)


class FakeResponse:
    def __init__(self, text, status_code=200):
        self.text = text
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise Exception(f"HTTP {self.status_code}")


@override_settings(
    ALLOWED_HOSTS=["testserver"],
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    DEFAULT_FROM_EMAIL="test@chinatozambia.org",
)
class MarketplaceFlowTests(TestCase):
    def setUp(self):
        self.rate = ExchangeRate.objects.create(
            rmb_to_zmw=Decimal("3.20"),
            markup_percentage=Decimal("35.00"),
            deposit_percentage=Decimal("35.00"),
            is_active=True,
        )

    def create_user(self, username="buyer", email="buyer@example.com"):
        return User.objects.create_user(
            username=username,
            email=email,
            password="Str0ngPass!2026",
        )

    def create_preorder_product(self, name="Test Headphones"):
        return Product.objects.create(
            name=name,
            description="Reliable product for marketplace tests.",
            rmb_price=Decimal("100.00"),
            product_type="preorder",
            status="active",
            is_available=True,
            delivery_min_days=14,
            delivery_max_days=30,
        )

    def test_public_pages_load(self):
        for url_name in ["home", "about", "faq", "register", "terms", "privacy", "registration_pending", "assistant"]:
            with self.subTest(url_name=url_name):
                response = self.client.get(reverse(url_name))
                self.assertEqual(response.status_code, 200)

    def test_homepage_exposes_mobile_app_manifest(self):
        response = self.client.get(reverse("home"))

        self.assertContains(response, 'rel="manifest"')
        self.assertContains(response, "serviceWorker")

    def test_service_worker_is_served_from_site_root(self):
        response = self.client.get(reverse("service_worker"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/javascript")
        self.assertEqual(response["Service-Worker-Allowed"], "/")
        self.assertContains(response, "chinazed-app-v1")

    @patch.dict("os.environ", {"OPENAI_API_KEY": ""})
    def test_assistant_chat_returns_fallback_reply_without_api_key(self):
        response = self.client.post(
            reverse("assistant_chat"),
            data='{"message":"How does the deposit work?"}',
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("35% deposit", response.json()["reply"])

    def test_product_uses_35_percent_deposit(self):
        product = self.create_preorder_product()

        self.assertEqual(product.selling_price(), Decimal("432.00"))
        self.assertEqual(product.deposit_amount(), Decimal("151.20"))
        self.assertEqual(product.balance_amount(), Decimal("280.80"))

    def test_registration_requires_terms_and_blocks_temporary_email(self):
        missing_terms = CustomUserRegistrationForm(
            data={
                "username": "newbuyer",
                "email": "newbuyer@example.com",
                "password1": "Str0ngPass!2026",
                "password2": "Str0ngPass!2026",
            }
        )
        self.assertFalse(missing_terms.is_valid())
        self.assertIn("accept_terms", missing_terms.errors)

        temporary_email = CustomUserRegistrationForm(
            data={
                "username": "tempbuyer",
                "email": "tempbuyer@mailinator.com",
                "password1": "Str0ngPass!2026",
                "password2": "Str0ngPass!2026",
                "accept_terms": "on",
            }
        )
        self.assertFalse(temporary_email.is_valid())
        self.assertIn("Please use a permanent email address.", temporary_email.errors["email"])

    def test_registration_creates_inactive_user_and_sends_activation_email(self):
        response = self.client.post(
            reverse("register"),
            {
                "username": "verifyme",
                "email": "verifyme@example.com",
                "password1": "Str0ngPass!2026",
                "password2": "Str0ngPass!2026",
                "accept_terms": "on",
            },
        )

        self.assertRedirects(response, reverse("registration_pending"))
        user = User.objects.get(username="verifyme")
        self.assertFalse(user.is_active)
        self.assertEqual(user.email, "verifyme@example.com")
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Activate your ChinaZed account", mail.outbox[0].subject)

        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)
        activation_response = self.client.get(
            reverse("activate_account", kwargs={"uidb64": uid, "token": token})
        )

        self.assertRedirects(activation_response, reverse("login"))
        user.refresh_from_db()
        self.assertTrue(user.is_active)

    def test_request_product_requires_login_and_saves_customer_request(self):
        response = self.client.get(reverse("request_product"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response["Location"])

        user = self.create_user()
        self.client.force_login(user)

        response = self.client.post(
            reverse("request_product"),
            {
                "product_name": "Running shoes",
                "product_link": "https://www.alibaba.com/product-detail/example",
                "source_platform": "alibaba",
                "notes": "Size 42, black.",
            },
        )

        self.assertRedirects(response, reverse("profile"))
        product_request = CustomerProductRequest.objects.get(user=user)
        self.assertEqual(product_request.product_name, "Running shoes")
        self.assertEqual(product_request.status, "new")

    def test_quoted_product_request_calculates_deposit_and_shows_on_profile(self):
        user = self.create_user()
        product_request = CustomerProductRequest.objects.create(
            user=user,
            product_name="Smart watch",
            product_link="https://www.temu.com/example",
            source_platform="temu",
            status="quoted",
            quoted_price=Decimal("1000.00"),
            customer_message="Quote includes estimated shipping to Zambia.",
        )

        product_request.refresh_from_db()
        self.assertEqual(product_request.quoted_deposit, Decimal("350.00"))
        self.assertIsNotNone(product_request.quoted_at)

        self.client.force_login(user)
        response = self.client.get(reverse("profile"))

        self.assertContains(response, "Smart watch")
        self.assertContains(response, "K1,000")
        self.assertContains(response, "K350")

    def test_cart_checkout_creates_order_with_35_percent_deposit(self):
        user = self.create_user()
        product = self.create_preorder_product()
        cart = Cart.objects.create(user=user)
        CartItem.objects.create(cart=cart, product=product, quantity=2)

        self.client.force_login(user)
        response = self.client.post(
            reverse("checkout_cart"),
            {
                "customer_phone": "0970000000",
                "customer_note": "Please confirm before buying.",
            },
        )

        self.assertRedirects(response, reverse("order_detail", kwargs={"order_id": Order.objects.get(user=user).id}))

        order = Order.objects.get(user=user)
        self.assertEqual(order.total_price, Decimal("864.00"))
        self.assertEqual(order.deposit_percentage_used, Decimal("35.00"))
        self.assertEqual(order.deposit_amount, Decimal("302.40"))
        self.assertEqual(order.balance_amount, Decimal("561.60"))
        self.assertEqual(order.items.count(), 1)
        self.assertFalse(cart.items.exists())

        profile_response = self.client.get(reverse("profile"))
        self.assertContains(profile_response, "item-thumb")
        self.assertContains(profile_response, product.name)

    @patch("core.management.commands.import_aliexpress_products.requests.get")
    def test_import_aliexpress_product_creates_preorder_product(self, mock_get):
        html = """
        <html>
            <head>
                <script type="application/ld+json">
                {
                    "@type": "Product",
                    "name": "Portable Mini Projector",
                    "description": "Compact projector for home entertainment.",
                    "image": "https://example.com/projector.jpg",
                    "offers": {
                        "price": "25.50",
                        "priceCurrency": "USD"
                    }
                }
                </script>
            </head>
        </html>
        """
        mock_get.return_value = FakeResponse(html)
        out = StringIO()

        call_command(
            "import_aliexpress_products",
            "https://www.aliexpress.com/item/100500-example.html",
            "--category",
            "Electronics",
            "--status",
            "active",
            "--usd-to-rmb",
            "7.20",
            stdout=out,
        )

        product = Product.objects.get(source_platform="aliexpress")
        self.assertEqual(product.name, "Portable Mini Projector")
        self.assertEqual(product.rmb_price, Decimal("183.60"))
        self.assertEqual(product.external_image_url, "https://example.com/projector.jpg")
        self.assertEqual(product.product_type, "preorder")
        self.assertEqual(product.status, "active")
        self.assertEqual(product.category.name, "Electronics")

        response = self.client.get(reverse("home"))
        self.assertContains(response, "https://example.com/projector.jpg")

    @patch("core.management.commands.import_aliexpress_products.requests.get")
    def test_import_aliexpress_product_accepts_manual_price_when_scrape_has_no_price(self, mock_get):
        mock_get.return_value = FakeResponse("<html><title>Blocked page</title></html>")
        out = StringIO()

        call_command(
            "import_aliexpress_products",
            "https://www.aliexpress.com/item/100500-manual.html",
            "--name",
            "Manual AliExpress Watch",
            "--price-usd",
            "12.00",
            "--usd-to-rmb",
            "7.20",
            stdout=out,
        )

        product = Product.objects.get(source_platform="aliexpress")
        self.assertEqual(product.name, "Manual AliExpress Watch")
        self.assertEqual(product.rmb_price, Decimal("86.40"))
        self.assertEqual(product.status, "draft")

    @patch("core.management.commands.import_aliexpress_products.requests.get")
    def test_import_china_product_detects_alibaba_links(self, mock_get):
        mock_get.return_value = FakeResponse("<html><title>Alibaba TV Product</title></html>")
        out = StringIO()

        call_command(
            "import_aliexpress_products",
            "https://www.alibaba.com/product-detail/Big-Screen-50-55-65-75_1601757949259.html",
            "--name",
            "Big Screen Smart TV",
            "--price-usd",
            "120.00",
            "--gallery-url",
            "https://example.com/tv-side.jpg",
            "--available-quantity",
            "12",
            "--sizes",
            "50 inch, 55 inch, 65 inch",
            "--colors",
            "Black, Silver",
            "--category",
            "Electronics",
            stdout=out,
        )

        product = Product.objects.get(source_platform="alibaba")
        self.assertEqual(product.name, "Big Screen Smart TV")
        self.assertEqual(product.rmb_price, Decimal("864.00"))
        self.assertEqual(product.supplier_name, "Alibaba")
        self.assertEqual(product.external_gallery_urls, "https://example.com/tv-side.jpg")
        self.assertEqual(product.available_quantity, 12)
        self.assertEqual(product.size_option_list(), ["50 inch", "55 inch", "65 inch"])
        self.assertEqual(product.color_option_list(), ["Black", "Silver"])

    def test_product_display_image_url_prefers_external_image_when_no_upload(self):
        product = self.create_preorder_product(name="External image item")
        product.external_image_url = "https://example.com/product.png"
        product.external_gallery_urls = "https://example.com/product-blue.png\nhttps://example.com/product-red.png"
        product.available_quantity = 25
        product.size_options = "S, M, L"
        product.color_options = "Black, Blue"
        product.save(update_fields=[
            "external_image_url",
            "external_gallery_urls",
            "available_quantity",
            "size_options",
            "color_options",
        ])

        self.assertEqual(product.display_image_url(), "https://example.com/product.png")
        self.assertEqual(
            product.display_gallery_urls(),
            [
                "https://example.com/product.png",
                "https://example.com/product-blue.png",
                "https://example.com/product-red.png",
            ],
        )
        self.assertEqual(product.size_option_list(), ["S", "M", "L"])
        self.assertEqual(product.color_option_list(), ["Black", "Blue"])
        self.assertEqual(product.availability_label(), "Supplier availability: 25")

        response = self.client.get(reverse("home"))
        self.assertContains(response, "https://example.com/product.png")

        detail_response = self.client.get(reverse("product_detail", kwargs={"slug": product.slug}))
        self.assertContains(detail_response, "https://example.com/product-blue.png")
        self.assertContains(detail_response, "Tap to zoom")
        self.assertContains(detail_response, "Supplier availability: 25")
        self.assertContains(detail_response, "Black")
        self.assertContains(detail_response, "S")

    def test_aliexpress_import_page_requires_staff(self):
        response = self.client.get(reverse("aliexpress_import"))

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response["Location"])

        user = self.create_user()
        self.client.force_login(user)
        response = self.client.get(reverse("aliexpress_import"))

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response["Location"])

    @patch("core.views.requests.get")
    def test_staff_can_preview_aliexpress_product_import(self, mock_get):
        html = """
        <html>
            <head>
                <script type="application/ld+json">
                {
                    "@type": "Product",
                    "name": "Portable Mini Projector",
                    "description": "Compact projector for home entertainment.",
                    "image": "https://example.com/projector.jpg",
                    "offers": {
                        "price": "25.50",
                        "priceCurrency": "USD"
                    }
                }
                </script>
            </head>
        </html>
        """
        mock_get.return_value = FakeResponse(html)
        staff = self.create_user(username="staff", email="staff@example.com")
        staff.is_staff = True
        staff.save(update_fields=["is_staff"])
        self.client.force_login(staff)

        response = self.client.post(
            reverse("aliexpress_import"),
            {
                "action": "preview",
                "product_url": "https://www.aliexpress.com/item/100500-preview.html",
                "usd_to_rmb": "7.20",
                "status": "active",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Portable Mini Projector")
        self.assertContains(response, "https://example.com/projector.jpg")
        self.assertContains(response, 'value="25.50"')
        self.assertContains(response, "https://www.aliexpress.com/item/100500-preview.html")

    @patch("core.views.requests.get")
    def test_staff_can_preview_aliexpress_product_import_without_url_scheme(self, mock_get):
        mock_get.return_value = FakeResponse("<html><title>AliExpress Phone Case</title></html>")
        staff = self.create_user(username="staff", email="staff@example.com")
        staff.is_staff = True
        staff.save(update_fields=["is_staff"])
        self.client.force_login(staff)

        response = self.client.post(
            reverse("aliexpress_import"),
            {
                "action": "preview",
                "product_url": "aliexpress.com/item/1005006227982959.html?spm=test",
                "usd_to_rmb": "7.20",
                "status": "active",
            },
        )

        self.assertEqual(response.status_code, 200)
        mock_get.assert_called_once()
        fetched_url = mock_get.call_args.args[0]
        self.assertEqual(fetched_url, "https://www.aliexpress.com/item/1005006227982959.html?spm=test")
        self.assertContains(response, "https://www.aliexpress.com/item/1005006227982959.html?spm=test")

    @patch("core.views.requests.get")
    def test_staff_preview_extracts_price_from_aliexpress_url_tracking_data(self, mock_get):
        mock_get.return_value = FakeResponse("<html><title>Fresh AliExpress Cable</title></html>")
        staff = self.create_user(username="staff", email="staff@example.com")
        staff.is_staff = True
        staff.save(update_fields=["is_staff"])
        self.client.force_login(staff)

        product_url = (
            "https://www.aliexpress.com/item/1005004196279246.html?"
            "pdp_npi=6%40dis%21ZMW%21ZMW+69.13%21ZMW+53.13%21%21%213.24%212.49%21%402101"
        )
        response = self.client.post(
            reverse("aliexpress_import"),
            {
                "action": "preview",
                "product_url": product_url,
                "name": "Old Product Name",
                "price_usd": "99.99",
                "usd_to_rmb": "7.20",
                "status": "active",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Fresh AliExpress Cable")
        self.assertNotContains(response, "Old Product Name")
        self.assertContains(response, 'value="2.49"')

    def test_staff_can_create_aliexpress_product_from_import_form(self):
        staff = self.create_user(username="staff", email="staff@example.com")
        staff.is_staff = True
        staff.save(update_fields=["is_staff"])
        self.client.force_login(staff)

        response = self.client.post(
            reverse("aliexpress_import"),
            {
                "action": "create",
                "product_url": "https://www.aliexpress.com/item/100500-create.html",
                "name": "AliExpress Smart Watch",
                "description": "Smart watch with multiple strap colors.",
                "price_usd": "12.00",
                "usd_to_rmb": "7.20",
                "new_category": "Smart Watches",
                "status": "active",
                "external_image_url": "https://example.com/watch-main.jpg",
                "external_gallery_urls": "https://example.com/watch-blue.jpg\nhttps://example.com/watch-black.jpg",
                "available_quantity": "50",
                "size_options": "One size",
                "color_options": "Blue, Black",
            },
        )

        product = Product.objects.get(source_link="https://www.aliexpress.com/item/100500-create.html")
        self.assertRedirects(response, reverse("product_detail", kwargs={"slug": product.slug}))
        self.assertEqual(product.name, "AliExpress Smart Watch")
        self.assertEqual(product.rmb_price, Decimal("86.40"))
        self.assertEqual(product.category.name, "Smart Watches")
        self.assertEqual(product.source_platform, "aliexpress")
        self.assertEqual(product.available_quantity, 50)
        self.assertEqual(product.display_gallery_urls()[1:], [
            "https://example.com/watch-blue.jpg",
            "https://example.com/watch-black.jpg",
        ])
        self.assertEqual(product.color_option_list(), ["Blue", "Black"])

    def test_staff_can_upload_main_image_when_creating_aliexpress_product(self):
        staff = self.create_user(username="staff", email="staff@example.com")
        staff.is_staff = True
        staff.save(update_fields=["is_staff"])
        self.client.force_login(staff)
        image = SimpleUploadedFile(
            "watch.gif",
            b"GIF87a\x01\x00\x01\x00\x80\x01\x00\x00\x00\x00\xff\xff\xff,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;",
            content_type="image/gif",
        )

        with tempfile.TemporaryDirectory() as media_root:
            with override_settings(MEDIA_ROOT=media_root):
                response = self.client.post(
                    reverse("aliexpress_import"),
                    {
                        "action": "create",
                        "product_url": "https://www.aliexpress.com/item/100500-upload.html",
                        "name": "Uploaded Image Watch",
                        "description": "Watch imported with a manually uploaded image.",
                        "price_usd": "8.50",
                        "usd_to_rmb": "7.20",
                        "new_category": "Smart Watches",
                        "status": "active",
                        "uploaded_image": image,
                    },
                )

                product = Product.objects.get(source_link="https://www.aliexpress.com/item/100500-upload.html")
                self.assertRedirects(response, reverse("product_detail", kwargs={"slug": product.slug}))
                self.assertTrue(product.image.name.startswith("products/"))
                self.assertIn("watch", product.display_image_url())
