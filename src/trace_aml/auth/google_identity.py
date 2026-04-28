from __future__ import annotations

from dataclasses import dataclass

from trace_aml.auth.models import AuthIdentity


class GoogleIdentityVerificationError(RuntimeError):
    """Raised when the Google credential cannot be verified."""


@dataclass(slots=True)
class GoogleIdentityVerifier:
    client_id: str

    def verify(self, credential: str) -> AuthIdentity:
        if not str(self.client_id or "").strip():
            raise GoogleIdentityVerificationError("Google client ID is not configured for this build.")
        if not str(credential or "").strip():
            raise GoogleIdentityVerificationError("Google credential was empty.")

        try:
            from google.auth.transport.requests import Request
            from google.oauth2 import id_token
        except Exception as exc:  # pragma: no cover - dependency/runtime path.
            raise GoogleIdentityVerificationError(
                "google-auth dependency is missing; cannot verify Google credentials."
            ) from exc

        try:
            claims = id_token.verify_oauth2_token(credential, Request(), self.client_id)
        except Exception as exc:  # pragma: no cover - network/runtime path.
            raise GoogleIdentityVerificationError("Google credential verification failed.") from exc

        if str(claims.get("email_verified", "")).lower() not in {"true", "1"}:
            raise GoogleIdentityVerificationError("Google account email is not verified.")

        email = str(claims.get("email") or "").strip()
        if not email:
            raise GoogleIdentityVerificationError("Google credential did not include an email address.")

        return AuthIdentity(
            email=email,
            display_name=str(claims.get("name") or "").strip(),
            avatar_url=str(claims.get("picture") or "").strip(),
            subject=str(claims.get("sub") or "").strip(),
        )

