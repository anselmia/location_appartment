from rest_framework import serializers
from activity.models import Price


class DailyPriceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Price
        fields = ["id", "date", "value"]
