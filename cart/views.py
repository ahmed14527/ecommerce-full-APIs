from rest_framework import generics, status, permissions
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_spectacular.utils import extend_schema

from .models import Cart, CartItem
from .serializers import CartSerializer, CartItemSerializer, UpdateCartItemSerializer


def get_or_create_cart(user):
    cart, _ = Cart.objects.get_or_create(user=user)
    return cart


@extend_schema(tags=['cart'])
class CartView(APIView):
    """Retrieve the current user's cart."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        cart = get_or_create_cart(request.user)
        serializer = CartSerializer(cart, context={'request': request})
        return Response(serializer.data)

    def delete(self, request):
        """Clear all items from the cart."""
        cart = get_or_create_cart(request.user)
        cart.items.all().delete()
        return Response({'detail': 'Cart cleared.'}, status=status.HTTP_200_OK)


@extend_schema(tags=['cart'])
class CartItemAddView(generics.CreateAPIView):
    """Add a product to the cart (or increment if already present)."""
    serializer_class = CartItemSerializer
    permission_classes = [permissions.IsAuthenticated]

    def create(self, request, *args, **kwargs):
        cart = get_or_create_cart(request.user)
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        product = serializer.validated_data['product']
        quantity = serializer.validated_data['quantity']

        item, created = CartItem.objects.get_or_create(
            cart=cart, product=product,
            defaults={'quantity': quantity}
        )
        if not created:
            new_qty = item.quantity + quantity
            if new_qty > product.stock:
                return Response(
                    {'detail': f"Only {product.stock} units available."},
                    status=status.HTTP_400_BAD_REQUEST
                )
            item.quantity = new_qty
            item.save()

        return Response(
            CartSerializer(cart, context={'request': request}).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK
        )


@extend_schema(tags=['cart'])
class CartItemDetailView(generics.RetrieveUpdateDestroyAPIView):
    """Update quantity or remove a cart item."""
    permission_classes = [permissions.IsAuthenticated]

    def get_serializer_class(self):
        if self.request.method in ('PUT', 'PATCH'):
            return UpdateCartItemSerializer
        return CartItemSerializer

    def get_queryset(self):
        cart = get_or_create_cart(self.request.user)
        return CartItem.objects.filter(cart=cart)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        instance.delete()
        cart = get_or_create_cart(request.user)
        return Response(CartSerializer(cart, context={'request': request}).data)
