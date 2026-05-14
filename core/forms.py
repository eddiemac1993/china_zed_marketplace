from django import forms
from .models import SupplierProductRequest, Order
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm


class PaymentProofForm(forms.ModelForm):
    class Meta:
        model = Order
        fields = ["payment_proof"]

        widgets = {
            "payment_proof": forms.FileInput(attrs={
                "accept": "image/*",
                "class": "form-control",
            })
        }

class CustomUserRegistrationForm(UserCreationForm):
    email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(attrs={
            "class": "form-control",
            "placeholder": "Enter your email"
        })
    )

    username = forms.CharField(
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "placeholder": "Enter username"
        })
    )

    password1 = forms.CharField(
        widget=forms.PasswordInput(attrs={
            "class": "form-control",
            "placeholder": "Enter password"
        })
    )

    password2 = forms.CharField(
        widget=forms.PasswordInput(attrs={
            "class": "form-control",
            "placeholder": "Confirm password"
        })
    )

    class Meta:
        model = User
        fields = ["username", "email", "password1", "password2"]

    def save(self, commit=True):
        user = super().save(commit=False)

        user.email = self.cleaned_data["email"]

        if commit:
            user.save()

        return user

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