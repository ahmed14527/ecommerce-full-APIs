from rest_framework import serializers
from .models import Category, Product, ProductImage


class CategorySerializer(serializers.ModelSerializer):
    subcategories = serializers.SerializerMethodField()

    class Meta:
        model = Category
        fields = ('id', 'name', 'slug', 'description', 'image', 'parent', 'subcategories', 'is_active')
        read_only_fields = ('slug',)

    def get_subcategories(self, obj):
        # Only include direct children to avoid deep recursion
        children = obj.subcategories.filter(is_active=True)
        return CategorySerializer(children, many=True, context=self.context).data


class ProductImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductImage
        fields = ('id', 'image', 'alt_text', 'is_primary', 'order')


class ProductListSerializer(serializers.ModelSerializer):
    """Lightweight serializer used in list views."""
    category_name = serializers.CharField(source='category.name', read_only=True)
    primary_image = serializers.SerializerMethodField()
    average_rating = serializers.ReadOnlyField()
    review_count = serializers.ReadOnlyField()
    is_in_stock = serializers.ReadOnlyField()
    discount_percentage = serializers.ReadOnlyField()

    class Meta:
        model = Product
        fields = (
            'id', 'name', 'slug', 'category', 'category_name', 'price',
            'compare_at_price', 'discount_percentage', 'is_in_stock',
            'primary_image', 'average_rating', 'review_count', 'is_featured',
        )

    def get_primary_image(self, obj):
        image = obj.images.filter(is_primary=True).first() or obj.images.first()
        if image:
            request = self.context.get('request')
            return request.build_absolute_uri(image.image.url) if request else image.image.url
        return None


class ProductDetailSerializer(serializers.ModelSerializer):
    """Full product detail serializer."""
    images = ProductImageSerializer(many=True, read_only=True)
    category_name = serializers.CharField(source='category.name', read_only=True)
    average_rating = serializers.ReadOnlyField()
    review_count = serializers.ReadOnlyField()
    is_in_stock = serializers.ReadOnlyField()
    discount_percentage = serializers.ReadOnlyField()

    class Meta:
        model = Product
        fields = (
            'id', 'name', 'slug', 'description', 'category', 'category_name',
            'price', 'compare_at_price', 'discount_percentage', 'stock', 'sku',
            'is_active', 'is_featured', 'is_in_stock', 'weight',
            'images', 'average_rating', 'review_count', 'created_at', 'updated_at',
        )
        read_only_fields = ('slug', 'created_at', 'updated_at')


class ProductWriteSerializer(serializers.ModelSerializer):
    """Used for create/update operations."""

    class Meta:
        model = Product
        fields = (
            'name', 'description', 'category', 'price', 'compare_at_price',
            'stock', 'sku', 'is_active', 'is_featured', 'weight',
        )
