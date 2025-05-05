from django import forms
from .models import Client, Reservation


class ReservationForm(forms.Form):
    name = forms.CharField()
    email = forms.EmailField()
    telephone = forms.CharField()
    date_debut = forms.DateField(widget=forms.TextInput(attrs={"id": "id_date_debut"}))
    date_fin = forms.DateField(widget=forms.TextInput(attrs={"id": "id_date_fin"}))
