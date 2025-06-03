# admin/huey_dashboard.py
from django.contrib import admin
from django.urls import path
from django.http import JsonResponse
from huey import RedisHuey

# Le même nom que dans settings.py
huey = RedisHuey("location_site")


class HueyDashboardAdmin(admin.ModelAdmin):
    change_list_template = "admin/huey_dashboard.html"

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path("status/", self.admin_site.admin_view(self.huey_status_view)),
        ]
        return custom_urls + urls

    def huey_status_view(self, request):
        inspector = huey.inspect()
        data = {
            "scheduled": inspector.scheduled(),
            "periodic": inspector.periodic(),
            "active": inspector.active(),
            "reserved": inspector.reserved(),
            "revoked": inspector.revoked(),
        }
        return JsonResponse(data)
