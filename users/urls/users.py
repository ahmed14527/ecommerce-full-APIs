from django.urls import path
from users.views import UserProfileView, ChangePasswordView, AddressListCreateView, AddressDetailView

urlpatterns = [
    path('me/', UserProfileView.as_view(), name='user-profile'),
    path('me/change-password/', ChangePasswordView.as_view(), name='change-password'),
    path('me/addresses/', AddressListCreateView.as_view(), name='address-list'),
    path('me/addresses/<int:pk>/', AddressDetailView.as_view(), name='address-detail'),
]
