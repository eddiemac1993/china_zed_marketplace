from .models import MarketplaceEvent
from .privacy_controls import has_optional_consent

class PageAnalyticsMiddleware:
    paths={"/", "/about/", "/faq/", "/terms/", "/privacy/", "/cookies/", "/refund-policy/", "/business-details/", "/order-policy/", "/price-list/", "/advertise/", "/saved/", "/profile/", "/request-product/", "/communinity/"}
    def __init__(self,get_response):self.get_response=get_response
    def __call__(self,request):
        response=self.get_response(request)
        if request.method=="GET" and response.status_code==200 and request.path in self.paths and has_optional_consent(request,"analytics") and not request.headers.get("HX-Request"):
            try:
                MarketplaceEvent.objects.create(event_type="page_view",path=request.path,user=request.user if request.user.is_authenticated else None)
            except Exception:
                import logging
                logging.getLogger(__name__).warning("Unable to save optional page analytics")
        return response
