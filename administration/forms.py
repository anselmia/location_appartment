from django import forms
from logement.models import Logement


class LogementForm(forms.ModelForm):
    class Meta:
        model = Logement
        fields = [
            "name",
            "description",
            "adresse",
            "price",
            "max_traveler",
            "nominal_traveler",
            "bedrooms",
            "fee_per_extra_traveler",
            "cleaning_fee",
            "tax",
            "cancelation_period",
            "ready_period",
            "entrance_hour_min",
            "entrance_hour_max",
            "leaving_hour",
            "max_days",
            "availablity_period",
            "animals",
        ]
        labels = {
            "name": "Nom du logement",
            "description": "Description",
            "adresse": "Adresse",
            "price": "Prix par nuit (€)",
            "max_traveler": "Voyageurs max.",
            "nominal_traveler": "Voyageurs inclus",
            "bedrooms": "Nombre de chambres",
            "fee_per_extra_traveler": "Frais par voyageur supplémentaire (€)",
            "cleaning_fee": "Frais de ménage (€)",
            "tax": "Taxe de séjour (%)",
            "cancelation_period": "Période limite d'annulation (jours)",
            "ready_period": "Délai avant arrivée (jours)",
            "entrance_hour_min": "Heure d'arrivée (Début)",
            "entrance_hour_max": "Heure d'arrivée (Fin)",
            "leaving_hour": "Heure de départ maximum",
            "max_days": "Durée maximum de séjour (jours)",
            "availablity_period": "Période de disponibilité (mois)",
            "animals": "Animaux de compagnie autorisés",
        }
        help_texts = {
            "nominal_traveler": "Nombre de voyageurs inclus sans frais supplémentaires.",
            "fee_per_extra_traveler": "S'applique si le nombre de voyageurs dépasse ceux inclus.",
        }
        widgets = {
            "description": forms.Textarea(attrs={"rows": 10}),
            "entrance_hour_min": forms.TimeInput(attrs={"type": "time"}),
            "entrance_hour_max": forms.TimeInput(attrs={"type": "time"}),
            "leaving_hour": forms.TimeInput(attrs={"type": "time"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Fields that should have numeric step=1
        step_1_fields = [
            "price",
            "max_traveler",
            "nominal_traveler",
            "bedrooms",
            "fee_per_extra_traveler",
            "cleaning_fee",
            "cancelation_period",
            "ready_period",
            "max_days",
            "availablity_period",
        ]
        for field_name in step_1_fields:
            if field_name in self.fields:
                self.fields[field_name].widget.attrs["step"] = "1"

        # Tax field step should be more precise (0.1%)
        if "tax" in self.fields:
            self.fields["tax"].widget.attrs["step"] = "0.1"

    def clean(self):
        cleaned_data = super().clean()
        max_traveler = cleaned_data.get("max_traveler")
        nominal_traveler = cleaned_data.get("nominal_traveler")

        if max_traveler is not None and nominal_traveler is not None:
            if nominal_traveler > max_traveler:
                self.add_error(
                    "nominal_traveler",
                    "Le nombre de voyageurs inclus ne peut pas dépasser le maximum autorisé.",
                )
