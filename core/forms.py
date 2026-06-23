from django import forms
from .models import CustomerProductRequest, SupplierProductRequest, Order
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
    BLOCKED_EMAIL_DOMAINS = {
        "10minutemail.com",
        "guerrillamail.com",
        "mailinator.com",
        "tempmail.com",
        "tempmail.net",
        "yopmail.com",
    }

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

    accept_terms = forms.BooleanField(
        required=True,
        error_messages={
            "required": "You must accept the Terms & Conditions and Privacy Policy to create an account."
        },
        widget=forms.CheckboxInput(attrs={
            "class": "terms-checkbox",
        })
    )

    class Meta:
        model = User
        fields = ["username", "email", "password1", "password2", "accept_terms"]

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        domain = email.rsplit("@", 1)[-1]

        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("An account with this email already exists.")

        if domain in self.BLOCKED_EMAIL_DOMAINS:
            raise forms.ValidationError("Please use a permanent email address.")

        return email

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
            "category",
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
            "category": forms.Select(attrs={
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


class CustomerProductRequestForm(forms.ModelForm):
    class Meta:
        model = CustomerProductRequest
        fields = [
            "product_name",
            "product_link",
            "source_platform",
            "notes",
            "screenshot",
        ]
        widgets = {
            "product_name": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Optional: product name or short description",
            }),
            "product_link": forms.URLInput(attrs={
                "class": "form-control",
                "placeholder": "Paste product link from Alibaba, Taobao, Temu, 1688, Shein...",
            }),
            "source_platform": forms.Select(attrs={
                "class": "form-control",
            }),
            "notes": forms.Textarea(attrs={
                "class": "form-control",
                "rows": 4,
                "placeholder": "Colour, size, quantity, budget, delivery notes, or anything we should check.",
            }),
            "screenshot": forms.ClearableFileInput(attrs={
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
