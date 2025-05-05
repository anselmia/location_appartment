from django import forms
from .models import CustomUser
from django.contrib.auth.forms import UserCreationForm, UserChangeForm


class CustomUserCreationForm(UserCreationForm):
    email = forms.EmailField(required=True, label="Email")

    class Meta:
        model = CustomUser
        fields = ["username", "email", "password1", "password2"]


class CustomUserChangeForm(UserChangeForm):
    email = forms.EmailField(required=True, label="Email")

    class Meta:
        model = CustomUser
        fields = ("username", "email", "is_admin")
