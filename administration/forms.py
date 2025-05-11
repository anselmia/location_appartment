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
            "bedrooms",
            "fee_per_extra_traveler",
            "cleaning_fee",
            "tax",
        ]
        labels = {
            "name": "Nom du logement",
            "description": "Description",
            "price": "Prix par nuit (€)",
            "max_traveler": "Voyageurs max.",
            "nominal_traveler": "Voyageurs inclus",
            "bedrooms": "Nombre de chambres",
            "fee_per_extra_traveler": "Frais par voyageur supplémentaire (€)",
            "cleaning_fee": "Frais de ménage (€)",
            "tax": "Taxe de séjour (%)",
        }
        help_texts = {
            "nominal_traveler": "Nombre de voyageurs inclus sans frais supplémentaires.",
            "fee_per_extra_traveler": "S'applique si le nombre de voyageurs dépasse ceux inclus.",
        }
        widgets = {
            "description": forms.Textarea(attrs={"rows": 10}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        step_fields = [
            "price",
            "max_traveler",
            "nominal_traveler",
            "bedrooms",
            "fee_per_extra_traveler",
            "cleaning_fee",
        ]
        for field_name in step_fields:
            if field_name in self.fields:
                self.fields[field_name].widget.attrs["step"] = "1"

        self.fields["tax"].widget.attrs["step"] = "0.1"

    def clean(self):
        cleaned_data = super().clean()
        max_traveler = cleaned_data.get("max_traveler")
        nominal_traveler = cleaned_data.get("nominal_traveler")

        if nominal_traveler and max_traveler and nominal_traveler > max_traveler:
            self.add_error(
                "nominal_traveler",
                "Le nombre de voyageurs inclus ne peut pas dépasser le maximum autorisé.",
            )
