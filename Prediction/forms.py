from django import forms
from django.core.exceptions import ValidationError

DIRECTION_CHOICE = (
    ('up', 'UP'),
    ('down', 'DOWN'),
)


class PredictionForm(forms.Form):
    amount = forms.IntegerField(
        min_value=1,
        widget=forms.NumberInput(attrs={
            'placeholder': 'Enter Amount',
            'class': 'form-control'
        })
    )

    direction = forms.ChoiceField(
        choices=DIRECTION_CHOICE,
        widget=forms.HiddenInput()
    )

    def clean_amount(self):
        amount = self.cleaned_data.get('amount')
        if amount <= 0:
            raise ValidationError("Amount must be greater than 0")
        return amount
