from django import forms
from logement.models import Logement, City
from .models import HomePageConfig, Service, Testimonial, Commitment, Entreprise


class LogementForm(forms.ModelForm):
    class Meta:
        model = Logement
        exclude = ['equipment']  # Prevent accidental overwrites
        fields = [
            "name",
            "description",
            "adresse",
            "ville",
            "price",
            "max_traveler",
            "nominal_traveler",
            "superficie",
            "bathrooms",
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
            "smoking",
            "statut",
            "type",
            "owner",
            "airbnb_link",
            "airbnb_calendar_link",
            "booking_link",
            "booking_calendar_link",
        ]
        labels = {
            "name": "Nom du logement",
            "description": "Description",
            "adresse": "Adresse",
            "ville": "Ville",
            "statut": "Statut",
            "price": "Prix par nuit (€)",
            "max_traveler": "Voyageurs max.",
            "nominal_traveler": "Voyageurs inclus",
            "superficie": "Surface en m²",
            "bathrooms": "Nombre de salle de bain",
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
            "smoking": "Logement fumeur",
            "airbnb_link": "Lien Airbnb",
            "airbnb_calendar_link": "Calendrier Airbnb",
            "booking_link": "Lien Booking",
            "booking_calendar_link": "Calendrier Booking",          
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
            "equipment": forms.CheckboxSelectMultiple,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if "ville" in self.fields:
            self.fields["ville"].queryset = City.objects.all().order_by(
                "code_postal", "name"
            )

        # Fields that should have numeric step=1
        step_1_fields = [
            "price",
            "max_traveler",
            "nominal_traveler",
            "bedrooms",
            "bathrooms",
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


class HomePageConfigForm(forms.ModelForm):
    class Meta:
        model = HomePageConfig
        fields = [
            "nom",
            "devise",
            "banner_image",
            "cta_text",
            "primary_color",
            "font_family",
            "contact_title",
        ]


class ServiceForm(forms.ModelForm):
    class Meta:
        model = Service
        fields = ["title", "icon_class", "description", "background_image"]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 2}),
        }


class TestimonialForm(forms.ModelForm):
    class Meta:
        model = Testimonial
        fields = ["content"]
        widgets = {
            "content": forms.Textarea(attrs={"rows": 3}),
        }


class CommitmentForm(forms.ModelForm):
    class Meta:
        model = Commitment
        fields = fields = ["title", "text", "background_image"]
        widgets = {
            "text": forms.Textarea(attrs={"rows": 3}),
        }


class EntrepriseForm(forms.ModelForm):
    class Meta:
        model = Entreprise
        fields = [
            'contact_address',
            'contact_phone',
            'contact_email',
            'facebook',
            'instagram',
            'linkedin',
            'logo',
        ]
        widgets = {
            'contact_address': forms.TextInput(attrs={'class': 'form-control'}),
            'contact_phone': forms.TextInput(attrs={'class': 'form-control'}),
            'contact_email': forms.EmailInput(attrs={'class': 'form-control'}),
            'facebook': forms.URLInput(attrs={'class': 'form-control'}),
            'instagram': forms.URLInput(attrs={'class': 'form-control'}),
            'linkedin': forms.URLInput(attrs={'class': 'form-control'}),
            'logo': forms.ClearableFileInput(attrs={'class': 'form-control-file'}),
        }