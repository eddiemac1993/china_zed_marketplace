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
        widget=MultipleFileInput(attrs={
            "multiple": True,
            "class": "form-control",
            "accept": "image/*",
        }),
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
            "image",
        ]

        widgets = {
            "supplier_name": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Supplier name or shop name",
            }),
            "supplier_contact": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Phone, WhatsApp or WeChat",
            }),
            "product_name": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Product name",
            }),
            "description": forms.Textarea(attrs={
                "class": "form-control",
                "rows": 4,
                "placeholder": "Describe the product (size, colour, model, etc.)",
            }),
            "rmb_price": forms.NumberInput(attrs={
                "class": "form-control",
                "placeholder": "Price in RMB",
                "step": "0.01",
            }),
            "image": forms.ClearableFileInput(attrs={
                "class": "form-control",
                "accept": "image/*",
            }),
        }


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