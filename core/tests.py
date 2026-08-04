from decimal import Decimal

from django.contrib.auth.models import User
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
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
        for url_name in ["home", "about", "faq", "register", "terms", "privacy", "registration_pending"]:
            with self.subTest(url_name=url_name):
                response = self.client.get(reverse(url_name))
                self.assertEqual(response.status_code, 200)

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

        self.assertEqual(response.status_code, 302)
        self.assertTrue(response["Location"].startswith("https://wa.me/"))

        order = Order.objects.get(user=user)
        self.assertEqual(order.total_price, Decimal("864.00"))
        self.assertEqual(order.deposit_percentage_used, Decimal("35.00"))
        self.assertEqual(order.deposit_amount, Decimal("302.40"))
        self.assertEqual(order.balance_amount, Decimal("561.60"))
        self.assertEqual(order.items.count(), 1)
        self.assertFalse(cart.items.exists())
