from rest_framework import serializers
from products.serializers import ProductListSerializer
from .models import Cart, CartItem


class CartItemSerializer(serializers.ModelSerializer):
    product_detail = ProductListSerializer(source='product', read_only=True)
    line_total = serializers.ReadOnlyField()

    class Meta:
        model = CartItem
        fields = ('id', 'product', 'product_detail', 'quantity', 'line_total', 'added_at')
        read_only_fields = ('id', 'added_at')

    def validate(self, attrs):
        product = attrs['product']
        quantity = attrs['quantity']
        if not product.is_active:
            raise serializers.ValidationError("This product is no longer available.")
        if quantity > product.stock:
            raise serializers.ValidationError(
                f"Only {product.stock} units available for '{product.name}'."
            )
        return attrs


class UpdateCartItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = CartItem
        fields = ('quantity',)

    def validate_quantity(self, value):
        product = self.instance.product
        if value > product.stock:
            raise serializers.ValidationError(
                f"Only {product.stock} units available."
            )
        return value


class CartSerializer(serializers.ModelSerializer):
    items = CartItemSerializer(many=True, read_only=True)
    total_items = serializers.ReadOnlyField()
    subtotal = serializers.ReadOnlyField()

    class Meta:
        model = Cart
        fields = ('id', 'items', 'total_items', 'subtotal', 'updated_at')
