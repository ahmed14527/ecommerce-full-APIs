import stripe
from django.conf import settings
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from rest_framework import generics, status, permissions
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_spectacular.utils import extend_schema

from orders.models import Order
from .models import Payment
from .serializers import PaymentSerializer, CreatePaymentIntentSerializer

stripe.api_key = settings.STRIPE_SECRET_KEY


@extend_schema(tags=['payments'])
class CreatePaymentIntentView(APIView):
    """
    Create a Stripe PaymentIntent for a given order.
    Returns a client_secret that the frontend uses to confirm payment.
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = CreatePaymentIntentSerializer

    def post(self, request):
        serializer = CreatePaymentIntentSerializer(
            data=request.data, context={'request': request}
        )
        serializer.is_valid(raise_exception=True)
        order = serializer.validated_data['order_id']

        try:
            intent = stripe.PaymentIntent.create(
                amount=int(order.total * 100),  # Stripe uses cents
                currency='usd',
                metadata={
                    'order_id': order.id,
                    'order_number': str(order.order_number),
                    'user_id': request.user.id,
                },
            )

            payment, _ = Payment.objects.update_or_create(
                order=order,
                defaults={
                    'user': request.user,
                    'provider': Payment.Provider.STRIPE,
                    'status': Payment.Status.PENDING,
                    'amount': order.total,
                    'currency': 'USD',
                    'stripe_payment_intent_id': intent.id,
                    'stripe_client_secret': intent.client_secret,
                }
            )

            return Response({
                'client_secret': intent.client_secret,
                'payment': PaymentSerializer(payment).data,
            })

        except stripe.error.StripeError as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(tags=['payments'])
class PaymentListView(generics.ListAPIView):
    """List all payments for the current user."""
    serializer_class = PaymentSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Payment.objects.filter(user=self.request.user).select_related('order')


@extend_schema(tags=['payments'])
class PaymentDetailView(generics.RetrieveAPIView):
    """Retrieve a single payment."""
    serializer_class = PaymentSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Payment.objects.filter(user=self.request.user)


@method_decorator(csrf_exempt, name='dispatch')
@extend_schema(tags=['payments'])
class StripeWebhookView(APIView):
    """
    Stripe webhook endpoint.
    Handles payment_intent.succeeded and payment_intent.payment_failed events.
    Configure your Stripe dashboard to POST to /api/v1/payments/webhook/.
    """
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def post(self, request):
        payload = request.body
        sig_header = request.META.get('HTTP_STRIPE_SIGNATURE', '')

        try:
            event = stripe.Webhook.construct_event(
                payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
            )
        except (ValueError, stripe.error.SignatureVerificationError):
            return Response({'detail': 'Invalid signature.'}, status=status.HTTP_400_BAD_REQUEST)

        intent = event['data']['object']
        payment_intent_id = intent.get('id')

        try:
            payment = Payment.objects.select_related('order').get(
                stripe_payment_intent_id=payment_intent_id
            )
        except Payment.DoesNotExist:
            return Response(status=status.HTTP_200_OK)

        if event['type'] == 'payment_intent.succeeded':
            payment.status = Payment.Status.SUCCEEDED
            payment.save(update_fields=['status'])
            payment.order.status = Order.Status.CONFIRMED
            payment.order.save(update_fields=['status'])

        elif event['type'] == 'payment_intent.payment_failed':
            payment.status = Payment.Status.FAILED
            payment.failure_reason = intent.get('last_payment_error', {}).get('message', '')
            payment.save(update_fields=['status', 'failure_reason'])

        elif event['type'] == 'charge.refunded':
            payment.status = Payment.Status.REFUNDED
            payment.refund_amount = intent.get('amount_refunded', 0) / 100
            payment.refunded_at = timezone.now()
            payment.save(update_fields=['status', 'refund_amount', 'refunded_at'])
            payment.order.status = Order.Status.REFUNDED
            payment.order.save(update_fields=['status'])

        return Response({'status': 'ok'})
