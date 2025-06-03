from django import forms
from .models import HomePageConfig, Service, Testimonial, Commitment, Entreprise, SiteConfig
from django.contrib.auth import get_user_model

from common.mixins import BootstrapFormMixin


class HomePageConfigForm(forms.ModelForm, BootstrapFormMixin):
    class Meta:
        model = HomePageConfig
        fields = [
            "description",
            "devise",
            "banner_image",
            "cta_text",
            "primary_color",
            "font_family",
            "contact_title",
        ]


class SiteConfigForm(forms.ModelForm, BootstrapFormMixin):
    class Meta:
        model = SiteConfig
        fields = [
            "sms",
        ]


class ServiceForm(forms.ModelForm, BootstrapFormMixin):
    class Meta:
        model = Service
        fields = ["title", "icon_class", "description", "background_image"]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 2}),
        }


class TestimonialForm(forms.ModelForm, BootstrapFormMixin):
    class Meta:
        model = Testimonial
        fields = ["content"]
        widgets = {
            "content": forms.Textarea(attrs={"rows": 3}),
        }


class CommitmentForm(forms.ModelForm, BootstrapFormMixin):
    class Meta:
        model = Commitment
        fields = ["title", "text", "background_image"]
        widgets = {
            "text": forms.Textarea(attrs={"rows": 3}),
        }


class EntrepriseForm(forms.ModelForm, BootstrapFormMixin):
    class Meta:
        model = Entreprise
        fields = [
            "name",
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

    def clean_contact_email(self):
        email = self.cleaned_data.get("contact_email")
        if not email:
            raise forms.ValidationError("L'adresse e-mail est obligatoire.")
        return email


CustomUser = get_user_model()
