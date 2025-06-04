from django.core.validators import EmailValidator
from django import forms
from .models import CustomUser, Message
from django.db.models import Q
from django.contrib.auth.forms import UserCreationForm, UserChangeForm
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.contrib.auth.forms import PasswordChangeForm
from common.mixins import BootstrapFormMixin

import logging

logger = logging.getLogger(__name__)


phone_validator = RegexValidator(
    regex=r"^\+?1?\d{9,15}$",
    message="Le numéro de téléphone n'est pas valide. Veuillez entrer un numéro valide.",
)


class CustomUserCreationForm(UserCreationForm):
    email = forms.EmailField(
        required=True,
        label="Email",
        validators=[EmailValidator(message="Veuillez entrer un email valide.")],
    )
    name = forms.CharField(required=True, label="Nom", max_length=100)
    last_name = forms.CharField(required=True, label="Prénom", max_length=100)

    class Meta:
        model = CustomUser
        fields = [
            "username",
            "name",
            "phone",
            "last_name",
            "email",
            "password1",
            "password2",
        ]

    def clean_name(self):
        name = self.cleaned_data.get("name")
        if not name:
            raise ValidationError("Le nom est obligatoire.")
        return name

    def clean_last_name(self):
        last_name = self.cleaned_data.get("last_name")
        if not last_name:
            raise ValidationError("Le prénom est obligatoire.")
        return last_name

    def clean(self):
        cleaned_data = super().clean()
        email = cleaned_data.get("email")
        username = cleaned_data.get("username")
        phone = cleaned_data.get("phone")

        if phone:
            phone_validator(phone)
        conflicts = CustomUser.objects.filter(Q(email=email) | Q(username=username) | Q(phone=phone))

        for user in conflicts:
            if user.email == email:
                self.add_error("email", "Cet email est déjà utilisé.")
            if user.username == username:
                self.add_error("username", "Ce nom d'utilisateur est déjà pris.")
            if user.phone == phone:
                self.add_error("phone", "Ce numéro de téléphone est déjà utilisé.")

        return cleaned_data


class CustomUserChangeForm(UserChangeForm):
    email = forms.EmailField(
        required=True,
        label="Email",
        validators=[EmailValidator(message="Veuillez entrer un email valide.")],
    )

    class Meta:
        model = CustomUser
        fields = ("username", "name", "last_name", "email", "phone")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["username"].disabled = True
        self.fields["name"].disabled = True
        self.fields["last_name"].disabled = True
        self.fields["email"].disabled = True

        # Remove the password field
        if "password" in self.fields:
            self.fields.pop("password", None)

    def clean_phone(self):
        phone = self.cleaned_data.get("phone")
        user = self.instance
        phone_validator(phone)  # this raises ValidationError if invalid
        if CustomUser.objects.filter(phone=phone).exclude(id=user.id).exists():
            raise ValidationError("Ce numéro de téléphone est déjà utilisé par un autre utilisateur.")
        return phone

    # Optional: You can add more custom validation for the is_admin field if needed
    def clean_is_admin(self):
        if "is_admin" not in self.cleaned_data:
            return self.instance.is_admin
        is_admin = self.cleaned_data["is_admin"]
        if not is_admin:
            raise ValidationError("L'utilisateur doit être un administrateur.")
        return is_admin


class MessageForm(forms.ModelForm):
    class Meta:
        model = Message
        fields = ["content"]
        widgets = {
            "content": forms.Textarea(
                attrs={
                    "rows": 3,
                    "placeholder": "Votre message...",
                    "class": "form-control",  # <-- Bootstrap style
                }
            ),
        }
        labels = {
            "content": "",  # No label above the field
        }


class ContactForm(forms.Form):
    name = forms.CharField(label="Nom", max_length=100)
    email = forms.EmailField(label="Email")
    subject = forms.CharField(label="Sujet", max_length=150)
    message = forms.CharField(label="Message", widget=forms.Textarea)

    def __init__(self, *args, **kwargs):
        name = kwargs.pop("name", "")
        email = kwargs.pop("email", "")  # The end date from the view

        super().__init__(*args, **kwargs)

        self.fields["name"].initial = name
        self.fields["email"].initial = email


class CustomPasswordChangeForm(PasswordChangeForm):
    old_password = forms.CharField(
        label="Mot de passe actuel",
        widget=forms.PasswordInput(attrs={"class": "form-control"}),
    )
    new_password1 = forms.CharField(
        label="Nouveau mot de passe",
        widget=forms.PasswordInput(attrs={"class": "form-control"}),
    )
    new_password2 = forms.CharField(
        label="Confirmation du nouveau mot de passe",
        widget=forms.PasswordInput(attrs={"class": "form-control"}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["old_password"].widget.attrs.update({"autocomplete": "current-password"})
        self.fields["new_password1"].widget.attrs.update({"autocomplete": "new-password"})
        self.fields["new_password2"].widget.attrs.update({"autocomplete": "new-password"})


class UserAdminUpdateForm(forms.ModelForm, BootstrapFormMixin):
    email = forms.EmailField(
        required=True, label="Email", validators=[EmailValidator(message="Veuillez entrer un email valide.")]
    )
    is_admin = forms.BooleanField(required=False)
    is_owner = forms.BooleanField(required=False)
    is_owner_admin = forms.BooleanField(required=False)

    class Meta:
        model = CustomUser
        fields = [
            "username",
            "name",
            "last_name",
            "email",
            "phone",
            "is_admin",
            "is_owner",
            "is_owner_admin",
            "stripe_customer_id",
            "stripe_account_id",
        ]
        labels = {
            "name": "Nom",
            "last_name": "Prénom",
            "phone": "Téléphone",
            "is_admin": "Administrateur plateforme",
            "is_owner_admin": "Administrateur de conciergerie",
            "email": "E-mail",
            "is_owner": "Propriétaire",
            "stripe_customer_id": "Compte client Stripe",
            "stripe_account_id": "Compte stripe Connect",
        }

    def clean_stripe_account_id(self):
        customer_id = self.cleaned_data.get("stripe_account_id")
        if (
            customer_id
            and CustomUser.objects.filter(stripe_account_id=customer_id).exclude(pk=self.instance.pk).exists()
        ):
            raise forms.ValidationError("Ce compte Stripe Connect est déjà utilisé.")
        return customer_id

    def clean_stripe_customer_id(self):
        customer_id = self.cleaned_data.get("stripe_customer_id")
        if (
            customer_id
            and CustomUser.objects.filter(stripe_customer_id=customer_id).exclude(pk=self.instance.pk).exists()
        ):
            raise forms.ValidationError("Cet identifiant client Stripe est déjà utilisé.")
        return customer_id

    def clean(self):
        cleaned_data = super().clean()
        for field in ["is_admin", "is_owner", "is_owner_admin"]:
            cleaned_data[field] = bool(self.data.get(field))
        return cleaned_data
