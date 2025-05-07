from django import forms


class ReservationForm(forms.Form):
    name = forms.CharField(required=True)
    last_name = forms.CharField(required=True)
    email = forms.EmailField(required=True)
    phone = forms.CharField(required=True)
    guest = forms.IntegerField(
        initial=1,
        min_value=1,
        required=True,
        widget=forms.NumberInput(attrs={'id': 'id_guest', 'class': 'form-control'})
    )
    start = forms.DateField(
        widget=forms.TextInput(attrs={"id": "id_start"}), required=True
    )
    end = forms.DateField(widget=forms.TextInput(attrs={"id": "id_end"}), required=True)

    def __init__(self, *args, **kwargs):
        # Extract user and date parameters from kwargs
        user = kwargs.pop(
            "user", None
        )  # Optional: If user is passed during form initialization
        start_date = kwargs.pop("start_date", None)  # The start date from the view
        end_date = kwargs.pop("end_date", None)  # The end date from the view
        max_guests = kwargs.pop("max_guests", 8)  # Default to 8 if not provided

        super().__init__(*args, **kwargs)

        # Ensure fields are initialized with empty string if user is not authenticated
        if user and user.is_authenticated:
            self.fields["name"].initial = user.name or ""
            self.fields["last_name"].initial = user.last_name or ""
            self.fields["email"].initial = user.email or ""
            self.fields["phone"].initial = user.phone or ""
        else:
            self.fields["name"].initial = ""
            self.fields["last_name"].initial = ""
            self.fields["email"].initial = ""
            self.fields["phone"].initial = ""

        # Set the dynamic max_value for the guest field
        self.fields["guest"].max_value = max_guests
        self.fields["guest"].widget.attrs["max"] = max_guests  # Set the 'max' attribute in the widget

        # Initialize start and end date fields if values are provided
        if start_date:
            self.fields["start"].initial = start_date
        if end_date:
            self.fields["end"].initial = end_date

    def clean_guest(self):
        guest = self.cleaned_data.get('guest')
        max_guests = self.fields['guest'].max_value  # Ensure it's the same max_value you want
        if guest > max_guests:
            raise forms.ValidationError(f"Le nombre de voyageurs ne peut pas dépasser {max_guests}.")
        return guest