from django.core.validators import EmailValidator
from django import forms
from .models import CustomUser, Message
from django.contrib.auth.forms import UserCreationForm, UserChangeForm
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.contrib.auth.forms import PasswordChangeForm

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

    # Custom validation for email uniqueness
    def clean_email(self):
        email = self.cleaned_data.get("email")
        if CustomUser.objects.filter(email=email).exists():
            logger.warning(
                f"Tentative d'enregistrement avec un email déjà utilisé : {email}"
            )
            raise ValidationError(
                "Cet email est déjà utilisé. Veuillez en choisir un autre."
            )
        return email

    def clean_username(self):
        username = self.cleaned_data.get("username")
        if CustomUser.objects.filter(username=username).exists():
            raise ValidationError("Ce nom d'utilisateur est déjà pris.")
        return username

    # Ensure that the name and last name are not empty
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

    def clean_phone(self):
        phone = self.cleaned_data.get("phone")
        phone_validator(phone)  # this raises ValidationError if invalid
        if CustomUser.objects.filter(phone=phone).exists():
            raise ValidationError(
                "Ce numéro de téléphone est déjà utilisé. Veuillez en choisir un autre."
            )
        return phone


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

    def clean_phone(self):
        phone = self.cleaned_data.get("phone")
        user = self.instance
        phone_validator(phone)  # this raises ValidationError if invalid
        if CustomUser.objects.filter(phone=phone).exclude(id=user.id).exists():
            raise ValidationError(
                "Ce numéro de téléphone est déjà utilisé par un autre utilisateur."
            )
        return phone

    # Optional: You can add more custom validation for the is_admin field if needed
    def clean_is_admin(self):
        is_admin = self.cleaned_data.get("is_admin")
        if not is_admin:
            raise ValidationError("L'utilisateur doit être un administrateur.")
        return is_admin


class MessageForm(forms.ModelForm):
    class Meta:
        model = Message
        fields = ["content"]
        widgets = {
            "content": forms.Textarea(
                attrs={"rows": 3, "placeholder": "Votre message..."}
            ),
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
