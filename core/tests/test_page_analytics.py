import json,time
from unittest.mock import patch
from django.test import SimpleTestCase,RequestFactory
from django.http import HttpResponse
from django.contrib.auth.models import User
from core.page_analytics import PageAnalyticsMiddleware
from core.privacy_controls import has_optional_consent

class PageAnalyticsTests(SimpleTestCase):
    def test_old_permission_requires_renewal(self):
        r=RequestFactory().get("/");r.COOKIES["czConsent"]=json.dumps({"version":1,"savedAt":time.time()*1000,"analytics":True})
        self.assertFalse(has_optional_consent(r,"analytics"))
    def test_consent_links_page_to_account(self):
        r=RequestFactory().get("/about/?private=excluded");r.user=User(pk=1)
        with patch("core.page_analytics.has_optional_consent",return_value=True),patch("core.page_analytics.MarketplaceEvent.objects.create") as create:
            PageAnalyticsMiddleware(lambda r:HttpResponse("ok"))(r)
        create.assert_called_once_with(event_type="page_view",path="/about/",user=r.user)
    def test_sensitive_pages_are_excluded(self):
        for path in ["/loans/","/checkout/","/admin/","/login/","/password-reset/"]:
            r=RequestFactory().get(path);r.user=User(pk=1)
            with patch("core.page_analytics.has_optional_consent",return_value=True),patch("core.page_analytics.MarketplaceEvent.objects.create") as create:
                PageAnalyticsMiddleware(lambda r:HttpResponse("ok"))(r)
            create.assert_not_called()
    def test_no_permission_no_record(self):
        r=RequestFactory().get("/");r.user=User(pk=1)
        with patch("core.page_analytics.MarketplaceEvent.objects.create") as create:
            PageAnalyticsMiddleware(lambda r:HttpResponse("ok"))(r)
        create.assert_not_called()
