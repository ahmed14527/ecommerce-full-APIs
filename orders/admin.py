from django.contrib import admin
from .models import Order, OrderItem

class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ('product_name', 'product_sku', 'unit_price', 'quantity', 'line_total')
    can_delete = False

@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('order_number', 'user', 'status', 'total', 'created_at')
    list_filter = ('status',)
    search_fields = ('order_number', 'user__email', 'shipping_full_name')
    readonly_fields = ('order_number', 'user', 'subtotal', 'total', 'created_at', 'updated_at')
    inlines = [OrderItemInline]
    fieldsets = (
        ('Order Info', {'fields': ('order_number', 'user', 'status', 'tracking_number', 'notes')}),
        ('Shipping', {'fields': ('shipping_full_name', 'shipping_street', 'shipping_city',
                                  'shipping_state', 'shipping_postal_code', 'shipping_country')}),
        ('Totals', {'fields': ('subtotal', 'shipping_cost', 'tax', 'total')}),
        ('Timestamps', {'fields': ('created_at', 'updated_at'), 'classes': ('collapse',)}),
    )
