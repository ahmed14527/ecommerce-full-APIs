from django.contrib import admin
from .models import Payment

@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ('reference', 'user', 'order', 'provider', 'status', 'amount', 'currency', 'created_at')
    list_filter = ('status', 'provider', 'currency')
    search_fields = ('reference', 'user__email', 'stripe_payment_intent_id')
    readonly_fields = ('reference', 'stripe_payment_intent_id', 'stripe_client_secret', 'created_at', 'updated_at')
    raw_id_fields = ('user', 'order')
