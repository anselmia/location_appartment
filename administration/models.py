from django.db import models

# Create your models here.
class SiteVisit(models.Model):
    ip_address = models.GenericIPAddressField()
    user_agent = models.TextField()
    path = models.CharField(max_length=200)
    timestamp = models.DateTimeField(auto_now_add=True)