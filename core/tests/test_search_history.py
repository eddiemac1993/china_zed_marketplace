import json
import time
from unittest.mock import patch

from django.contrib import admin
from django.contrib.auth.models import User
from django.test import TestCase, RequestFactory, override_settings
from django.urls import reverse

from core.admin import SearchHistoryAdmin
from core.models import MarketplaceEvent, SearchHistory


@override_settings(SECURE_SSL_REDIRECT=False, ALLOWED_HOSTS=["testserver"])
class SearchHistoryTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("searcher")
        self.other = User.objects.create_user("other")
        self.client.force_login(self.user)

    def consent(self, enabled=True):
        self.client.cookies["czConsent"] = json.dumps({"version": 2, "savedAt": time.time()*1000, "analytics": enabled})

    def test_submitted_search_saved_with_user_result_count_and_timestamp(self):
        self.consent()
        response = self.client.get(reverse("home"), {"q": "  purple   sandals  "})
        self.assertEqual(response.status_code, 200)
        event = MarketplaceEvent.objects.get(event_type="zero_search")
        self.assertEqual(event.search_query, "purple sandals")
        self.assertEqual(event.user, self.user)
        self.assertEqual(event.result_count, 0)
        self.assertIsNotNone(event.created_at)

    def test_search_not_stored_without_permission_or_after_rejecting(self):
        for enabled in (None, False):
            if enabled is not None:
                self.consent(enabled)
            self.client.get(reverse("home"), {"q": "sandals"})
        self.assertFalse(MarketplaceEvent.objects.filter(event_type__in=["search", "zero_search"]).exists())

    def test_profile_only_displays_own_searches_and_escapes_terms(self):
        MarketplaceEvent.objects.create(event_type="search", user=self.user, search_query="<script>alert(1)</script>", result_count=2)
        MarketplaceEvent.objects.create(event_type="search", user=self.other, search_query="other-person-secret-query", result_count=0)
        response = self.client.get(reverse("profile"))
        self.assertContains(response, "Recent searches")
        self.assertContains(response, "&lt;script&gt;")
        self.assertNotContains(response, "<script>alert(1)</script>")
        self.assertNotContains(response, "other-person-secret-query")
        self.assertContains(response, "Ask AI assistant")

    def test_admin_search_history_is_scoped_to_nonempty_searches(self):
        expected = MarketplaceEvent.objects.create(event_type="search", search_query="phone", result_count=2)
        MarketplaceEvent.objects.create(event_type="product_view")
        MarketplaceEvent.objects.create(event_type="search", search_query="")
        view = SearchHistoryAdmin(SearchHistory, admin.site)
        request = RequestFactory().get("/")
        self.assertEqual(list(view.get_queryset(request).values_list("id", flat=True)), [expected.pk])
        response = self.client.get(reverse("admin:core_searchhistory_changelist"))
        self.assertEqual(response.status_code, 302)

    def test_staff_profile_and_search_admin_render(self):
        self.user.is_staff = self.user.is_superuser = True
        self.user.save()
        response = self.client.get(reverse("profile"))
        self.assertContains(response, "Customer searches")
        response = self.client.get(reverse("admin:core_searchhistory_changelist"))
        self.assertEqual(response.status_code, 200)

    def test_suggestions_do_not_save_partial_queries(self):
        self.consent()
        self.client.get(reverse("search_suggestions"), {"q": "san"})
        self.assertFalse(MarketplaceEvent.objects.filter(event_type__in=["search", "zero_search"]).exists())
