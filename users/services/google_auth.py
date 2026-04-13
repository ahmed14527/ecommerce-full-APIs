"""
apps/users/services/google_auth.py

Service layer for Google OAuth ID-token authentication.

Flow:
  1. Frontend obtains a Google ID token (e.g. from Google Sign-In / One Tap).
  2. Frontend sends the raw ID token to POST /api/auth/google/.
  3. This service verifies the token cryptographically against Google's public
     keys — we never trust the frontend payload directly.
  4. If valid, we find-or-create the user and return JWT tokens.

Why verify server-side?
  Verifying with `google-auth` downloads Google's public key set and checks
  the token signature, audience (CLIENT_ID), and expiry. This cannot be
  spoofed by a malicious client.

Dependencies:
  pip install google-auth
"""

import logging
from dataclasses import dataclass
from typing import Optional

from django.conf import settings
from django.db import transaction
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token
from rest_framework_simplejwt.tokens import RefreshToken

from users.models import SocialAccount, User

logger = logging.getLogger(__name__)


# ── Data transfer objects ─────────────────────────────────────────────────────

@dataclass(frozen=True)
class GoogleUserInfo:
    """
    Typed container for the claims we extract from a verified Google ID token.
    Frozen so it cannot be accidentally mutated downstream.
    """
    google_id: str          # 'sub' — stable unique ID in Google's system
    email: str
    name: str
    avatar_url: str
    email_verified: bool


@dataclass(frozen=True)
class AuthResult:
    """Returned to the view after a successful Google login."""
    user: User
    access_token: str
    refresh_token: str
    created: bool           # True if this is a brand-new user


# ── Token verification ────────────────────────────────────────────────────────

class GoogleTokenError(Exception):
    """Raised for any problem with the Google ID token."""


def verify_google_id_token(raw_token: str) -> GoogleUserInfo:
    """
    Verify a Google ID token and extract user info.

    Raises GoogleTokenError on:
      - Invalid signature
      - Wrong audience (not our CLIENT_ID)
      - Expired token
      - Unverified email
      - Missing required claims

    Args:
        raw_token: The raw ID token string sent by the frontend.

    Returns:
        GoogleUserInfo with verified claims.
    """
    client_id = settings.GOOGLE_OAUTH_CLIENT_ID
    if not client_id:
        raise GoogleTokenError("GOOGLE_OAUTH_CLIENT_ID is not configured.")

    try:
        # `verify_oauth2_token` fetches Google's public keys, verifies the
        # signature, checks the `aud` claim matches our CLIENT_ID, and
        # validates the `exp` claim.  This is the only safe way to verify.
        claims = id_token.verify_oauth2_token(
            raw_token,
            google_requests.Request(),
            client_id,
        )
    except ValueError as exc:
        # google-auth raises ValueError for all verification failures
        logger.warning("Google ID token verification failed: %s", exc)
        raise GoogleTokenError(f"Invalid Google token: {exc}") from exc

    # Double-check the issuer — must be accounts.google.com
    issuer = claims.get("iss", "")
    if issuer not in ("accounts.google.com", "https://accounts.google.com"):
        raise GoogleTokenError(f"Unexpected token issuer: {issuer}")

    # We refuse to create accounts for unverified emails
    if not claims.get("email_verified", False):
        raise GoogleTokenError("Google email is not verified.")

    # Extract required claims — raise clearly if any are missing
    try:
        return GoogleUserInfo(
            google_id=claims["sub"],
            email=claims["email"],
            name=claims.get("name", ""),
            avatar_url=claims.get("picture", ""),
            email_verified=True,
        )
    except KeyError as exc:
        raise GoogleTokenError(f"Missing required claim: {exc}") from exc


# ── User provisioning ─────────────────────────────────────────────────────────

def _build_jwt_tokens(user: User) -> tuple[str, str]:
    """Return (access_token_str, refresh_token_str) for a given user."""
    refresh = RefreshToken.for_user(user)
    return str(refresh.access_token), str(refresh)


@transaction.atomic
def get_or_create_google_user(info: GoogleUserInfo) -> tuple[User, bool]:
    """
    Find an existing user by their Google provider ID, then by email,
    or create a new one.

    Strategy (in order):
      1. Existing SocialAccount with this google_id   → return that user
      2. Existing User with same email (no SocialAccount) → link & return
      3. No user at all → create User + SocialAccount

    The whole thing runs in a transaction so we never create a User without
    a SocialAccount or vice-versa.

    Args:
        info: Verified GoogleUserInfo from verify_google_id_token().

    Returns:
        (user, created) — created=True only if a brand-new User was made.
    """
    # ── Step 1: look up by provider ID ───────────────────────────────────────
    try:
        social = SocialAccount.objects.select_related("user").get(
            provider=SocialAccount.Provider.GOOGLE,
            provider_user_id=info.google_id,
        )
        # Refresh avatar / name on every login in case Google profile changed
        user = social.user
        _sync_user_profile(user, info)
        _sync_social_extra_data(social, info)
        return user, False

    except SocialAccount.DoesNotExist:
        pass

    # ── Step 2: look up by email (existing non-Google account) ───────────────
    try:
        user = User.objects.get(email=info.email)
        # Link the Google provider to this existing account
        SocialAccount.objects.create(
            user=user,
            provider=SocialAccount.Provider.GOOGLE,
            provider_user_id=info.google_id,
            extra_data=_build_extra_data(info),
        )
        _sync_user_profile(user, info)
        logger.info("Linked Google account to existing user: %s", user.email)
        return user, False

    except User.DoesNotExist:
        pass

    # ── Step 3: create brand-new user ─────────────────────────────────────────
    user = User.objects.create_user(
        email=info.email,
        password=None,          # Google-only accounts have no usable password
        name=info.name,
        avatar_url=info.avatar_url,
    )
    SocialAccount.objects.create(
        user=user,
        provider=SocialAccount.Provider.GOOGLE,
        provider_user_id=info.google_id,
        extra_data=_build_extra_data(info),
    )
    logger.info("Created new user via Google OAuth: %s", user.email)
    return user, True


# ── Public entry point ────────────────────────────────────────────────────────

def authenticate_google_user(raw_token: str) -> AuthResult:
    """
    Full Google OAuth flow: verify token → provision user → issue JWTs.

    This is the only function views should call.

    Args:
        raw_token: Raw Google ID token string from the request body.

    Returns:
        AuthResult with user + JWT tokens.

    Raises:
        GoogleTokenError: If token verification fails for any reason.
    """
    info = verify_google_id_token(raw_token)
    user, created = get_or_create_google_user(info)

    if not user.is_active:
        raise GoogleTokenError("This account has been deactivated.")

    access_token, refresh_token = _build_jwt_tokens(user)

    return AuthResult(
        user=user,
        access_token=access_token,
        refresh_token=refresh_token,
        created=created,
    )


# ── Private helpers ───────────────────────────────────────────────────────────

def _sync_user_profile(user: User, info: GoogleUserInfo) -> None:
    """Update user profile fields that may change between Google logins."""
    changed = False
    if info.name and user.name != info.name:
        user.name = info.name
        changed = True
    if info.avatar_url and user.avatar_url != info.avatar_url:
        user.avatar_url = info.avatar_url
        changed = True
    if changed:
        user.save(update_fields=["name", "avatar_url", "updated_at"])


def _sync_social_extra_data(social: SocialAccount, info: GoogleUserInfo) -> None:
    """Refresh the JSON snapshot on the SocialAccount."""
    social.extra_data = _build_extra_data(info)
    social.save(update_fields=["extra_data", "updated_at"])


def _build_extra_data(info: GoogleUserInfo) -> dict:
    return {
        "google_id": info.google_id,
        "email": info.email,
        "name": info.name,
        "avatar_url": info.avatar_url,
    }
