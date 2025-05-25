from django import forms
from logement.models import Logement, City
from .models import HomePageConfig, Service, Testimonial, Commitment, Entreprise


class HomePageConfigForm(forms.ModelForm):
    class Meta:
        model = HomePageConfig
        fields = [
            "nom",
            "description",
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
            "contact_address",
            "contact_phone",
            "contact_email",
            "facebook",
            "instagram",
            "linkedin",
            "logo",
        ]
        widgets = {
            "contact_address": forms.TextInput(attrs={"class": "form-control"}),
            "contact_phone": forms.TextInput(attrs={"class": "form-control"}),
            "contact_email": forms.EmailInput(attrs={"class": "form-control"}),
            "facebook": forms.URLInput(attrs={"class": "form-control"}),
            "instagram": forms.URLInput(attrs={"class": "form-control"}),
            "linkedin": forms.URLInput(attrs={"class": "form-control"}),
            "logo": forms.ClearableFileInput(attrs={"class": "form-control-file"}),
        }
