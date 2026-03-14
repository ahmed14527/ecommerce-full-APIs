from rest_framework import serializers
from users.models import Address
from cart.models import Cart
from .models import Order, OrderItem


class OrderItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderItem
        fields = ('id', 'product', 'product_name', 'product_sku', 'unit_price', 'quantity', 'line_total')


class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    can_cancel = serializers.ReadOnlyField()
    order_number = serializers.UUIDField(read_only=True)

    class Meta:
        model = Order
        fields = (
            'id', 'order_number', 'status', 'can_cancel',
            'shipping_full_name', 'shipping_street', 'shipping_city',
            'shipping_state', 'shipping_postal_code', 'shipping_country',
            'subtotal', 'shipping_cost', 'tax', 'total',
            'notes', 'tracking_number', 'items', 'created_at', 'updated_at',
        )
        read_only_fields = (
            'id', 'order_number', 'status', 'subtotal', 'total',
            'created_at', 'updated_at', 'tracking_number',
        )


class CreateOrderSerializer(serializers.Serializer):
    """Converts the current cart into an order."""
    address_id = serializers.IntegerField()
    notes = serializers.CharField(required=False, allow_blank=True)
    shipping_cost = serializers.DecimalField(max_digits=10, decimal_places=2, default=0)
    tax = serializers.DecimalField(max_digits=10, decimal_places=2, default=0)

    def validate_address_id(self, value):
        user = self.context['request'].user
        try:
            return Address.objects.get(id=value, user=user)
        except Address.DoesNotExist:
            raise serializers.ValidationError("Address not found.")

    def validate(self, attrs):
        user = self.context['request'].user
        try:
            cart = Cart.objects.prefetch_related('items__product').get(user=user)
        except Cart.DoesNotExist:
            raise serializers.ValidationError("No cart found.")
        if not cart.items.exists():
            raise serializers.ValidationError("Your cart is empty.")

        # Stock check
        for item in cart.items.all():
            if item.quantity > item.product.stock:
                raise serializers.ValidationError(
                    f"Insufficient stock for '{item.product.name}'. "
                    f"Only {item.product.stock} available."
                )
        attrs['cart'] = cart
        return attrs

    def create(self, validated_data):
        address = validated_data['address_id']
        cart = validated_data['cart']
        shipping_cost = validated_data.get('shipping_cost', 0)
        tax = validated_data.get('tax', 0)
        notes = validated_data.get('notes', '')
        user = self.context['request'].user

        subtotal = cart.subtotal
        total = subtotal + shipping_cost + tax

        order = Order.objects.create(
            user=user,
            shipping_full_name=address.full_name,
            shipping_street=address.street_address,
            shipping_city=address.city,
            shipping_state=address.state,
            shipping_postal_code=address.postal_code,
            shipping_country=address.country,
            subtotal=subtotal,
            shipping_cost=shipping_cost,
            tax=tax,
            total=total,
            notes=notes,
        )

        # Create order items and decrement stock
        for item in cart.items.select_related('product').all():
            OrderItem.objects.create(
                order=order,
                product=item.product,
                product_name=item.product.name,
                product_sku=item.product.sku,
                unit_price=item.product.price,
                quantity=item.quantity,
            )
            item.product.stock -= item.quantity
            item.product.save(update_fields=['stock'])

        # Clear the cart
        cart.items.all().delete()
        return order
