from django.contrib import admin
from django.db import models
from common.services.huey import HueyDashboardAdmin


class HueyFakeModel(models.Model):
    class Meta:
        managed = False
        verbose_name = "Huey (Tâches en file)"
        verbose_name_plural = "Huey (Tâches en file)"


admin.site.register(HueyFakeModel, HueyDashboardAdmin)
