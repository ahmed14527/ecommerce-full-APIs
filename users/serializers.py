

from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.tokens import RefreshToken, TokenError

User = get_user_model()


# ── Token payload ─────────────────────────────────────────────────────────────

class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        # Custom claims embedded in the JWT payload
        token["email"] = user.email
        token["name"] = user.name
        token["is_staff"] = user.is_staff
        return token


# ── Registration ──────────────────────────────────────────────────────────────

class RegisterSerializer(serializers.ModelSerializer):
    """
    Validates and creates a new email/password user.

    password is write-only and validated against Django's AUTH_PASSWORD_VALIDATORS.
    password_confirm is stripped before save — it's never stored.
    """

    password = serializers.CharField(
        write_only=True,
        min_length=8,
        validators=[validate_password],
    )
    password_confirm = serializers.CharField(write_only=True, min_length=8)

    class Meta:
        model = User
        fields = ("email", "name", "password", "password_confirm")

    def validate_email(self, value):
        """Normalize and uniqueness-check the email."""
        value = value.lower().strip()
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return value

    def validate(self, attrs):
        if attrs["password"] != attrs.pop("password_confirm"):
            raise serializers.ValidationError({"password_confirm": "Passwords do not match."})
        return attrs

    def create(self, validated_data):
        return User.objects.create_user(**validated_data)


class RegisterResponseSerializer(serializers.Serializer):
    """Response shape after successful registration."""
    user = serializers.SerializerMethodField()
    access = serializers.CharField()
    refresh = serializers.CharField()

    def get_user(self, obj):
        return UserProfileSerializer(obj["user"]).data


# ── Login ─────────────────────────────────────────────────────────────────────

class LoginSerializer(serializers.Serializer):
    """
    Email + password login.

    Uses Django's authenticate() so it respects is_active,
    custom backends, and rate-limiting middleware if added later.
    """

    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        email = attrs["email"].lower().strip()
        password = attrs["password"]

        # authenticate() checks password hash + is_active
        user = authenticate(
            request=self.context.get("request"),
            username=email,       # USERNAME_FIELD = 'email', mapped to username kwarg
            password=password,
        )

        if user is None:
            raise serializers.ValidationError(
                {"non_field_errors": "Invalid email or password."}
            )

        if not user.is_active:
            raise serializers.ValidationError(
                {"non_field_errors": "This account has been deactivated."}
            )

        attrs["user"] = user
        return attrs


# ── Logout ────────────────────────────────────────────────────────────────────

class LogoutSerializer(serializers.Serializer):
    """
    Accepts the refresh token to blacklist it.

    After blacklisting, the refresh token is unusable even if it hasn't expired.
    The access token remains valid until its own expiry (typically 15–60 min).
    For immediate access token invalidation, keep ACCESS_TOKEN_LIFETIME short.
    """

    refresh = serializers.CharField()

    def validate_refresh(self, value):
        """Parse the token eagerly so we can return a 400 with a clear error."""
        try:
            self._token = RefreshToken(value)
        except TokenError as exc:
            raise serializers.ValidationError(f"Invalid or expired token: {exc}") from exc
        return value

    def save(self):
        """Blacklist the token. Call after is_valid()."""
        self._token.blacklist()


# ── Token refresh ─────────────────────────────────────────────────────────────
# We re-export SimpleJWT's TokenRefreshSerializer unchanged.
# The view can use it directly or wrap it here if custom logic is needed.

from rest_framework_simplejwt.serializers import TokenRefreshSerializer  # noqa: F401, E402


# ── Google OAuth ──────────────────────────────────────────────────────────────

class GoogleAuthSerializer(serializers.Serializer):
    """
    Input: Google ID token sent by the frontend.

    The token is a raw JWT string produced by Google Sign-In / One Tap.
    We do NOT validate it here — that happens in the service layer using
    google-auth so we can check the cryptographic signature.
    """

    id_token = serializers.CharField(
        help_text="Google ID token obtained from the frontend Google Sign-In flow."
    )

    def validate_id_token(self, value):
        if not value or len(value) < 20:
            raise serializers.ValidationError("Invalid Google ID token format.")
        return value.strip()


class GoogleAuthResponseSerializer(serializers.Serializer):
    """Response shape after successful Google login."""
    access = serializers.CharField()
    refresh = serializers.CharField()
    created = serializers.BooleanField(help_text="True if this is a new account.")
    user = serializers.SerializerMethodField()

    def get_user(self, obj):
        return UserProfileSerializer(obj["user"]).data


# ── User profile ──────────────────────────────────────────────────────────────

class UserProfileSerializer(serializers.ModelSerializer):
    """
    Read-only user representation returned in all auth responses.

    Never exposes: password, is_superuser, permissions.
    """

    class Meta:
        model = User
        fields = (
            "id",
            "email",
            "name",
            "avatar_url",
            "is_staff",
            "date_joined",
        )
        read_only_fields = fields


class UserUpdateSerializer(serializers.ModelSerializer):
    """
    Allows users to update their own name and avatar_url.
    Email and password changes are handled by separate endpoints.
    """

    class Meta:
        model = User
        fields = ("name", "avatar_url")

    def validate_name(self, value):
        return value.strip()


# ── Password change ───────────────────────────────────────────────────────────

class PasswordChangeSerializer(serializers.Serializer):
    """
    Allows an authenticated user to change their password.
    Verifies the current password before accepting the new one.
    """

    current_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(
        write_only=True,
        min_length=8,
        validators=[validate_password],
    )
    confirm_new_password = serializers.CharField(write_only=True, min_length=8)

    def validate_current_password(self, value):
        user = self.context["request"].user
        if not user.check_password(value):
            raise serializers.ValidationError("Current password is incorrect.")
        return value

    def validate(self, attrs):
        if attrs["new_password"] != attrs.pop("confirm_new_password"):
            raise serializers.ValidationError(
                {"confirm_new_password": "New passwords do not match."}
            )
        return attrs

    def save(self):
        user = self.context["request"].user
        user.set_password(self.validated_data["new_password"])
        user.save(update_fields=["password", "updated_at"])
        return user
