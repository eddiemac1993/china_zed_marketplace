from django import forms
from .models import SupplierProductRequest


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleFileField(forms.FileField):
    def clean(self, data, initial=None):
        if not data:
            return []

        if isinstance(data, (list, tuple)):
            return [super(MultipleFileField, self).clean(d, initial) for d in data]

        return [super().clean(data, initial)]


class SupplierProductRequestForm(forms.ModelForm):
    images = MultipleFileField(
        widget=MultipleFileInput(attrs={"multiple": True}),
        required=False
    )

    class Meta:
        model = SupplierProductRequest
        fields = [
            "supplier_name",
            "supplier_contact",
            "product_name",
            "description",
            "rmb_price",
        ]


class OrderForm(forms.Form):
    customer_phone = forms.CharField(
        max_length=20,
        label="Phone Number",
        widget=forms.TextInput(attrs={
            "placeholder": "Example: 0970000000"
        })
    )

    customer_note = forms.CharField(
        required=False,
        label="Order Note",
        widget=forms.Textarea(attrs={
            "rows": 4,
            "placeholder": "Any colour, size, model or delivery instructions?"
        })
    )