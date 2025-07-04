from django import forms


class StarRadioSelect(forms.RadioSelect):
    template_name = "widgets/star_radio.html"
