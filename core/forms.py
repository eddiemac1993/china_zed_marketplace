from django import forms
from .models import Category, CustomerProductRequest, SupplierProductRequest, Order, CollectionCentre, Biker
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm, PasswordResetForm, SetPasswordForm


class StyledPasswordResetForm(PasswordResetForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["email"].widget.attrs.update({
            "class": "form-control",
            "placeholder": "you@example.com",
        })


class StyledSetPasswordForm(SetPasswordForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["new_password1"].widget.attrs.update({"class": "form-control"})
        self.fields["new_password2"].widget.attrs.update({"class": "form-control"})


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
    marketplace_share_text = forms.CharField(required=False, widget=forms.Textarea(attrs={"class": "form-control", "rows": 3, "placeholder": "Paste an AliExpress or Taobao product link/share text"}), label="Marketplace product link")
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
            "source_platform",
            "source_link",
            "external_image_url",
            "external_gallery_urls",
            "original_product_name",
            "original_description",
            "source_product_id",
            "source_currency",
            "displayed_price_min",
            "displayed_price_max",
            "original_displayed_price",
            "imported_store_name",
            "imported_variant_data",
            "import_status",
            "imported_image_paths",
            "selected_color",
            "selected_size",
            "selected_other_variants",
            "price_confirmed",
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
            "source_platform": forms.HiddenInput(),
            "source_link": forms.HiddenInput(),
            "external_image_url": forms.HiddenInput(),
            "external_gallery_urls": forms.HiddenInput(),
            "original_product_name": forms.HiddenInput(),
            "original_description": forms.HiddenInput(),
            "source_product_id": forms.HiddenInput(),
            "source_currency": forms.HiddenInput(),
            "displayed_price_min": forms.HiddenInput(),
            "displayed_price_max": forms.HiddenInput(),
            "original_displayed_price": forms.HiddenInput(),
            "imported_store_name": forms.HiddenInput(),
            "imported_variant_data": forms.HiddenInput(),
            "import_status": forms.HiddenInput(),
            "imported_image_paths": forms.HiddenInput(),
            "selected_color": forms.TextInput(attrs={"class": "form-control", "placeholder": "Confirm selected colour"}),
            "selected_size": forms.TextInput(attrs={"class": "form-control", "placeholder": "Confirm selected size"}),
            "selected_other_variants": forms.Textarea(attrs={"class": "form-control", "rows": 2, "placeholder": "Model, bundle or other selected options"}),
            "price_confirmed": forms.CheckboxInput(attrs={"class": "terms-checkbox"}),
            "product_type": forms.RadioSelect(attrs={
                "class": "type-radio",
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

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)
        self.fields["supplier_contact"].required = True
        if self.user and self.user.is_staff:
            for field_name in (
                "supplier_name", "supplier_contact", "product_name", "description",
                "category", "rmb_price", "local_price", "stock_quantity",
                "price_confirmed", "selected_color", "selected_size",
                "selected_other_variants",
            ):
                self.fields[field_name].required = False

    def clean(self):
        cleaned_data = super().clean()

        is_staff_draft = bool(self.user and self.user.is_staff)

        product_type = cleaned_data.get("product_type")
        stock_quantity = cleaned_data.get("stock_quantity") or 0
        rmb_price = cleaned_data.get("rmb_price")
        local_price = cleaned_data.get("local_price")
        imported_paths = cleaned_data.get("imported_image_paths") or []
        allowed_prefix = f"supplier_imports/{self.user.pk}/" if self.user else ""
        if not isinstance(imported_paths, list) or any(not isinstance(path, str) or not allowed_prefix or not path.startswith(allowed_prefix) for path in imported_paths):
            self.add_error("imported_image_paths", "Imported image references are invalid. Import the product again.")
            imported_paths = []
        uploaded_images = self.files.getlist("images")
        cover_image = self.files.get("image")
        variant_data = cleaned_data.get("imported_variant_data") or {}

        if product_type == "local" and not is_staff_draft:
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

        if product_type == "preorder" and not is_staff_draft:
            if stock_quantity <= 0:
                self.add_error("stock_quantity", "Please enter the quantity you can supply.")
            if not rmb_price:
                self.add_error(
                    "rmb_price",
                    "Please enter RMB price for China pre-order products."
                )
            if not cleaned_data.get("price_confirmed"):
                self.add_error("price_confirmed", "Confirm the supplier RMB price after selecting the exact variant.")

        if not uploaded_images and not cover_image and not imported_paths:
            self.add_error("images", "Add at least one valid product image before submission.")

        if not is_staff_draft and variant_data.get("colors") and not cleaned_data.get("selected_color"):
            self.add_error("selected_color", "Select or enter the exact colour.")
        if not is_staff_draft and variant_data.get("sizes") and not cleaned_data.get("selected_size"):
            self.add_error("selected_size", "Select or enter the exact size.")

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


ORDER_FORM_INPUT_CLASS = "w-full rounded border border-brand-border px-3.5 py-2.5 text-sm text-brand-ink outline-none transition focus:border-brand-red focus:ring-2 focus:ring-red-100"


class OrderForm(forms.Form):
    customer_phone = forms.CharField(
        max_length=20,
        label="Recipient's Phone Number",
        widget=forms.TextInput(attrs={
            "placeholder": "Example: 0970000000",
            "class": ORDER_FORM_INPUT_CLASS,
        })
    )

    delivery_method = forms.ChoiceField(
        choices=[("collection", "Collect from a Centre"), ("direct", "Direct to Address")],
        initial="collection",
        widget=forms.RadioSelect,
    )

    collection_centre = forms.ModelChoiceField(
        queryset=CollectionCentre.objects.filter(is_active=True, is_deleted=False),
        required=False,
        label="Nearest Collection Centre",
        empty_label="Select a collection centre",
        widget=forms.Select(attrs={"class": ORDER_FORM_INPUT_CLASS}),
    )

    delivery_address = forms.CharField(
        required=False,
        label="Recipient's Delivery Address",
        widget=forms.Textarea(attrs={
            "rows": 3,
            "placeholder": "Street address, area/compound, town/city, and any landmark that helps the courier find you",
            "class": ORDER_FORM_INPUT_CLASS,
        })
    )

    customer_note = forms.CharField(
        required=False,
        label="Order Note",
        widget=forms.Textarea(attrs={
            "rows": 4,
            "placeholder": "Any colour, size, model or delivery instructions?",
            "class": ORDER_FORM_INPUT_CLASS,
        })
    )

    def clean(self):
        cleaned_data = super().clean()
        delivery_method = cleaned_data.get("delivery_method")

        if delivery_method == "direct" and not cleaned_data.get("delivery_address"):
            self.add_error("delivery_address", "Please provide the delivery address.")

        # A collection centre is required for both delivery methods once any
        # centre exists — for "direct" orders it's the staging point a biker
        # dispatches from. Only skip the requirement while the centre list is
        # still empty, so checkout isn't blocked before any centre is seeded.
        if self.fields["collection_centre"].queryset.exists() and not cleaned_data.get("collection_centre"):
            self.add_error("collection_centre", "Please select a collection centre.")

        return cleaned_data


BIKER_FORM_INPUT_CLASS = ORDER_FORM_INPUT_CLASS


class BikerApplicationForm(forms.ModelForm):
    class Meta:
        model = Biker
        fields = ["full_name", "phone", "vehicle_type", "home_centre", "id_number"]
        widgets = {
            "full_name": forms.TextInput(attrs={"class": BIKER_FORM_INPUT_CLASS, "placeholder": "Full name"}),
            "phone": forms.TextInput(attrs={"class": BIKER_FORM_INPUT_CLASS, "placeholder": "Example: 0970000000"}),
            "vehicle_type": forms.Select(attrs={"class": BIKER_FORM_INPUT_CLASS}),
            "home_centre": forms.Select(attrs={"class": BIKER_FORM_INPUT_CLASS}),
            "id_number": forms.TextInput(attrs={"class": BIKER_FORM_INPUT_CLASS, "placeholder": "Optional"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["home_centre"].queryset = CollectionCentre.objects.filter(is_active=True, is_deleted=False)
        self.fields["home_centre"].empty_label = "Select the centre you operate from"
        self.fields["id_number"].required = False
