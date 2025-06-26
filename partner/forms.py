from django import forms
from partner.models import Partners


class PartnerForm(forms.ModelForm):
    class Meta:
        model = Partners
        exclude = ["user", "validated", "date_creation"]  # ← important ici
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Nom du partenaire"}),
            "logo": forms.ClearableFileInput(attrs={"class": "form-control"}),
            "description": forms.Textarea(
                attrs={"class": "form-control", "rows": 4, "placeholder": "Description du partenaire"}
            ),
            "adresse": forms.Textarea(attrs={"class": "form-control", "rows": 3, "placeholder": "Adresse postale"}),
            "code_postal": forms.TextInput(attrs={"class": "form-control", "placeholder": "Code postal"}),
            "ville": forms.Select(attrs={"class": "form-select"}),
            "pays": forms.TextInput(attrs={"class": "form-control", "placeholder": "France"}),
            "telephone": forms.TextInput(attrs={"class": "form-control", "placeholder": "Numéro de téléphone"}),
            "email": forms.EmailInput(attrs={"class": "form-control", "placeholder": "Email"}),
            "forme_juridique": forms.TextInput(attrs={"class": "form-control", "placeholder": "SASU, SARL, etc."}),
            "siret": forms.TextInput(attrs={"class": "form-control", "placeholder": "Numéro SIRET"}),
            "nom_representant": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "Nom du représentant légal"}
            ),
            "email_representant": forms.EmailInput(
                attrs={"class": "form-control", "placeholder": "Email du représentant"}
            ),
            "telephone_representant": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "Téléphone du représentant"}
            ),
            "actif": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

