"""
apps/users/views.py

Views are intentionally thin:
  - Deserialize input
  - Call service or serializer
  - Serialize output
  - Return response

No business logic lives here.
"""

import logging

from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from users.serializers import (
    CustomTokenObtainPairSerializer,
    GoogleAuthSerializer,
    LoginSerializer,
    LogoutSerializer,
    PasswordChangeSerializer,
    RegisterSerializer,
    UserProfileSerializer,
    UserUpdateSerializer,
)
from users.services.google_auth import GoogleTokenError, authenticate_google_user

logger = logging.getLogger(__name__)


# ── Registration ──────────────────────────────────────────────────────────────

class RegisterView(generics.CreateAPIView):
    """
    POST /api/auth/register/

    Creates a new email/password user and returns JWT tokens immediately
    so the user doesn't need to log in after registering.

    Permission: AllowAny (public endpoint)
    """

    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()

        # Issue tokens immediately — no need for a separate login step
        from rest_framework_simplejwt.tokens import RefreshToken
        refresh = RefreshToken.for_user(user)

        return Response(
            {
                "user": UserProfileSerializer(user).data,
                "access": str(refresh.access_token),
                "refresh": str(refresh),
            },
            status=status.HTTP_201_CREATED,
        )


# ── Login ─────────────────────────────────────────────────────────────────────

class LoginView(APIView):
    """
    POST /api/auth/login/

    Email + password login. Returns JWT access + refresh tokens.
    We use a custom serializer instead of SimpleJWT's TokenObtainPairView
    so we can return the user profile alongside the tokens.

    Permission: AllowAny (public endpoint)
    """

    permission_classes = [permissions.AllowAny]
    serializer_class = LoginSerializer          # for drf-spectacular schema

    def post(self, request):
        serializer = LoginSerializer(
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]

        from rest_framework_simplejwt.tokens import RefreshToken
        refresh = RefreshToken.for_user(user)

        return Response(
            {
                "user": UserProfileSerializer(user).data,
                "access": str(refresh.access_token),
                "refresh": str(refresh),
            }
        )


# ── Token refresh ─────────────────────────────────────────────────────────────

class TokenRefreshView(TokenRefreshView):
    """
    POST /api/auth/token/refresh/

    Standard SimpleJWT token refresh — inherits directly.
    Separated here so we can add custom logic later (e.g. rotate + blacklist).
    """


# ── Logout ────────────────────────────────────────────────────────────────────

class LogoutView(APIView):
    """
    POST /api/auth/logout/

    Blacklists the provided refresh token so it cannot be used again.
    The access token expires naturally (keep ACCESS_TOKEN_LIFETIME short).

    Body: { "refresh": "<refresh_token>" }

    Permission: IsAuthenticated
    """

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = LogoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(
            {"detail": "Successfully logged out."},
            status=status.HTTP_200_OK,
        )


# ── Google OAuth ──────────────────────────────────────────────────────────────

class GoogleAuthView(APIView):
    """
    POST /api/auth/google/

    Accepts a Google ID token from the frontend, verifies it against
    Google's public keys, and returns JWT tokens for our system.

    Why this is safe:
      - We NEVER trust the payload the frontend sends.
      - The `google-auth` library verifies the token signature, audience
        (CLIENT_ID), issuer, and expiry — none of which the frontend can fake.
      - Token verification happens in the service layer, not here.

    Body:    { "id_token": "<google_id_token>" }
    Returns: { "access": "...", "refresh": "...", "created": bool, "user": {...} }

    Permission: AllowAny (the Google token IS the credential)
    """

    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = GoogleAuthSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        raw_token = serializer.validated_data["id_token"]

        try:
            result = authenticate_google_user(raw_token)
        except GoogleTokenError as exc:
            # Return 401 for token problems — do not expose internal details
            logger.warning(
                "Google auth failed for request from %s: %s",
                request.META.get("REMOTE_ADDR"),
                exc,
            )
            return Response(
                {"detail": "Google authentication failed. Please try again."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        http_status = status.HTTP_201_CREATED if result.created else status.HTTP_200_OK

        return Response(
            {
                "user": UserProfileSerializer(result.user).data,
                "access": result.access_token,
                "refresh": result.refresh_token,
                "created": result.created,
            },
            status=http_status,
        )


# ── Current user profile ──────────────────────────────────────────────────────

class MeView(generics.RetrieveUpdateAPIView):
    """
    GET  /api/users/me/    — return current user profile
    PATCH /api/users/me/   — update name / avatar_url

    Permission: IsAuthenticated
    """

    permission_classes = [permissions.IsAuthenticated]

    def get_serializer_class(self):
        if self.request.method in ("PUT", "PATCH"):
            return UserUpdateSerializer
        return UserProfileSerializer

    def get_object(self):
        return self.request.user

    def update(self, request, *args, **kwargs):
        kwargs["partial"] = True          # always allow partial updates
        return super().update(request, *args, **kwargs)


# ── Password change ───────────────────────────────────────────────────────────

class PasswordChangeView(APIView):
    """
    POST /api/users/me/change-password/

    Requires current password — prevents account takeover if a session
    token is stolen but the attacker doesn't know the password.

    Permission: IsAuthenticated
    """

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = PasswordChangeSerializer(
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({"detail": "Password updated successfully."})
