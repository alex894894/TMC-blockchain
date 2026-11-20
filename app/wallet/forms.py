from django import forms

class TransferForm(forms.Form):
    recipient = forms.CharField(
        max_length=44,
        label="TMC recipient address",
    )

    amount = forms.DecimalField(
        min_value=0.01,
        max_digits=18,
        decimal_places=2,
        label="Amount",
    )

    def clean_recipient(self):
        recipient = self.cleaned_data["recipient"].strip()

        if (
            len(recipient) != 44
            or not recipient.startswith("tmc_")
        ):
            raise forms.ValidationError(
                "Nädogry TMC salgysy."
            )

        return recipient
