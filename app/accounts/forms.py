from django import forms
from django.contrib.auth.forms import UserCreationForm

from .models import User


class RegistrationForm(UserCreationForm):
    email = forms.EmailField(required=True)

    class Meta:
        model = User
        fields = (
            "username",
            "email",
            "first_name",
            "last_name",
        )

    def clean_email(self):
        email = self.cleaned_data["email"].lower()

        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError(
                "Bu elektron poçta eýýäm hasaba alyndy."
            )

        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data["email"].lower()

        if commit:
            user.save()

        return user

class ContactForm(forms.Form):
    subject = forms.CharField(
        max_length=100
    )

    email = forms.EmailField()

    message = forms.CharField(
        widget=forms.Textarea,
        max_length=1000
    )


from django import forms


class TransferForm(forms.Form):
    recipient = forms.CharField(
        max_length=44,
        label="Recipient address"
    )

    amount = forms.DecimalField(
        min_value=0.01,
        max_digits=18,
        decimal_places=2,
        label="Amount"
    )

    def clean_recipient(self):
        recipient = self.cleaned_data["recipient"]

        if not recipient.startswith("tmc_"):
            raise forms.ValidationError(
                "Nädogry TMC salgysy."
            )

        if len(recipient) != 44:
            raise forms.ValidationError(
                "TMC salgysynyň uzynlygy nädogry."
            )

        return recipient



class TransferForm(forms.Form):
    recipient = forms.CharField(max_length=44)

    amount = forms.DecimalField(
        min_value=0.01,
        max_digits=18,
        decimal_places=2
    )

    fee = forms.DecimalField(
        min_value=0,
        max_digits=18,
        decimal_places=2
    )

    def clean(self):
        cleaned_data = super().clean()

        amount = cleaned_data.get("amount")
        fee = cleaned_data.get("fee")

        if amount is not None and fee is not None:
            if fee > amount:
                raise forms.ValidationError(
                    "Komissiýa töleg möçberinden uly bolup bilmez."
                )

        return cleaned_data
