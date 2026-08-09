from django import forms
from .models import EventRegistration


class EventRegistrationForm(forms.ModelForm):
    class Meta:
        model = EventRegistration
        fields = [
            "full_name",
            "phone",
            "email",
            "church_name",
            "location",
            "notes",
        ]

        widgets = {
            "full_name": forms.TextInput(attrs={
                "class": "ev-input",
                "placeholder": "Your full name",
            }),
            "phone": forms.TextInput(attrs={
                "class": "ev-input",
                "placeholder": "Example: 0970000000",
            }),
            "email": forms.EmailInput(attrs={
                "class": "ev-input",
                "placeholder": "you@example.com",
            }),
            "church_name": forms.TextInput(attrs={
                "class": "ev-input",
                "placeholder": "Church or organisation name",
            }),
            "location": forms.TextInput(attrs={
                "class": "ev-input",
                "placeholder": "Town or city",
            }),
            "notes": forms.Textarea(attrs={
                "class": "ev-input",
                "rows": 4,
                "placeholder": "Travel needs, how many people are coming, dietary needs...",
            }),
        }
