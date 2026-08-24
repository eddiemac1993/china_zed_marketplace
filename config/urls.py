from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.contrib.auth import views as auth_views
from django.contrib.sitemaps import Sitemap
from django.contrib.sitemaps.views import sitemap
from django.http import HttpResponse
from django.views.generic import RedirectView
from django.urls import reverse
from core.models import Product
from core.forms import StyledPasswordResetForm, StyledSetPasswordForm



class StaticViewSitemap(Sitemap):
    priority = 0.7
    changefreq = "weekly"

    def items(self):
        return ["home", "about", "faq", "terms", "privacy", "order_policy", "request_product"]

    def location(self, item):
        return reverse(item)


class ProductSitemap(Sitemap):
    priority = 0.8
    changefreq = "daily"

    def items(self):
        return Product.objects.filter(
            status="active",
            is_available=True,
            is_deleted=False,
        ).only("slug", "updated_at")

    def location(self, product):
        return reverse("product_detail", kwargs={"slug": product.slug})

    def lastmod(self, product):
        return product.updated_at


sitemaps = {
    "static": StaticViewSitemap,
    "products": ProductSitemap,
}


def robots_txt(request):
    content = (
        "User-agent: *\n"
        "Allow: /\n"
        "Disallow: /admin/\n"
        "Disallow: /cart/\n"
        "Disallow: /profile/\n"
        "Sitemap: https://www.chinatozambia.org/sitemap.xml\n"
    )
    return HttpResponse(content, content_type="text/plain; charset=utf-8")


urlpatterns = [
    path("favicon.ico", RedirectView.as_view(url=settings.STATIC_URL + "core/images/market-icon-64.png", permanent=True), name="favicon"),
    path("sitemap.xml", sitemap, {"sitemaps": sitemaps}, name="django.contrib.sitemaps.views.sitemap"),
    path("robots.txt", robots_txt, name="robots_txt"),
    path("admin/", admin.site.urls),
    path("accounts/", include("allauth.urls")),
    path("", include("core.urls")),
    path("events/", include("events.urls")),
    path("price-list/", include("pricelist.urls")),
    path("communinity/", include("communinity.urls")),

    path(
        "password-reset/",
        auth_views.PasswordResetView.as_view(
            template_name="core/password_reset.html",
            email_template_name="core/password_reset_email.txt",
            html_email_template_name="core/password_reset_email.html",
            subject_template_name="core/password_reset_subject.txt",
            success_url="/password-reset/done/",
            form_class=StyledPasswordResetForm,
        ),
        name="password_reset",
    ),

    path(
        "password-reset/done/",
        auth_views.PasswordResetDoneView.as_view(
            template_name="core/password_reset_done.html"
        ),
        name="password_reset_done",
    ),

    path(
        "reset/<uidb64>/<token>/",
        auth_views.PasswordResetConfirmView.as_view(
            template_name="core/password_reset_confirm.html",
            success_url="/reset/done/",
            form_class=StyledSetPasswordForm,
        ),
        name="password_reset_confirm",
    ),

    path(
        "reset/done/",
        auth_views.PasswordResetCompleteView.as_view(
            template_name="core/password_reset_complete.html"
        ),
        name="password_reset_complete",
    ),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

urlpatterns += [path('webpush/', include('webpush.urls'))]
