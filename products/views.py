from rest_framework import viewsets, permissions, status, parsers
from rest_framework.decorators import action
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema, extend_schema_view

from .models import Category, Product, ProductImage
from .serializers import (
    CategorySerializer,
    ProductListSerializer,
    ProductDetailSerializer,
    ProductWriteSerializer,
    ProductImageSerializer,
)
from .filters import ProductFilter


class IsAdminOrReadOnly(permissions.BasePermission):
    """Allow read access to all; write access to admin only."""
    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return True
        return request.user and request.user.is_staff


@extend_schema(tags=['products'])
class CategoryViewSet(viewsets.ModelViewSet):
    queryset = Category.objects.filter(is_active=True, parent=None).prefetch_related('subcategories')
    serializer_class = CategorySerializer
    permission_classes = [IsAdminOrReadOnly]
    lookup_field = 'slug'
    search_fields = ['name', 'description']


@extend_schema(tags=['products'])
class ProductViewSet(viewsets.ModelViewSet):
    queryset = Product.objects.filter(is_active=True).select_related('category').prefetch_related('images', 'reviews')
    permission_classes = [IsAdminOrReadOnly]
    filterset_class = ProductFilter
    search_fields = ['name', 'description', 'sku', 'category__name']
    ordering_fields = ['price', 'created_at', 'name']
    ordering = ['-created_at']
    lookup_field = 'slug'

    def get_serializer_class(self):
        if self.action == 'list':
            return ProductListSerializer
        if self.action in ('create', 'update', 'partial_update'):
            return ProductWriteSerializer
        return ProductDetailSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        # Admins can see inactive products
        if self.request.user.is_authenticated and self.request.user.is_staff:
            return Product.objects.select_related('category').prefetch_related('images', 'reviews')
        return qs

    @extend_schema(tags=['products'])
    @action(detail=True, methods=['post', 'delete'], permission_classes=[permissions.IsAdminUser],
            parser_classes=[parsers.MultiPartParser, parsers.FormParser])
    def images(self, request, slug=None):
        """Upload or delete product images."""
        product = self.get_object()
        if request.method == 'POST':
            serializer = ProductImageSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            serializer.save(product=product)
            return Response(serializer.data, status=status.HTTP_201_CREATED)

        image_id = request.data.get('image_id')
        try:
            image = ProductImage.objects.get(id=image_id, product=product)
            image.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        except ProductImage.DoesNotExist:
            return Response({'detail': 'Image not found.'}, status=status.HTTP_404_NOT_FOUND)

    @extend_schema(tags=['products'])
    @action(detail=False, methods=['get'])
    def featured(self, request):
        """Return featured products."""
        qs = self.get_queryset().filter(is_featured=True)[:12]
        serializer = ProductListSerializer(qs, many=True, context={'request': request})
        return Response(serializer.data)
