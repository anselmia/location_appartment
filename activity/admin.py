from django.contrib import admin
from activity.models import Activity, ActivityPhoto, Partners, Price, CloseDate

# Register your models here.
admin.site.register(Activity)
admin.site.register(ActivityPhoto)
admin.site.register(Partners)
admin.site.register(Price)
admin.site.register(CloseDate)
