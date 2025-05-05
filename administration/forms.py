from django import forms
from logement.models import Logement

class LogementForm(forms.ModelForm):
    class Meta:
        model = Logement
        fields = ['name', 'description', 'prix_par_nuit']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 4}),
        }