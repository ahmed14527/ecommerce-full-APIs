from rest_framework import serializers
from .models import Payment


class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = (
            'id', 'reference', 'order', 'provider', 'status',
            'amount', 'currency', 'stripe_client_secret',
            'failure_reason', 'refund_amount', 'refunded_at',
            'created_at', 'updated_at',
        )
        read_only_fields = fields  # Payments are created internally


class CreatePaymentIntentSerializer(serializers.Serializer):
    """Initiates a Stripe PaymentIntent for an order."""
    order_id = serializers.IntegerField()

    def validate_order_id(self, value):
        from orders.models import Order
        user = self.context['request'].user
        try:
            order = Order.objects.get(id=value, user=user)
        except Order.DoesNotExist:
            raise serializers.ValidationError("Order not found.")
        if order.status == Order.Status.CANCELLED:
            raise serializers.ValidationError("Cannot pay for a cancelled order.")
        if hasattr(order, 'payment') and order.payment.status == Payment.Status.SUCCEEDED:
            raise serializers.ValidationError("Order is already paid.")
        return order


class WebhookSerializer(serializers.Serializer):
    """Used only for documentation purposes."""
    type = serializers.CharField()
    data = serializers.DictField()
