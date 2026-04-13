"""
apps/users/tests.py

Full test coverage for:
  - User model
  - Registration
  - Login / Logout
  - Token refresh
  - Google OAuth (mocked — we never make real Google API calls in tests)
  - Profile read / update
  - Password change
"""

from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient, APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from users.models import SocialAccount
from users.services.google_auth import (
    GoogleTokenError,
    GoogleUserInfo,
    authenticate_google_user,
    get_or_create_google_user,
    verify_google_id_token,
)

User = get_user_model()


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_user(email="test@example.com", password="TestPass123!", name="Test User"):
    return User.objects.create_user(email=email, password=password, name=name)


def auth_client(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


SAMPLE_GOOGLE_INFO = GoogleUserInfo(
    google_id="google-sub-123456",
    email="google@example.com",
    name="Google User",
    avatar_url="https://lh3.googleusercontent.com/photo.jpg",
    email_verified=True,
)


# ═════════════════════════════════════════════════════════════════════════════
# Model tests
# ═════════════════════════════════════════════════════════════════════════════

class UserModelTest(TestCase):

    def test_create_user_email_required(self):
        with self.assertRaises(ValueError):
            User.objects.create_user(email="", password="pass")

    def test_create_user_email_normalized(self):
        user = User.objects.create_user(email="TEST@EXAMPLE.COM", password="pass")
        self.assertEqual(user.email, "test@example.com")

    def test_create_user_no_username_field(self):
        self.assertFalse(hasattr(User, "username"))

    def test_str_returns_email(self):
        user = make_user()
        self.assertEqual(str(user), "test@example.com")

    def test_first_name_property(self):
        user = make_user(name="Jane Doe")
        self.assertEqual(user.first_name, "Jane")

    def test_last_name_property(self):
        user = make_user(name="Jane Doe Smith")
        self.assertEqual(user.last_name, "Doe Smith")

    def test_create_superuser(self):
        admin = User.objects.create_superuser(email="admin@example.com", password="admin123")
        self.assertTrue(admin.is_staff)
        self.assertTrue(admin.is_superuser)

    def test_create_superuser_must_have_is_staff(self):
        with self.assertRaises(ValueError):
            User.objects.create_superuser(
                email="admin2@example.com", password="admin123", is_staff=False
            )


class SocialAccountModelTest(TestCase):

    def test_social_account_str(self):
        user = make_user()
        sa = SocialAccount.objects.create(
            user=user,
            provider=SocialAccount.Provider.GOOGLE,
            provider_user_id="sub-123",
        )
        self.assertIn("google", str(sa))
        self.assertIn(user.email, str(sa))

    def test_unique_provider_user_id(self):
        user = make_user()
        SocialAccount.objects.create(
            user=user, provider=SocialAccount.Provider.GOOGLE, provider_user_id="sub-123"
        )
        with self.assertRaises(Exception):
            SocialAccount.objects.create(
                user=user, provider=SocialAccount.Provider.GOOGLE, provider_user_id="sub-123"
            )


# ═════════════════════════════════════════════════════════════════════════════
# Registration API
# ═════════════════════════════════════════════════════════════════════════════

class RegisterAPITest(APITestCase):

    URL = "/api/auth/register/"

    def test_register_success(self):
        r = self.client.post(self.URL, {
            "email": "new@example.com",
            "name": "New User",
            "password": "StrongPass123!",
            "password_confirm": "StrongPass123!",
        })
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        self.assertIn("access", r.data)
        self.assertIn("refresh", r.data)
        self.assertEqual(r.data["user"]["email"], "new@example.com")

    def test_register_password_mismatch(self):
        r = self.client.post(self.URL, {
            "email": "mm@example.com",
            "password": "StrongPass123!",
            "password_confirm": "WrongPass456!",
        })
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_register_duplicate_email(self):
        make_user(email="dup@example.com")
        r = self.client.post(self.URL, {
            "email": "dup@example.com",
            "password": "StrongPass123!",
            "password_confirm": "StrongPass123!",
        })
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_register_weak_password_rejected(self):
        r = self.client.post(self.URL, {
            "email": "weak@example.com",
            "password": "123",
            "password_confirm": "123",
        })
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_register_email_normalized(self):
        r = self.client.post(self.URL, {
            "email": "UPPER@EXAMPLE.COM",
            "password": "StrongPass123!",
            "password_confirm": "StrongPass123!",
        })
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        self.assertEqual(r.data["user"]["email"], "upper@example.com")


# ═════════════════════════════════════════════════════════════════════════════
# Login API
# ═════════════════════════════════════════════════════════════════════════════

class LoginAPITest(APITestCase):

    URL = "/api/auth/login/"

    def setUp(self):
        self.user = make_user(email="login@example.com", password="MyPass123!")

    def test_login_success(self):
        r = self.client.post(self.URL, {
            "email": "login@example.com",
            "password": "MyPass123!",
        })
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertIn("access", r.data)
        self.assertIn("refresh", r.data)

    def test_login_wrong_password(self):
        r = self.client.post(self.URL, {
            "email": "login@example.com",
            "password": "WrongPass!",
        })
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_login_nonexistent_user(self):
        r = self.client.post(self.URL, {
            "email": "nobody@example.com",
            "password": "AnyPass123!",
        })
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_login_inactive_user(self):
        self.user.is_active = False
        self.user.save()
        r = self.client.post(self.URL, {
            "email": "login@example.com",
            "password": "MyPass123!",
        })
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)


# ═════════════════════════════════════════════════════════════════════════════
# Logout API
# ═════════════════════════════════════════════════════════════════════════════

class LogoutAPITest(APITestCase):

    URL = "/api/auth/logout/"

    def setUp(self):
        self.user = make_user()
        self.client = auth_client(self.user)
        self.refresh = RefreshToken.for_user(self.user)

    def test_logout_success(self):
        r = self.client.post(self.URL, {"refresh": str(self.refresh)})
        self.assertEqual(r.status_code, status.HTTP_200_OK)

    def test_logout_blacklists_token(self):
        self.client.post(self.URL, {"refresh": str(self.refresh)})
        # Trying to use the same token again should fail
        r = self.client.post("/api/auth/token/refresh/", {"refresh": str(self.refresh)})
        self.assertEqual(r.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_logout_invalid_token(self):
        r = self.client.post(self.URL, {"refresh": "not-a-token"})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_logout_requires_auth(self):
        unauthed = APIClient()
        r = unauthed.post(self.URL, {"refresh": str(self.refresh)})
        self.assertEqual(r.status_code, status.HTTP_401_UNAUTHORIZED)


# ═════════════════════════════════════════════════════════════════════════════
# Token refresh API
# ═════════════════════════════════════════════════════════════════════════════

class TokenRefreshAPITest(APITestCase):

    URL = "/api/auth/token/refresh/"

    def test_refresh_success(self):
        user = make_user(email="refresh@example.com")
        refresh = RefreshToken.for_user(user)
        r = self.client.post(self.URL, {"refresh": str(refresh)})
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertIn("access", r.data)

    def test_refresh_invalid_token(self):
        r = self.client.post(self.URL, {"refresh": "garbage"})
        self.assertEqual(r.status_code, status.HTTP_401_UNAUTHORIZED)


# ═════════════════════════════════════════════════════════════════════════════
# Google OAuth service unit tests (all mocked — no real Google calls)
# ═════════════════════════════════════════════════════════════════════════════

class GoogleAuthServiceTest(TestCase):

    @patch("apps.users.services.google_auth.id_token.verify_oauth2_token")
    def test_verify_returns_user_info(self, mock_verify):
        mock_verify.return_value = {
            "sub": "google-sub-abc",
            "email": "g@example.com",
            "name": "G User",
            "picture": "https://pic.url",
            "email_verified": True,
            "iss": "accounts.google.com",
        }
        with self.settings(GOOGLE_OAUTH_CLIENT_ID="test-client-id"):
            info = verify_google_id_token("fake-token")

        self.assertEqual(info.email, "g@example.com")
        self.assertEqual(info.google_id, "google-sub-abc")
        self.assertTrue(info.email_verified)

    @patch("apps.users.services.google_auth.id_token.verify_oauth2_token")
    def test_verify_raises_on_invalid_token(self, mock_verify):
        mock_verify.side_effect = ValueError("Token expired")
        with self.settings(GOOGLE_OAUTH_CLIENT_ID="test-client-id"):
            with self.assertRaises(GoogleTokenError):
                verify_google_id_token("expired-token")

    @patch("apps.users.services.google_auth.id_token.verify_oauth2_token")
    def test_verify_raises_on_unverified_email(self, mock_verify):
        mock_verify.return_value = {
            "sub": "sub", "email": "e@e.com", "email_verified": False,
            "iss": "accounts.google.com",
        }
        with self.settings(GOOGLE_OAUTH_CLIENT_ID="test-client-id"):
            with self.assertRaises(GoogleTokenError) as ctx:
                verify_google_id_token("token")
        self.assertIn("not verified", str(ctx.exception))

    @patch("apps.users.services.google_auth.id_token.verify_oauth2_token")
    def test_verify_raises_on_bad_issuer(self, mock_verify):
        mock_verify.return_value = {
            "sub": "sub", "email": "e@e.com", "email_verified": True,
            "iss": "evil.com",
        }
        with self.settings(GOOGLE_OAUTH_CLIENT_ID="test-client-id"):
            with self.assertRaises(GoogleTokenError):
                verify_google_id_token("token")

    def test_get_or_create_new_user(self):
        user, created = get_or_create_google_user(SAMPLE_GOOGLE_INFO)
        self.assertTrue(created)
        self.assertEqual(user.email, SAMPLE_GOOGLE_INFO.email)
        self.assertEqual(SocialAccount.objects.filter(user=user).count(), 1)

    def test_get_or_create_existing_social_account(self):
        # Create user + social account
        user, _ = get_or_create_google_user(SAMPLE_GOOGLE_INFO)
        # Second call — should find, not create
        user2, created = get_or_create_google_user(SAMPLE_GOOGLE_INFO)
        self.assertFalse(created)
        self.assertEqual(user.id, user2.id)
        self.assertEqual(SocialAccount.objects.count(), 1)

    def test_get_or_create_links_existing_email_user(self):
        # Existing user created with email/password
        existing = make_user(email=SAMPLE_GOOGLE_INFO.email)
        user, created = get_or_create_google_user(SAMPLE_GOOGLE_INFO)
        self.assertFalse(created)
        self.assertEqual(user.id, existing.id)
        # Google social account should now be linked
        self.assertTrue(SocialAccount.objects.filter(user=user, provider="google").exists())

    def test_get_or_create_syncs_profile(self):
        updated_info = GoogleUserInfo(
            google_id=SAMPLE_GOOGLE_INFO.google_id,
            email=SAMPLE_GOOGLE_INFO.email,
            name="Updated Name",
            avatar_url="https://new-avatar.url",
            email_verified=True,
        )
        user, _ = get_or_create_google_user(SAMPLE_GOOGLE_INFO)
        user2, _ = get_or_create_google_user(updated_info)
        self.assertEqual(user2.name, "Updated Name")
        self.assertEqual(user2.avatar_url, "https://new-avatar.url")


# ═════════════════════════════════════════════════════════════════════════════
# Google OAuth API endpoint
# ═════════════════════════════════════════════════════════════════════════════

class GoogleAuthAPITest(APITestCase):

    URL = "/api/auth/google/"

    @patch("apps.users.views.authenticate_google_user")
    def test_google_login_new_user(self, mock_auth):
        from apps.users.services.google_auth import AuthResult
        user = make_user(email="gapi@example.com", name="G API User")
        mock_auth.return_value = AuthResult(
            user=user,
            access_token="fake-access",
            refresh_token="fake-refresh",
            created=True,
        )
        r = self.client.post(self.URL, {"id_token": "valid-google-token"})
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        self.assertEqual(r.data["access"], "fake-access")
        self.assertTrue(r.data["created"])

    @patch("apps.users.views.authenticate_google_user")
    def test_google_login_existing_user(self, mock_auth):
        from apps.users.services.google_auth import AuthResult
        user = make_user(email="existing@example.com")
        mock_auth.return_value = AuthResult(
            user=user,
            access_token="access-token",
            refresh_token="refresh-token",
            created=False,
        )
        r = self.client.post(self.URL, {"id_token": "valid-google-token"})
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertFalse(r.data["created"])

    @patch("apps.users.views.authenticate_google_user")
    def test_google_login_invalid_token_returns_401(self, mock_auth):
        mock_auth.side_effect = GoogleTokenError("Token expired")
        r = self.client.post(self.URL, {"id_token": "bad-token"})
        self.assertEqual(r.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_google_login_missing_token(self):
        r = self.client.post(self.URL, {})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)


# ═════════════════════════════════════════════════════════════════════════════
# Profile API
# ═════════════════════════════════════════════════════════════════════════════

class ProfileAPITest(APITestCase):

    URL = "/api/users/me/"

    def setUp(self):
        self.user = make_user(email="profile@example.com", name="Profile User")
        self.client = auth_client(self.user)

    def test_get_profile(self):
        r = self.client.get(self.URL)
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(r.data["email"], "profile@example.com")
        self.assertEqual(r.data["name"], "Profile User")

    def test_update_name(self):
        r = self.client.patch(self.URL, {"name": "Updated Name"})
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertEqual(self.user.name, "Updated Name")

    def test_profile_requires_auth(self):
        unauthed = APIClient()
        r = unauthed.get(self.URL)
        self.assertEqual(r.status_code, status.HTTP_401_UNAUTHORIZED)


# ═════════════════════════════════════════════════════════════════════════════
# Password change API
# ═════════════════════════════════════════════════════════════════════════════

class PasswordChangeAPITest(APITestCase):

    URL = "/api/users/me/change-password/"

    def setUp(self):
        self.user = make_user(email="pwchange@example.com", password="OldPass123!")
        self.client = auth_client(self.user)

    def test_change_password_success(self):
        r = self.client.post(self.URL, {
            "current_password": "OldPass123!",
            "new_password": "NewPass456!",
            "confirm_new_password": "NewPass456!",
        })
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("NewPass456!"))

    def test_wrong_current_password(self):
        r = self.client.post(self.URL, {
            "current_password": "WrongOld!",
            "new_password": "NewPass456!",
            "confirm_new_password": "NewPass456!",
        })
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_new_passwords_mismatch(self):
        r = self.client.post(self.URL, {
            "current_password": "OldPass123!",
            "new_password": "NewPass456!",
            "confirm_new_password": "DifferentPass789!",
        })
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_requires_auth(self):
        unauthed = APIClient()
        r = unauthed.post(self.URL, {})
        self.assertEqual(r.status_code, status.HTTP_401_UNAUTHORIZED)
