from django.contrib import admin
from .models import Review, ReviewHelpful

@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ('user', 'product', 'rating', 'is_verified_purchase', 'is_approved', 'helpful_count', 'created_at')
    list_filter = ('rating', 'is_verified_purchase', 'is_approved')
    search_fields = ('user__email', 'product__name', 'body')
    list_editable = ('is_approved',)
    raw_id_fields = ('user', 'product')
    readonly_fields = ('helpful_count', 'created_at', 'updated_at')
