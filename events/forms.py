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