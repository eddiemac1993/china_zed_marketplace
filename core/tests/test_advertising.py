import base64

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from core.models import Advertisement, Product


@override_settings(ALLOWED_HOSTS=["testserver"], SECURE_SSL_REDIRECT=False)
class AdvertisementSubmissionTests(TestCase):
    def setUp(self):
        Product.objects.create(
            name="Grid product",
            description="A product used to verify sponsored grid cards.",
            rmb_price="100.00",
            product_type="preorder",
            status="active",
            is_available=True,
        )

    def test_any_visitor_can_open_advertising_form(self):
        response = self.client.get(reverse("advertise"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Upload my ad")
        self.assertNotContains(response, "Advertiser name")

    def test_public_submission_goes_live_and_appears_as_product_sized_card(self):
        image = SimpleUploadedFile("advert.png", base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
        ), content_type="image/png")
        response = self.client.post(reverse("advertise"), {"image": image})

        advertisement = Advertisement.objects.get()
        self.assertRedirects(response, reverse("advertise_success", kwargs={"ad_id": advertisement.pk}))
        self.assertTrue(advertisement.is_active)
        self.assertIsNotNone(advertisement.display_from)

        success = self.client.get(response["Location"])
        self.assertContains(success, "Your advert is live!")
        self.assertContains(success, advertisement.image.url)

        home = self.client.get(reverse("home"))
        self.assertContains(home, advertisement.image.url)
        self.assertContains(home, "Sponsored")

    def test_future_and_inactive_ads_do_not_appear(self):
        Advertisement.objects.create(
            advertiser_name="Hidden advertiser",
            headline="This should stay hidden",
            cta_url="https://example.com",
            is_active=False,
        )

        home = self.client.get(reverse("home"))
        self.assertNotContains(home, "This should stay hidden")

    def test_homepage_shows_zambian_shopping_shortcuts_and_real_trust_copy(self):
        home = self.client.get(reverse("home"))

        self.assertContains(home, "Pay with Mobile Money")
        self.assertContains(home, "MTN MoMo")
        self.assertContains(home, "TRENDING IN ZAMBIA")
        self.assertContains(home, "Ask on WhatsApp")
        self.assertNotContains(home, "1,247")
        self.assertNotContains(home, "people browsing now")
