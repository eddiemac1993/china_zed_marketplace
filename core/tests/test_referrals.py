from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib import admin
from django.contrib.auth.models import AnonymousUser, User
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from core.models import Category, Order, OrderItem, Product, ReferralReward
from core.referral_admin import ReferralRewardAdmin
from core.referrals import capture_referral, referral_url, referrer_for


@override_settings(SECURE_SSL_REDIRECT=False, ALLOWED_HOSTS=["testserver"])
class ReferralTests(TestCase):
    def setUp(self):
        self.referrer = User.objects.create_user("referrer")
        self.buyer = User.objects.create_user("buyer")
        self.product = Product.objects.create(name="Referral product", description="A product", rmb_price=100, category=Category.objects.create(name="Referral category"),
            status="active", is_available=True, external_image_url="https://example.com/product.png")
        self.factory = RequestFactory()

    def request(self, user=None):
        request = self.factory.get("/")
        request.user = user or AnonymousUser()
        request.session = {}
        return request

    def referred_request(self):
        from urllib.parse import urlsplit
        link = referral_url(self.request(self.referrer), self.product)
        request = self.factory.get(link)
        request.user = AnonymousUser()
        request.session = {}
        capture_referral(request, self.product)
        return request

    def order_item(self):
        order = Order.objects.create(user=self.buyer, customer_phone="260700000000", delivery_fee=50)
        item = OrderItem.objects.create(order=order, product=self.product, referrer=self.referrer,
            quantity=2, unit_price=Decimal("90.00"))
        return order, item

    def complete(self, order):
        order.status = "successful"
        order.deposit_confirmed = order.balance_paid = True
        order.save()

    def test_signed_link_attribution_survives_signin_and_is_product_specific(self):
        request = self.referred_request()
        request.user = self.buyer
        self.assertEqual(referrer_for(request, self.product), self.referrer)
        self.product.pk += 1000
        self.assertIsNone(referrer_for(request, self.product))

    def test_invalid_expired_and_self_referrals_are_rejected(self):
        request = self.request(self.buyer)
        request.GET = {"ref": "forged"}
        capture_referral(request, self.product)
        self.assertIsNone(referrer_for(request, self.product))
        request = self.referred_request()
        request.user = self.referrer
        self.assertIsNone(referrer_for(request, self.product))
        request.user = self.buyer
        request.session["product_referrals"][str(self.product.pk)]["expires"] = 0
        self.assertIsNone(referrer_for(request, self.product))

    def test_reward_requires_completion_and_payment_and_excludes_delivery(self):
        order, item = self.order_item()
        reward = item.referral_reward
        self.assertEqual(reward.amount, Decimal("9.00"))
        self.assertEqual(reward.status, "pending")
        order.status = "successful"
        order.save()
        reward.refresh_from_db()
        self.assertEqual(reward.status, "pending")
        self.complete(order)
        order.save()
        reward.refresh_from_db()
        self.assertEqual(reward.status, "earned")
        self.assertEqual(ReferralReward.objects.count(), 1)
        self.assertEqual((reward.payout_due + timedelta(days=1)).day, 1)

    def test_refund_voids_unpaid_rewards(self):
        order, item = self.order_item()
        self.complete(order)
        order.refund_status = "due"
        order.save()
        item.referral_reward.refresh_from_db()
        self.assertEqual(item.referral_reward.status, "void")

    def test_self_purchase_does_not_create_reward(self):
        order = Order.objects.create(user=self.referrer, customer_phone="260700000000")
        OrderItem.objects.create(order=order, product=self.product, referrer=self.referrer, quantity=1, unit_price=100)
        self.complete(order)
        self.assertFalse(ReferralReward.objects.exists())

    def test_payout_requires_reference_due_date_and_cannot_repeat(self):
        order, item = self.order_item()
        self.complete(order)
        reward = item.referral_reward
        reward.refresh_from_db()
        model_admin = ReferralRewardAdmin(ReferralReward, admin.site)
        request = self.request(self.referrer)
        with patch.object(model_admin, "message_user"), patch.object(model_admin, "log_change"):
            model_admin.record_payment(request, ReferralReward.objects.all())
            reward.refresh_from_db()
            self.assertEqual(reward.status, "earned")
            reward.payout_due = timezone.localdate()
            reward.payment_reference = "TEST-TRANSFER-123"
            reward.save()
            model_admin.record_payment(request, ReferralReward.objects.all())
            reward.refresh_from_db()
            self.assertEqual(reward.status, "paid")
            paid_at = reward.paid_at
            model_admin.record_payment(request, ReferralReward.objects.all())
            order.save()
            reward.refresh_from_db()
            self.assertEqual(reward.paid_at, paid_at)
            self.assertEqual(reward.paid_by, self.referrer)

    def test_product_share_and_profile_render(self):
        self.client.force_login(self.referrer)
        response = self.client.get(reverse("product_detail", args=[self.product.slug]))
        self.assertContains(response, "Share my referral link")
        self.assertContains(response, "?ref=")
        response = self.client.get(reverse("profile"))
        self.assertContains(response, "Your referral earnings")

    def test_guest_link_is_captured_by_product_view(self):
        link = referral_url(self.request(self.referrer), self.product)
        self.client.get(link)
        self.client.force_login(self.buyer)
        self.assertEqual(self.client.session["product_referrals"][str(self.product.pk)]["user"], self.referrer.pk)

    def test_whatsapp_share_includes_referral(self):
        from urllib.parse import parse_qs, urlparse
        self.client.force_login(self.referrer)
        response = self.client.get(reverse("product_whatsapp", args=[self.product.slug]))
        message = parse_qs(urlparse(response.url).query)["text"][0]
        self.assertIn("?ref=", message)

    def test_both_checkout_paths_preserve_referrer(self):
        from core.models import Cart, CartItem, CollectionCentre
        CollectionCentre.objects.all().delete()
        link = referral_url(self.request(self.referrer), self.product)
        self.client.get(link)
        self.client.force_login(self.buyer)
        form = {"customer_phone": "0970000000", "delivery_method": "direct",
                "delivery_address": "Test address, Lusaka", "accept_order_terms": "on"}
        with patch("core.views.send_mail"):
            response = self.client.post(reverse("place_order", args=[self.product.slug]), form)
            self.assertEqual(response.status_code, 302)
            self.assertEqual(OrderItem.objects.get().referrer, self.referrer)
            cart, _ = Cart.objects.get_or_create(user=self.buyer)
            CartItem.objects.create(cart=cart, product=self.product, quantity=2)
            response = self.client.post(reverse("checkout_cart"), form)
            self.assertEqual(response.status_code, 302)
        self.assertEqual(OrderItem.objects.filter(referrer=self.referrer).count(), 2)
        self.assertEqual(ReferralReward.objects.count(), 2)
