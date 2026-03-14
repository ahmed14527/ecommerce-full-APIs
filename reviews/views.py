from django.db.models import Avg, Count
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema

from .models import Review, ReviewHelpful
from .serializers import ReviewSerializer, ProductReviewSummarySerializer


class IsOwnerOrAdminOrReadOnly(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True
        return obj.user == request.user or request.user.is_staff


@extend_schema(tags=['reviews'])
class ReviewViewSet(viewsets.ModelViewSet):
    serializer_class = ReviewSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly, IsOwnerOrAdminOrReadOnly]
    filterset_fields = ['product', 'rating', 'is_verified_purchase']
    ordering_fields = ['created_at', 'rating', 'helpful_count']
    ordering = ['-created_at']

    def get_queryset(self):
        qs = Review.objects.select_related('user', 'product').filter(is_approved=True)
        if self.request.user.is_authenticated and self.request.user.is_staff:
            return Review.objects.select_related('user', 'product').all()
        return qs

    def perform_create(self, serializer):
        serializer.save()

    @extend_schema(tags=['reviews'])
    @action(detail=False, methods=['get'], url_path='product/(?P<product_id>[^/.]+)/summary')
    def product_summary(self, request, product_id=None):
        """Return rating stats for a specific product."""
        reviews = Review.objects.filter(product_id=product_id, is_approved=True)
        total = reviews.count()
        avg = reviews.aggregate(avg=Avg('rating'))['avg'] or 0.0
        breakdown = {str(i): reviews.filter(rating=i).count() for i in range(1, 6)}
        return Response(ProductReviewSummarySerializer({
            'average_rating': round(avg, 1),
            'total_reviews': total,
            'rating_breakdown': breakdown,
        }).data)

    @extend_schema(tags=['reviews'])
    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAuthenticated])
    def helpful(self, request, pk=None):
        """Mark a review as helpful (or undo it)."""
        review = self.get_object()
        vote, created = ReviewHelpful.objects.get_or_create(review=review, user=request.user)
        if not created:
            vote.delete()
            review.helpful_count = max(0, review.helpful_count - 1)
            review.save(update_fields=['helpful_count'])
            return Response({'detail': 'Removed helpful vote.'})

        review.helpful_count += 1
        review.save(update_fields=['helpful_count'])
        return Response({'detail': 'Marked as helpful.'}, status=status.HTTP_201_CREATED)

    @extend_schema(tags=['reviews'])
    @action(detail=True, methods=['patch'], permission_classes=[permissions.IsAdminUser])
    def approve(self, request, pk=None):
        """Admin: approve or reject a review."""
        review = self.get_object()
        review.is_approved = request.data.get('is_approved', True)
        review.save(update_fields=['is_approved'])
        return Response(ReviewSerializer(review, context={'request': request}).data)
