import re

from django import forms
from activity.models import Activity, ActivityRating
from common.forms import StarRadioSelect


class ActivityForm(forms.ModelForm):
    def __init__(self, *args, owner=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._owner = owner

    class Meta:
        model = Activity
        exclude = ["owner", "created_at", "updated_at"]
        labels = {
            "name": "Nom de l'activité",
            "description": "Description de l'activité",
            "detail": "Détails de l'activité",
            "duration": "Durée (minutes)",
            "location": "Ville",
            "category": "Catégorie",
            "start": "Heure de début",
            "end": "Heure de fin",
            "day_of_week": "Jour de la semaine",
            "ready_period": "Délai entre deux activités (minutes)",
            "nominal_guests": "Nombre de participants par défaut",
            "fee_per_extra_guest": "Frais par participant supplémentaire (€)",
            "max_participants": "Nombre maximum de participants",
            "cancelation_period": "Délai d'annulation (jours)",
            "availability_period": "Préavis (jours)",
            "price": "Prix (€)",
            "is_active": "Activité active ?",
            "fixed_slots": "Horraires Fixes ?",
        }
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Nom de l'activité"}),
            "description": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 4,
                    "placeholder": "Décrivez l'activité, le déroulement, les points forts...",
                }
            ),
            "detail": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 4,
                    "placeholder": "Détails supplémentaires sur l'activité, les conditions particulières, etc.",
                }
            ),
            "duration": forms.NumberInput(attrs={"class": "form-control", "placeholder": "Durée totale en minutes"}),
            "location": forms.Select(attrs={"class": "form-select", "placeholder": "Choisissez la ville"}),
            "category": forms.Select(attrs={"class": "form-select", "placeholder": "Choisissez la catégorie"}),
            "start": forms.TimeInput(attrs={"class": "form-control", "type": "time", "placeholder": "Heure de début"}),
            "end": forms.TimeInput(attrs={"class": "form-control", "type": "time", "placeholder": "Heure de fin"}),
            "days_of_week": forms.CheckboxSelectMultiple(attrs={"class": "form-check-input"}),
            "ready_period": forms.NumberInput(
                attrs={"class": "form-control", "placeholder": "Délai entre deux activités (minutes)"}
            ),
            "nominal_guests": forms.NumberInput(
                attrs={"class": "form-control", "placeholder": "Nombre de participants par défaut"}
            ),
            "fee_per_extra_guest": forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Frais par participant supplémentaire (€)",
                    "step": "0.01",
                }
            ),
            "max_participants": forms.NumberInput(
                attrs={"class": "form-control", "placeholder": "Nombre maximum de participants autorisés"}
            ),
            "cancelation_period": forms.NumberInput(
                attrs={"class": "form-control", "placeholder": "Délai d'annulation en jours"}
            ),
            "availability_period": forms.NumberInput(
                attrs={"class": "form-control", "placeholder": "Nombre de jours nécessaires à la préparation"}
            ),
            "price": forms.NumberInput(
                attrs={"class": "form-control", "placeholder": "Prix par participant (€)", "step": "0.01"}
            ),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "fixed_slots": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "manual_time_slots": forms.Textarea(
                attrs={"class": "form-control", "rows": 3, "placeholder": "Exemple :\n09:00\n11:00\n14:30"}
            ),
        }

    def clean(self):
        cleaned_data = super().clean()
        is_active = cleaned_data.get("is_active")
        owner = self._owner

        fixed_slots = cleaned_data.get("fixed_slots")
        manual_time_slots = cleaned_data.get("manual_time_slots", "")
        ready_period = cleaned_data.get("ready_period")

        # Validation: only one mode must be filled
        if fixed_slots:
            # Manual slots required
            if not manual_time_slots.strip():
                self.add_error("manual_time_slots", "Veuillez renseigner au moins un créneau horaire.")
            else:
                # Validate each line is HH:MM
                for line in manual_time_slots.strip().splitlines():
                    if not re.match(r"^([01]\d|2[0-3]):[0-5]\d$", line.strip()):
                        self.add_error(
                            "manual_time_slots", f"Format invalide pour le créneau : {line.strip()} (attendu HH:MM)"
                        )
            cleaned_data["ready_period"] = None
        else:
            # ready_period required
            if not ready_period:
                self.add_error("ready_period", "Veuillez renseigner un délai entre deux activités.")
            cleaned_data["manual_time_slots"] = None

        if is_active and not self.instance.pk:  # Seulement à la création
            if not owner:
                self.add_error(None, "L'activité ne peut pas être ouverte sans propriétaire.")
            else:
                if not getattr(owner, "stripe_account_id", None):
                    self.add_error(None, "Le propriétaire doit avoir un compte Stripe connecté.")
        return cleaned_data


class ActivityRatingForm(forms.ModelForm):
    class Meta:
        model = ActivityRating
        fields = ["stars", "comment"]
        widgets = {
            "stars": StarRadioSelect(choices=[(i, "") for i in range(1, 6)]),
            "comment": forms.Textarea(attrs={"rows": 3, "placeholder": "Votre commentaire (optionnel)"}),
        }
        labels = {
            "stars": "Note globale",
            "comment": "Votre commentaire",
        }