from django import forms


class ReservationForm(forms.Form):
    guest = forms.IntegerField(
        initial=1,
        min_value=1,
        required=True,
        widget=forms.NumberInput(attrs={"id": "id_guest", "class": "form-control"}),
    )
    start = forms.DateField(
        widget=forms.TextInput(attrs={"id": "id_start"}), required=True
    )
    end = forms.DateField(widget=forms.TextInput(attrs={"id": "id_end"}), required=True)

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
        if start_date:
            self.fields["start"].initial = start_date
        if end_date:
            self.fields["end"].initial = end_date
        if guest:
            self.fields["guest"].initial = guest

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
