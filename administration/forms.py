from django import forms
from .models import HomePageConfig, Service, Testimonial, Commitment, Entreprise, SiteConfig

from logement.models import PlatformFeeWaiver, Logement
from accounts.models import CustomUser
from django.db.models import Q

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


class PlatformFeeWaiverForm(forms.ModelForm, BootstrapFormMixin):
    class Meta:
        model = PlatformFeeWaiver
        fields = ["logement", "owner", "max_amount", "end_date"]
        widgets = {
            "logement": forms.Select(attrs={"class": "form-select"}),
            "owner": forms.Select(attrs={"class": "form-select"}),
            "max_amount": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "end_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["logement"].required = False
        self.fields["owner"].required = False
        self.fields["max_amount"].required = False
        self.fields["end_date"].required = False
        self.fields["logement"].queryset = Logement.objects.all().order_by("name")
        self.fields["owner"].queryset = (
            CustomUser.objects.filter(is_active=True)
            .filter(Q(is_owner=True) | Q(is_admin=True))
            .order_by("name", "last_name")
        )
        if self.instance and self.instance.pk and self.instance.end_date:
            self.initial["end_date"] = self.instance.end_date.strftime("%Y-%m-%d")

    def clean(self):
        cleaned_data = super().clean()
        logement = cleaned_data.get("logement")
        owner = cleaned_data.get("owner")
        max_amount = cleaned_data.get("max_amount")
        end_date = cleaned_data.get("end_date")
        if not logement and not owner:
            raise forms.ValidationError("Veuillez sélectionner au moins un logement ou un propriétaire.")
        if not max_amount and not end_date:
            raise forms.ValidationError("Veuillez renseigner un plafond ou une date de fin.")

        # Check for existing active waiver
        qs = PlatformFeeWaiver.objects.all()
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if logement:
            qs = qs.filter(logement=logement)
        if owner:
            qs = qs.filter(owner=owner)
        for waiver in qs:
            if waiver.is_active() if callable(waiver.is_active) else waiver.is_active:
                raise forms.ValidationError("Une exemption active existe déjà pour ce logement ou ce propriétaire.")
        return cleaned_data
