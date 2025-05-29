from django import forms
from logement.models import Discount, Logement, City
from accounts.models import CustomUser
from decimal import Decimal


class LogementForm(forms.ModelForm):
    class Meta:
        model = Logement
        exclude = ["equipment"]  # Prevent accidental overwrites
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
            "tax_max",
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
            "admin",
            "airbnb_link",
            "airbnb_calendar_link",
            "booking_link",
            "booking_calendar_link",
            "caution",
            "beds",
            "map_link",
            "admin_fee",
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
            "beds": "Nombre de lits",
            "fee_per_extra_traveler": "Frais par voyageur supplémentaire (€)",
            "cleaning_fee": "Frais de ménage (€)",
            "tax": "Taxe de séjour (%)",
            "tax_max": "Taxe de séjour Max / Personne / Jour (€)",
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
            "caution": "Dépôt de garantie (€)",
            "map_link": "Lien Google Map",
            "owner": "Propriétaire",
            "admin": "Administrateur du logement",
            "admin_fee": "Frais de gestion Administrateur (%)",
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
            "map_link": forms.Textarea(attrs={"rows": 2}),
            "admin": forms.Select(attrs={"class": "form-control select2"}),
            "owner": forms.Select(attrs={"class": "form-control select2"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-control")

        if "ville" in self.fields:
            self.fields["ville"].queryset = City.objects.all().order_by("code_postal", "name")

        if "admin" in self.fields:
            self.fields["admin"].queryset = CustomUser.objects.filter(is_owner_admin=True).order_by("username")

        if "owner" in self.fields:
            self.fields["owner"].queryset = CustomUser.objects.filter(is_owner=True).order_by("username")

        # Fields that should have numeric step=1
        step_1_fields = [
            "price",
            "max_traveler",
            "nominal_traveler",
            "bedrooms",
            "bathrooms",
            "beds" "fee_per_extra_traveler",
            "cleaning_fee",
            "cancelation_period",
            "ready_period",
            "max_days",
            "availablity_period",
            "caution",
        ]
        for field_name in step_1_fields:
            if field_name in self.fields:
                self.fields[field_name].widget.attrs["step"] = "1"
                self.fields[field_name].widget.attrs.update({"type": "number"})

        # Tax field step should be more precise (0.1%)
        if "tax" in self.fields:
            self.fields["tax"].widget.attrs["step"] = "0.1"
        if "admin_fee" in self.fields and self.instance.pk:
            self.fields["admin_fee"].initial = float(self.instance.admin_fee) * 100
            self.fields["admin_fee"].widget.attrs["step"] = "0.1"

    def clean(self):
        cleaned_data = super().clean()
        max_traveler = cleaned_data.get("max_traveler")
        nominal_traveler = cleaned_data.get("nominal_traveler")
        admin_fee = cleaned_data.get("admin_fee")
        if admin_fee is not None:
            cleaned_data["admin_fee"] = admin_fee / Decimal("100")

        if max_traveler is not None and nominal_traveler is not None:
            if nominal_traveler > max_traveler:
                self.add_error(
                    "nominal_traveler",
                    "Le nombre de voyageurs inclus ne peut pas dépasser le maximum autorisé.",
                )

        caution = cleaned_data.get("caution")
        if caution is not None and caution < 0:
            self.add_error("caution", "Le montant de la caution ne peut pas être négatif.")

        statut = cleaned_data.get("statut")
        owner = cleaned_data.get("owner")
        admin = cleaned_data.get("admin")

        if statut == "open":
            if not owner:
                self.add_error("owner", "Le logement ne peut pas être ouvert sans propriétaire.")
            else:
                if not getattr(owner, "stripe_account_id", None):
                    self.add_error("owner", "Le propriétaire doit avoir un compte Stripe connecté.")

            if admin:
                if not getattr(admin, "stripe_account_id", None):
                    self.add_error(
                        "admin",
                        f"L'administrateur '{admin.username}' n'a pas de compte Stripe connecté.",
                    )


class ReservationForm(forms.Form):
    guest = forms.IntegerField(
        initial=1,
        min_value=1,
        required=True,
        widget=forms.NumberInput(
            attrs={
                "id": "id_guest",
                "class": "form-control",
                "type": "number",  # enables numeric input with up/down arrows
                "inputmode": "numeric",  # mobile: show numeric keypad
                "pattern": "[0-9]*",  # hint for numeric input
                "oninput": "this.value = this.value.replace(/[^0-9]/g, '')",  # restrict manual input
            }
        ),
    )
    start = forms.DateField(
        widget=forms.DateInput(attrs={"id": "id_start", "class": "form-control", "type": "date"}),
        required=True,
    )
    end = forms.DateField(
        widget=forms.DateInput(attrs={"id": "id_end", "class": "form-control", "type": "date"}),
        required=True,
    )

    class Meta:
        widgets = {
            "start": forms.DateInput(
                attrs={
                    "class": "form-control",
                    "type": "date",
                }  # Ensures date input widget
            ),
            "end": forms.DateInput(
                attrs={
                    "class": "form-control",
                    "type": "date",
                }  # Ensures date input widget
            ),
        }

    def __init__(self, *args, **kwargs):
        start_date = kwargs.pop("start_date", None)  # The start date from the view
        end_date = kwargs.pop("end_date", None)  # The end date from the view
        guest = kwargs.pop("guest", None)
        max_guests = kwargs.pop("max_guests", 8)  # Default to 8 if not provided

        super().__init__(*args, **kwargs)

        # Set the dynamic max_value for the guest field
        self.fields["guest"].max_value = max_guests
        self.fields["guest"].widget.attrs["max"] = max_guests  # Set the 'max' attribute in the widget

        # Initialize start and end date fields if values are provided
        self.fields["start"].initial = start_date or ""
        self.fields["end"].initial = end_date or ""
        self.fields["guest"].initial = guest or 1

    def clean_guest(self):
        guest = self.cleaned_data.get("guest")
        max_guests = self.fields["guest"].max_value  # Ensure it's the same max_value you want
        if guest > max_guests:
            raise forms.ValidationError(f"Le nombre de voyageurs ne peut pas dépasser {max_guests}.")
        return guest


class DiscountForm(forms.ModelForm):
    class Meta:
        model = Discount
        fields = [
            "discount_type",
            "name",
            "value",
            "min_nights",
            "exact_nights",
            "days_before_min",
            "days_before_max",
            "start_date",
            "end_date",
        ]
        widgets = {
            "discount_type": forms.Select(
                attrs={
                    "class": "form-select",
                    "required": True,
                    "id": "discount-type-select",
                }
            ),
            "name": forms.TextInput(attrs={"class": "form-control", "required": True}),
            "value": forms.NumberInput(attrs={"class": "form-control", "step": "0.1", "required": True}),
            "min_nights": forms.NumberInput(attrs={"class": "form-control", "step": "1"}),
            "exact_nights": forms.NumberInput(attrs={"class": "form-control", "step": "1"}),
            "days_before_min": forms.NumberInput(attrs={"class": "form-control", "step": "1"}),
            "days_before_max": forms.NumberInput(attrs={"class": "form-control", "step": "1"}),
            "start_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "end_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
        }

    def __init__(self, *args, **kwargs):
        update_id = kwargs.pop("update_id", None)
        super().__init__(*args, **kwargs)
        if update_id:
            self.instance = Discount.objects.get(id=update_id)

    def clean(self):
        cleaned_data = super().clean()
        dt = cleaned_data.get("discount_type")
        logement = self.instance.logement if self.instance.pk else Logement.objects.first()

        if logement and dt:
            existing_discount = (
                Discount.objects.filter(logement=logement, discount_type=dt)
                .exclude(id=self.instance.id if self.instance else None)
                .exists()
            )

            if existing_discount:
                self.add_error(
                    "discount_type",
                    "Ce type de réduction est déjà associé à ce logement.",
                )

        if dt:
            # You can set these boolean flags in your DiscountType model
            if getattr(dt, "requires_min_nights", False) and not cleaned_data.get("min_nights"):
                self.add_error("min_nights", "Ce champ est requis pour ce type de réduction.")

            if getattr(dt, "requires_days_before", False) and not (
                cleaned_data.get("days_before_min") or cleaned_data.get("days_before_max")
            ):
                self.add_error(
                    "days_before_min",
                    "Un critère de délai est requis (avant ou après).",
                )

            if getattr(dt, "requires_date_range", False):
                if not cleaned_data.get("start_date"):
                    self.add_error("start_date", "La date de début est requise.")
                if not cleaned_data.get("end_date"):
                    self.add_error("end_date", "La date de fin est requise.")
