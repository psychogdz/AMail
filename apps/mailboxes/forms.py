import re
from django import forms
from django.conf import settings
from .models import Category, EmailAddress, get_default_domain


class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ['name']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Category name'})
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user

    def clean_name(self):
        name = self.cleaned_data.get('name', '').strip()
        if not name:
            raise forms.ValidationError("Category name cannot be empty.")
        if self.user:
            qs = Category.objects.filter(user=self.user, name=name)
            if self.instance and self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise forms.ValidationError("You already have a category with this name.")
        return name


class EmailAddressForm(forms.Form):
    local_part = forms.CharField(
        max_length=64,
        widget=forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'e.g. netflix'})
    )
    category = forms.ModelChoiceField(
        queryset=Category.objects.none(),
        required=False,
        empty_label='Uncategorized'
    )

    def __init__(self, user, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['category'].queryset = Category.objects.filter(user=user)

    def clean_local_part(self):
        local_part = self.cleaned_data.get('local_part', '').strip().lower()
        if not local_part:
            raise forms.ValidationError("Local part cannot be empty.")

        if len(local_part) == 1:
            if not re.match(r'^[a-z0-9]$', local_part):
                raise forms.ValidationError("Only letters and numbers are allowed.")
        else:
            if not re.match(r'^[a-z0-9][a-z0-9._-]*[a-z0-9]$', local_part):
                raise forms.ValidationError(
                    "Must start and end with a letter or number. "
                    "Only letters, numbers, dots, hyphens, and underscores are allowed."
                )

        reserved = getattr(settings, 'RESERVED_EMAIL_ADDRESSES', [])
        if local_part in reserved:
            raise forms.ValidationError("This email address is reserved and cannot be used.")

        domain = get_default_domain()
        if EmailAddress.objects.filter(local_part=local_part, domain=domain).exists():
            raise forms.ValidationError("This email address is already taken.")

        return local_part


class MoveAddressForm(forms.Form):
    category = forms.ModelChoiceField(
        queryset=Category.objects.none(),
        required=False,
        empty_label='Uncategorized'
    )

    def __init__(self, user, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['category'].queryset = Category.objects.filter(user=user)
