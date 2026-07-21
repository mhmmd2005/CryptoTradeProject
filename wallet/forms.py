import re
from decimal import Decimal

from django import forms

# 🌐 الگوی رگولار اکسپرشن برای اعتبارسنجی شبکه‌های مختلف بلاکچین
ADDRESS_PATTERNS = {
    'usdttrc20': r'^T[a-km-zA-HJ-NP-Z1-9]{33}$',  # شروع با T و طول ۳۴ کاراکتر (TRC-20)
    'trx': r'^T[a-km-zA-HJ-NP-Z1-9]{33}$',  # شبکه ترون
    'eth': r'^0x[a-fA-F0-9]{40}$',  # شروع با 0x و ۴۰ کاراکتر هگز (ERC-20)
    'btc': r'^(1|3|bc1)[a-zA-HJ-NP-Z0-9]{25,62}$'  # فرمت‌های استاندارد بیت‌کوین
}


class WithdrawForm(forms.Form):
    address = forms.CharField(
        label="Wallet Address",
        max_length=200,
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "placeholder": "Enter destination wallet address",
            "id": "wallet-address"
        })
    )
    amount = forms.DecimalField(
        label="Withdrawal Amount",
        max_digits=20,
        decimal_places=6,
        min_value=Decimal("0.000001"),
        widget=forms.NumberInput(attrs={
            "class": "form-control",
            "placeholder": "0.000000",
            "step": "0.000001"
        })
    )

    # دریافت داینامیک آدرس داخلی و نوع ارز از ویو
    def __init__(self, wallet_address=None, currency=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.wallet_address = wallet_address
        self.currency = currency

    def clean_address(self):
        address = self.cleaned_data.get("address")
        address = address.strip() if address else address

        # ۱. جلوگیری از واریز به آدرس داخلی خود کاربر
        if self.wallet_address and address == self.wallet_address:
            raise forms.ValidationError("Withdrawal to your internal wallet address is prohibited.")

        # ۲. 🎯 سپر امنیتی پس‌زمینه: چک کردن فرمت آدرس مقصد بر اساس شبکه بلاکچین
        if self.currency:
            currency_key = self.currency.lower()
            pattern = ADDRESS_PATTERNS.get(currency_key)
            if pattern and not re.match(pattern, address):
                display_name = "USDT (TRC-20)" if currency_key == 'usdttrc20' else currency_key.upper()
                raise forms.ValidationError(f"The destination address format is invalid for {display_name} network.")

        return address


class DepositForm(forms.Form):
    amount = forms.DecimalField(
        label="Deposit Amount",
        max_digits=20,
        decimal_places=2,
        min_value=Decimal("0.01"),
        widget=forms.NumberInput(attrs={
            "class": "form-control",
            "placeholder": "0.00",
            "step": "0.01"
        })
    )
