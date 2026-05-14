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
            "product_type",
            "stock_quantity",
            "product_name",
            "description",
            "rmb_price",
            "local_price",
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
            "product_type": forms.Select(attrs={
                "class": "form-control",
            }),
            "stock_quantity": forms.NumberInput(attrs={
                "class": "form-control",
                "placeholder": "Enter quantity available in Zambia",
                "min": "0",
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
                "placeholder": "Price in RMB for China pre-order",
                "step": "0.01",
            }),
            "local_price": forms.NumberInput(attrs={
                "class": "form-control",
                "placeholder": "Local price in ZMW",
                "step": "0.01",
            }),
            "image": forms.ClearableFileInput(attrs={
                "class": "form-control",
                "accept": "image/*",
            }),
        }

    def clean(self):
        cleaned_data = super().clean()

        product_type = cleaned_data.get("product_type")
        stock_quantity = cleaned_data.get("stock_quantity") or 0
        rmb_price = cleaned_data.get("rmb_price")
        local_price = cleaned_data.get("local_price")

        if product_type == "local":
            if stock_quantity <= 0:
                self.add_error(
                    "stock_quantity",
                    "Please enter stock quantity for local products."
                )

            if not local_price:
                self.add_error(
                    "local_price",
                    "Please enter local price in ZMW."
                )

        if product_type == "preorder":
            if not rmb_price:
                self.add_error(
                    "rmb_price",
                    "Please enter RMB price for China pre-order products."
                )

        return cleaned_data


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