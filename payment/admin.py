from django.contrib import admin
from payment.models import PaymentTask


class PaymentTaskAdmin(admin.ModelAdmin):
    list_display = [field.name for field in PaymentTask._meta.fields]


admin.site.register(PaymentTask, PaymentTaskAdmin)
