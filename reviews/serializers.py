from rest_framework import serializers
from .models import Review, ReviewHelpful


class ReviewSerializer(serializers.ModelSerializer):
    user_email = serializers.EmailField(source='user.email', read_only=True)
    user_name = serializers.CharField(source='user.full_name', read_only=True)

    class Meta:
        model = Review
        fields = (
            'id', 'product', 'user', 'user_email', 'user_name',
            'rating', 'title', 'body', 'is_verified_purchase',
            'is_approved', 'helpful_count', 'created_at', 'updated_at',
        )
        read_only_fields = (
            'id', 'user', 'user_email', 'user_name',
            'is_verified_purchase', 'is_approved', 'helpful_count',
            'created_at', 'updated_at',
        )

    def validate(self, attrs):
        user = self.context['request'].user
        product = attrs.get('product', getattr(self.instance, 'product', None))
        if self.instance is None:  
            if Review.objects.filter(product=product, user=user).exists():
                raise serializers.ValidationError("You have already reviewed this product.")
        return attrs

    def create(self, validated_data):
        from orders.models import Order, OrderItem
        user = self.context['request'].user
        product = validated_data['product']

        # Check if user actually purchased this product
        purchased = OrderItem.objects.filter(
            order__user=user,
            product=product,
            order__status='delivered',
        ).exists()

        return Review.objects.create(
            user=user,
            is_verified_purchase=purchased,
            **validated_data
        )


class ProductReviewSummarySerializer(serializers.Serializer):
    """Aggregated stats for a product's reviews."""
    average_rating = serializers.FloatField()
    total_reviews = serializers.IntegerField()
    rating_breakdown = serializers.DictField(child=serializers.IntegerField())
