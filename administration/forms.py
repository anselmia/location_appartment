from django import forms
from logement.models import Logement


class LogementForm(forms.ModelForm):
    class Meta:
        model = Logement
        fields = [
            "name",
            "description",
            "price",
            "max_traveler",
            "nominal_traveler",
            "fee_per_extra_traveler",
            "cleaning_fee",
            "tax",
        ]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 4}),
        }
