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
from logement.models import Logement  # Your model


class LogementSitemap(Sitemap):
    changefreq = "weekly"
    priority = 0.8

    def items(self):
        return Logement.objects.all()

    def location(self, obj):
        return "f/book/"  # or the booking page URL like "/booking/"


sitemaps = {
    "logements": LogementSitemap,
}

urlpatterns = [
    path("admin/", admin.site.urls),  # optional
    path("accounts/", include("accounts.urls", namespace="accounts")),
    path("admin-area/", include("administration.urls", namespace="administration")),
    path("", include("logement.urls", namespace="logement")),  # main site
    path("sitemap.xml", sitemap, {"sitemaps": sitemaps}, name="sitemap"),
]

# Append the static files URLs
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
