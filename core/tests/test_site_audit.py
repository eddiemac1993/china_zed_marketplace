import json
import time
import inspect
from urllib.parse import quote
from unittest.mock import patch
from django.test import SimpleTestCase, RequestFactory
from django.contrib.auth.models import User, AnonymousUser
from core.privacy_controls import has_optional_consent
from core import views
from core.forms import OrderForm, AdvertisementSubmissionForm
from core.models import CustomerProfile

class SiteAuditTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()
    def test_consent_defaults_and_rejects_invalid_values(self):
        request=self.factory.get("/")
        request.user=AnonymousUser()
        for raw in ["", "bad-json", "[]", "null", json.dumps({"version":2,"savedAt":time.time()*1000,"analytics":"true"})]:
            request.COOKIES["czConsent"]=raw
            self.assertFalse(has_optional_consent(request,"analytics"))
    def test_consent_expiration_and_separate_categories(self):
        request=self.factory.get("/")
        request.user=AnonymousUser()
        for age,expected in [(0,True),(181*86400,False),(-3600,False)]:
            request.COOKIES["czConsent"]=quote(json.dumps({"version":2,"savedAt":(time.time()-age)*1000,"analytics":True,"personalization":False}))
            self.assertEqual(has_optional_consent(request,"analytics"),expected)
            self.assertFalse(has_optional_consent(request,"personalization"))
    def test_no_tracking_or_history_query_without_consent(self):
        request=self.factory.get("/")
        request.user=AnonymousUser()
        views.record_marketplace_event(request,"product_view")
        response=views.visible_history_products(request)
        self.assertEqual(json.loads(response.content),{"slugs":[]})
    def test_no_external_ai_without_consent(self):
        request=self.factory.post("/",data=json.dumps({"message":"Hello"}),content_type="application/json")
        request.user=User(username="test")
        with patch("core.views.requests.post") as post, patch("core.views.fallback_assistant_reply",return_value="Local help"):
            response=inspect.unwrap(views.assistant_chat_view)(request)
        post.assert_not_called()
        self.assertEqual(json.loads(response.content)["reply"],"Local help")
    def test_terms_and_image_rights_are_required(self):
        for field in [OrderForm.base_fields["accept_order_terms"],AdvertisementSubmissionForm.base_fields["rights_confirmed"]]:
            self.assertTrue(field.required)
    def test_profile_photo_is_optional(self):
        profile=CustomerProfile(user=User(first_name="A",last_name="B"),phone="260700000000")
        self.assertTrue(profile.is_complete())
        self.assertEqual(profile.completion_percentage(),100)

    def test_opted_in_analytics_omits_identifiers_and_search_text(self):
        request=self.factory.get("/")
        request.user=AnonymousUser()
        with patch("core.views.has_optional_consent",return_value=True), patch("core.views.MarketplaceEvent.objects.create") as create:
            views.record_marketplace_event(request,"search",search_query="private email",order="private",result_count=2)
        create.assert_called_once_with(event_type="search",user=None,path="",result_count=2)
