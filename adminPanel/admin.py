from django.contrib import admin

from adminPanel.models import TicketReply, PlatformRevenue, RevenueJournal


# ثبت مدل‌ها در پنل ادمین

@admin.register(PlatformRevenue)
class PlatformRevenueAdmin(admin.ModelAdmin):
    list_display = ('title', 'balance', 'updated_at')
    readonly_fields = ('balance', 'updated_at')
    search_fields = ('title',)

    def has_add_permission(self, request):
        return not PlatformRevenue.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(RevenueJournal)
class RevenueJournalAdmin(admin.ModelAdmin):
    list_display = ('account', 'amount', 'balance_after', 'user_email', 'prediction_link', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('user_email', 'prediction__id')
    readonly_fields = ('account', 'amount', 'balance_before', 'balance_after', 'prediction', 'user_email', 'created_at')

    def prediction_link(self, obj):
        if obj.prediction:
            return f"Pred #{obj.prediction.id}"
        return "-"

    prediction_link.short_description = "Related Prediction"

    def has_add_permission(self, request): return False

    def has_change_permission(self, request, obj=None): return False


admin.site.register(TicketReply)

