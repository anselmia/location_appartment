import re
from django.core.validators import EmailValidator
from django import forms
from .models import CustomUser, Message
from django.contrib.auth.forms import UserCreationForm, UserChangeForm
from django.core.exceptions import ValidationError


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
            raise ValidationError(
                "Cet email est déjà utilisé. Veuillez en choisir un autre."
            )
        return email

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
        phone_regex = r"^\+?1?\d{9,15}$"  # You can adjust this regex to match your required phone format
        if not re.match(phone_regex, phone):
            raise ValidationError(
                "Le numéro de téléphone n'est pas valide. Veuillez entrer un numéro valide."
            )
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
        fields = ("name", "phone", "last_name", "email")

    def __init__(self, *args, **kwargs):
        name = kwargs.pop("name", "")
        last_name = kwargs.pop("last_name", "")
        email = kwargs.pop("email", "")
        phone = kwargs.pop("phone", "")

        super().__init__(*args, **kwargs)

        # Initialize start and end date fields if values are provided
        self.fields["name"].initial = name
        self.fields["last_name"].initial = last_name
        self.fields["email"].initial = email
        self.fields["phone"].initial = phone

    # Custom validation for email uniqueness during update
    def clean_email(self):
        email = self.cleaned_data.get("email")
        user = self.instance
        if CustomUser.objects.filter(email=email).exclude(id=user.id).exists():
            raise ValidationError(
                "Cet email est déjà utilisé par un autre utilisateur."
            )
        return email

    # Ensure that the username cannot be changed (optional based on requirements)
    def clean_username(self):
        username = self.cleaned_data.get("username")
        if username != self.instance.username:
            raise ValidationError("Le nom d'utilisateur ne peut pas être modifié.")
        return username

    def clean_phone(self):
        phone = self.cleaned_data.get("phone")
        user = self.instance
        phone_regex = r"^\+?1?\d{9,15}$"  # You can adjust this regex to match your required phone format
        if not re.match(phone_regex, phone):
            raise ValidationError(
                "Le numéro de téléphone n'est pas valide. Veuillez entrer un numéro valide."
            )
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
