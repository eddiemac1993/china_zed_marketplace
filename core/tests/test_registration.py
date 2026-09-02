from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse


@override_settings(SECURE_SSL_REDIRECT=False)
class RegistrationEmailFailureTests(TestCase):
    @patch("core.views.send_activation_email", side_effect=OSError("SMTP unavailable"))
    def test_registration_keeps_inactive_user_when_email_delivery_fails(self, _send_email):
        response = self.client.post(
            reverse("register"),
            {
                "email": "retry@example.com",
                "password1": "Str0ngPass!2026",
                "password2": "Str0ngPass!2026",
                "accept_terms": "on",
            },
            follow=True,
        )

        self.assertRedirects(response, reverse("registration_pending"))
        user = get_user_model().objects.get(email="retry@example.com")
        self.assertFalse(user.is_active)
        self.assertContains(response, "Your account was saved")
        self.assertEqual(response.content.count(b"Your account was saved"), 1)

    @patch("core.views.send_activation_email", side_effect=OSError("SMTP unavailable"))
    def test_resend_failure_returns_friendly_error(self, _send_email):
        get_user_model().objects.create_user(
            username="retry-user",
            email="retry@example.com",
            password="Str0ngPass!2026",
            is_active=False,
        )

        response = self.client.post(
            reverse("resend_activation"),
            {"email": "retry@example.com"},
            follow=True,
        )

        self.assertRedirects(response, reverse("registration_pending"))
        self.assertContains(response, "We still could not send")
        self.assertEqual(response.content.count(b"We still could not send"), 1)
