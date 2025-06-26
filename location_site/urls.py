"""
URL configuration for location_site project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/4.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.contrib.sitemaps.views import sitemap
from django.contrib.sitemaps import Sitemap
from logement.models import Logement
from activity.models import Activity
from django.urls import reverse
from django.views.generic import TemplateView


class LogementSitemap(Sitemap):
    changefreq = "weekly"
    priority = 0.8
    protocol = "https"

    def items(self):
        return Logement.objects.all()

    def location(self, obj):
        return reverse("reservation:book_logement", kwargs={"pk": obj.id})


class ActivitySitemap(Sitemap):
    changefreq = "weekly"
    priority = 0.8
    protocol = "https"

    def items(self):
        return Activity.objects.all()

    def location(self, obj):
        return reverse("reservation:book_activity", kwargs={"pk": obj.id})


class StaticViewSitemap(Sitemap):
    priority = 0.5
    changefreq = "monthly"
    protocol = "https"

    def items(self):
        return [
            "common:home",
            "accounts:contact",
            "logement:logement_search",
            "activity:search",
            "common:legal_rental",
            "common:cgu",
            "common:confidentiality",
            "common:cgv",
            "common:join_owner",
            "common:join_user",
        ]

    def location(self, item):
        return reverse(item)


sitemaps = {
    "logements": LogementSitemap,
    "activities": ActivitySitemap,
    "static": StaticViewSitemap,
}

urlpatterns = [
    path("", include("common.urls", namespace="common")),  # main site
    path("admin/", admin.site.urls),  # optional
    path("accounts/", include("accounts.urls", namespace="accounts")),
    path("activity/", include("activity.urls", namespace="activity")),
    path("admin-area/", include("administration.urls", namespace="administration")),
    path("conciergerie/", include("conciergerie.urls", namespace="conciergerie")),
    path("logement/", include("logement.urls", namespace="logement")),
    path("partner/", include("partner.urls", namespace="partner")),
    path("payment/", include("payment.urls", namespace="payment")),
    path("reservation/", include("reservation.urls", namespace="reservation")),
    path(
        "sitemap.xml",
        sitemap,
        {"sitemaps": sitemaps},
        name="sitemap",
    ),
    path("robots.txt", TemplateView.as_view(template_name="robots.txt", content_type="text/plain")),
]

# Append the static files URLs
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)


handler400 = "common.views.custom_bad_request"
handler403 = "common.views.custom_permission_denied"
handler404 = "common.views.custom_page_not_found"
handler500 = "common.views.custom_server_error"
