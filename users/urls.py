"""
apps/users/urls.py

URL structure:
  /api/auth/register/             POST   — register with email + password
  /api/auth/login/                POST   — login, receive JWT tokens
  /api/auth/logout/               POST   — blacklist refresh token
  /api/auth/token/refresh/        POST   — refresh access token
  /api/auth/google/               POST   — Google ID token → JWT tokens

  /api/users/me/                  GET    — current user profile
  /api/users/me/                  PATCH  — update name / avatar
  /api/users/me/change-password/  POST   — change password
"""

from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from users.views import (
    GoogleAuthView,
    LoginView,
    LogoutView,
    MeView,
    PasswordChangeView,
    RegisterView,
)

app_name = 'users'

# ── Authentication routes ─────────────────────────────────────────────────────
auth_urlpatterns = [
    path("register/",        RegisterView.as_view(),    name="auth-register"),
    path("login/",           LoginView.as_view(),       name="auth-login"),
    path("logout/",          LogoutView.as_view(),      name="auth-logout"),
    path("token/refresh/",   TokenRefreshView.as_view(), name="token-refresh"),
    path("google/",          GoogleAuthView.as_view(),  name="auth-google"),
]

# ── User profile routes ───────────────────────────────────────────────────────
user_urlpatterns = [
    path("me/",                  MeView.as_view(),              name="user-me"),
    path("me/change-password/",  PasswordChangeView.as_view(),  name="user-change-password"),
]
