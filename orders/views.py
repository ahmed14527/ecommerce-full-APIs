from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema

from .models import Order
from .serializers import OrderSerializer, CreateOrderSerializer


@extend_schema(tags=['orders'])
class OrderViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated]
    http_method_names = ['get', 'post', 'head', 'options']  # no PUT/PATCH/DELETE for orders

    def get_serializer_class(self):
        if self.action == 'create':
            return CreateOrderSerializer
        return OrderSerializer

    def get_queryset(self):
        qs = Order.objects.prefetch_related('items__product').filter(user=self.request.user)
        # Staff can see all orders
        if self.request.user.is_staff:
            qs = Order.objects.prefetch_related('items__product').all()
        status_filter = self.request.query_params.get('status')
        if status_filter:
            qs = qs.filter(status=status_filter)
        return qs

    def create(self, request, *args, **kwargs):
        serializer = CreateOrderSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        order = serializer.save()
        return Response(
            OrderSerializer(order).data,
            status=status.HTTP_201_CREATED
        )

    @extend_schema(tags=['orders'])
    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        """Cancel an order if it is still cancellable."""
        order = self.get_object()
        if not order.can_cancel:
            return Response(
                {'detail': f"Order in status '{order.status}' cannot be cancelled."},
                status=status.HTTP_400_BAD_REQUEST
            )
        order.status = Order.Status.CANCELLED
        order.save(update_fields=['status'])

        # Restore stock
        for item in order.items.select_related('product').all():
            if item.product:
                item.product.stock += item.quantity
                item.product.save(update_fields=['stock'])

        return Response(OrderSerializer(order).data)

    @extend_schema(tags=['orders'])
    @action(detail=True, methods=['patch'], permission_classes=[permissions.IsAdminUser])
    def update_status(self, request, pk=None):
        """Admin-only: update order status and tracking number."""
        order = self.get_object()
        new_status = request.data.get('status')
        tracking = request.data.get('tracking_number')

        if new_status and new_status not in Order.Status.values:
            return Response({'detail': 'Invalid status.'}, status=status.HTTP_400_BAD_REQUEST)

        if new_status:
            order.status = new_status
        if tracking:
            order.tracking_number = tracking
        order.save()
        return Response(OrderSerializer(order).data)
