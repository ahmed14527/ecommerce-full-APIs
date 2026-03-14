from django.db import models
from django.contrib.auth import get_user_model
from products.models import Product

User = get_user_model()


class Cart(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='cart')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Cart'

    def __str__(self):
        return f"Cart – {self.user.email}"

    @property
    def total_items(self):
        return sum(item.quantity for item in self.items.all())

    @property
    def subtotal(self):
        return sum(item.line_total for item in self.items.all())


class CartItem(models.Model):
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=1)
    added_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('cart', 'product')
        verbose_name = 'Cart Item'

    def __str__(self):
        if self.product_id and self.product is not None:
            return f"{self.quantity} × {self.product.name}"
        return f"{self.quantity} × (no product)"

    @property
    def line_total(self):
        if self.product_id and self.product is not None:
            return self.product.price * self.quantity
        return 0

    def clean(self):
        from django.core.exceptions import ValidationError
        if not self.product_id:
            raise ValidationError({'product': 'Product is required for cart items.'})
        if self.quantity > self.product.stock:
            raise ValidationError(
                f"Only {self.product.stock} units of '{self.product.name}' available."
            )
