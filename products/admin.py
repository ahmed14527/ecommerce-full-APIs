from django.contrib import admin
from .models import Category, Product, ProductImage


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 1
    fields = ('image', 'alt_text', 'is_primary', 'order')


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'parent', 'is_active', 'created_at')
    list_filter = ('is_active', 'parent')
    search_fields = ('name',)
    prepopulated_fields = {'slug': ('name',)}


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = (
        'name', 'category', 'cost_price', 'price', 'profit_margin',
        'display_profit', 'stock', 'is_active', 'is_featured', 'created_at',
    )
    list_filter = ('is_active', 'is_featured', 'category')
    search_fields = ('name', 'sku', 'description')
    prepopulated_fields = {'slug': ('name',)}
    list_editable = ('price', 'stock', 'is_active', 'is_featured')
    inlines = [ProductImageInline]
    readonly_fields = ('display_profit', 'created_at', 'updated_at')
    fieldsets = (
        ('Basic Info', {'fields': ('name', 'slug', 'description', 'category', 'sku')}),
        ('Pricing', {
            'fields': ('cost_price', 'profit_margin', 'price', 'compare_at_price', 'display_profit'),
            'description': (
                'Set cost_price + profit_margin to auto-calculate the selling price, '
                'or set price manually. profit is always computed (price − cost_price).'
            ),
        }),
        ('Inventory', {'fields': ('stock', 'weight')}),
        ('Visibility', {'fields': ('is_active', 'is_featured')}),
        ('Timestamps', {'fields': ('created_at', 'updated_at'), 'classes': ('collapse',)}),
    )

    @admin.display(description='Profit', ordering='price')
    def display_profit(self, obj):
        if obj.profit is not None:
            return f'{obj.profit:.2f}'
        return '—'


@admin.register(ProductImage)
class ProductImageAdmin(admin.ModelAdmin):
    list_display = ('product', 'is_primary', 'order', 'created_at')
    list_filter = ('is_primary',)
    raw_id_fields = ('product',)
