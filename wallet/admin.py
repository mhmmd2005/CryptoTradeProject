from django.contrib import admin

from wallet.models import DollarWallet, WalletTransaction,WithdrawRequest


# ابتدا اکشن تعریف بشه
@admin.action(description="Mark selected deposits as Success")
def mark_success(modeladmin, request, queryset):
    for tx in queryset.filter(status="pending", type="deposit"):
        tx.status = "success"
        tx.confirmed = True
        wallet = tx.wallet
        wallet.balance += tx.amount
        wallet.save()
        tx.save()


# بعد Admin
class WalletTransactionAdmin(admin.ModelAdmin):
    list_display = ("wallet", "type", "amount", "status", "confirmed", "timestamp")
    list_filter = ("status", "type")
    actions = [mark_success]


admin.site.register(DollarWallet)
admin.site.register(WithdrawRequest)
admin.site.register(WalletTransaction, WalletTransactionAdmin)
