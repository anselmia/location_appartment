from django import forms
from django.utils.translation import gettext_lazy as _

class ReservationForm(forms.Form):
    guest_adult = forms.IntegerField(
        initial=1,
        min_value=1,
        required=True,
        widget=forms.NumberInput(
            attrs={
                "id": "id_guest_adult",
                "class": "form-control",
                "type": "number",  # enables numeric input with up/down arrows
                "inputmode": "numeric",  # mobile: show numeric keypad
                "pattern": "[0-9]*",  # hint for numeric input
                "oninput": "this.value = this.value.replace(/[^0-9]/g, '')",  # restrict manual input
            }
        ),
    )
    guest_minor = forms.IntegerField(
        initial=0,
        min_value=0,
        required=True,
        widget=forms.NumberInput(
            attrs={
                "id": "id_guest_minor",
                "class": "form-control",
                "type": "number",  # enables numeric input with up/down arrows
                "inputmode": "numeric",  # mobile: show numeric keypad
                "pattern": "[0-9]*",  # hint for numeric input
                "oninput": "this.value = this.value.replace(/[^0-9]/g, '')",  # restrict manual input
            }
        ),
    )
    start = forms.DateField(
        widget=forms.DateInput(attrs={"id": "id_start", "class": "form-control", "type": "date"}),
        required=True,
    )
    end = forms.DateField(
        widget=forms.DateInput(attrs={"id": "id_end", "class": "form-control", "type": "date"}),
        required=True,
    )

    class Meta:
        widgets = {
            "start": forms.DateInput(
                attrs={
                    "class": "form-control",
                    "type": "date",
                }  # Ensures date input widget
            ),
            "end": forms.DateInput(
                attrs={
                    "class": "form-control",
                    "type": "date",
                }  # Ensures date input widget
            ),
        }

    def __init__(self, *args, **kwargs):
        start_date = kwargs.pop("start_date", None)  # The start date from the view
        end_date = kwargs.pop("end_date", None)  # The end date from the view
        guest_adult = kwargs.pop("guest_adult", None)
        guest_minor = kwargs.pop("guest_minor", None)
        max_guests = kwargs.pop("max_guests", 8)  # Default to 8 if not provided

        super().__init__(*args, **kwargs)

        # Validators
        self.fields["guest_adult"].max_value = max_guests
        self.fields["guest_minor"].max_value = max_guests - 1
        self.fields["guest_adult"].min_value = 1
        self.fields["guest_minor"].min_value = 0

        # HTML <input max="…"> attributes
        self.fields["guest_adult"].widget.attrs["max"] = max_guests
        self.fields["guest_minor"].widget.attrs["max"] = max_guests - 1

        # Initialize start and end date fields if values are provided
        self.fields["start"].initial = start_date or ""
        self.fields["end"].initial = end_date or ""
        self.fields["guest_adult"].initial = guest_adult or 1
        self.fields["guest_minor"].initial = guest_minor or 0

    def clean(self):
        cleaned_data = super().clean()

        # Pull the numbers (fallback to 0 if the field is empty / missing)
        adult = cleaned_data.get("guest_adult") or 0
        minor = cleaned_data.get("guest_minor") or 0

        # Same cap you injected in __init__
        max_guests = self.fields["guest_adult"].max_value  # or self.MAX_GUESTS, or self.form_max_guests

        if adult + minor > max_guests:
            raise forms.ValidationError(
                _("Le nombre total de voyageurs ne peut pas dépasser %(max)s."),
                params={"max": max_guests},
            )

        return cleaned_data
