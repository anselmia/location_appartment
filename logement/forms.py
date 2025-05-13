from django import forms
from logement.models import Discount, Logement


class ReservationForm(forms.Form):
    guest = forms.IntegerField(
        initial=1,
        min_value=1,
        required=True,
        widget=forms.NumberInput(attrs={"id": "id_guest", "class": "form-control"}),
    )
    start = forms.DateField(
        widget=forms.DateInput(
            attrs={"id": "id_start", "class": "form-control", "type": "date"}
        ),
        required=True,
    )
    end = forms.DateField(
        widget=forms.DateInput(
            attrs={"id": "id_end", "class": "form-control", "type": "date"}
        ),
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
        guest = kwargs.pop("guest", None)
        max_guests = kwargs.pop("max_guests", 8)  # Default to 8 if not provided

        super().__init__(*args, **kwargs)

        # Set the dynamic max_value for the guest field
        self.fields["guest"].max_value = max_guests
        self.fields["guest"].widget.attrs[
            "max"
        ] = max_guests  # Set the 'max' attribute in the widget

        # Initialize start and end date fields if values are provided
        self.fields["start"].initial = start_date or ""
        self.fields["end"].initial = end_date or ""
        self.fields["guest"].initial = guest or 1

    def clean_guest(self):
        guest = self.cleaned_data.get("guest")
        max_guests = self.fields[
            "guest"
        ].max_value  # Ensure it's the same max_value you want
        if guest > max_guests:
            raise forms.ValidationError(
                f"Le nombre de voyageurs ne peut pas dépasser {max_guests}."
            )
        return guest


class DiscountForm(forms.ModelForm):
    class Meta:
        model = Discount
        fields = [
            "discount_type",
            "value",
            "min_nights",
            "days_before",
            "start_date",
            "end_date",
        ]
        widgets = {
            "discount_type": forms.Select(
                attrs={"class": "form-select", "required": True}
            ),
            "value": forms.NumberInput(
                attrs={"class": "form-control", "step": "0.1", "required": True}
            ),
            "min_nights": forms.NumberInput(
                attrs={"class": "form-control", "step": "1"}
            ),
            "days_before": forms.NumberInput(
                attrs={"class": "form-control", "step": "1"}
            ),
            "start_date": forms.DateInput(
                attrs={"class": "form-control", "type": "date"}
            ),
            "end_date": forms.DateInput(
                attrs={"class": "form-control", "type": "date"}
            ),
        }

    def __init__(self, *args, **kwargs):
        # Check if update_id is passed to handle the update logic
        update_id = kwargs.pop("update_id", None)
        super().__init__(*args, **kwargs)

        if update_id:
            self.instance = Discount.objects.get(id=update_id)

    def clean(self):
        cleaned_data = super().clean()
        dt = cleaned_data.get("discount_type")
        logement = Logement.objects.first()

        # Ensure discount type is unique for this logement
        if logement and dt:
            existing_discount = (
                Discount.objects.filter(logement=logement, discount_type=dt)
                .exclude(id=self.instance.id if self.instance else None)
                .exists()
            )
            if existing_discount:
                self.add_error(
                    "discount_type",
                    "Ce type de réduction est déjà associé à ce logement.",
                )

        if dt:
            if dt.requires_min_nights and not cleaned_data.get("min_nights"):
                self.add_error(
                    "min_nights", "Ce champ est requis pour ce type de réduction."
                )

            if dt.requires_days_before and not cleaned_data.get("days_before"):
                self.add_error(
                    "days_before", "Ce champ est requis pour ce type de réduction."
                )

            if dt.requires_date_range:
                if not cleaned_data.get("start_date") or not cleaned_data.get(
                    "end_date"
                ):
                    self.add_error(
                        "start_date", "Les dates sont requises pour ce type."
                    )
                    self.add_error("end_date", "Les dates sont requises pour ce type.")
