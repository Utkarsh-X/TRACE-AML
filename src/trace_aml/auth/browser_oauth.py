from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlencode

import httpx


class BrowserOAuthError(RuntimeError):
    """Raised when the browser-based OAuth flow cannot proceed."""


@dataclass(slots=True)
class GoogleBrowserOAuthClient:
    client_id: str
    client_secret: str
    redirect_uri: str
    timeout_seconds: int = 8
    authorize_url: str = "https://accounts.google.com/o/oauth2/v2/auth"
    token_url: str = "https://oauth2.googleapis.com/token"

    def build_authorize_url(self, state: str) -> str:
        if not str(self.client_id or "").strip():
            raise BrowserOAuthError("Google client ID is not configured for this build.")
        if not str(self.client_secret or "").strip():
            raise BrowserOAuthError("Google client secret is not configured for this build.")
        if not str(self.redirect_uri or "").strip():
            raise BrowserOAuthError("Google redirect URI is not configured for this build.")

        query = urlencode(
            {
                "client_id": self.client_id,
                "redirect_uri": self.redirect_uri,
                "response_type": "code",
                "scope": "openid email profile",
                "state": state,
                "prompt": "select_account",
            }
        )
        return f"{self.authorize_url}?{query}"

    def exchange_code(self, code: str) -> str:
        if not str(code or "").strip():
            raise BrowserOAuthError("Google authorization code was empty.")

        try:
            response = httpx.post(
                self.token_url,
                data={
                    "code": code,
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "redirect_uri": self.redirect_uri,
                    "grant_type": "authorization_code",
                },
                headers={"Accept": "application/json"},
                timeout=self.timeout_seconds,
                follow_redirects=True,
            )
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:  # pragma: no cover - network/runtime path.
            raise BrowserOAuthError("Google authorization code exchange failed.") from exc

        id_token = str(payload.get("id_token") or "").strip()
        if not id_token:
            raise BrowserOAuthError("Google token response did not include an ID token.")
        return id_token
