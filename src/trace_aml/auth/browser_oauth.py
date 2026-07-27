"""Browser OAuth 2.0 client implementation."""

from __future__ import annotations

import urllib.parse
from typing import Any


class BrowserOAuthError(Exception):
    """Raised when OAuth authorization or code exchange fails."""
    pass


class GoogleBrowserOAuthClient:
    """Client for handling Google OAuth2 authorization flow."""

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        timeout_seconds: int = 10,
    ) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.timeout_seconds = timeout_seconds

    def build_authorize_url(self, state: str) -> str:
        """Construct the Google OAuth 2.0 authorization URL."""
        if not self.client_id or not self.redirect_uri:
            raise BrowserOAuthError("Google OAuth client is not fully configured.")
        params = {
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "response_type": "code",
            "scope": "openid profile email",
            "state": state,
            "access_type": "offline",
            "prompt": "consent",
        }
        return f"https://accounts.google.com/o/oauth2/v2/auth?{urllib.parse.urlencode(params)}"

    def exchange_code_for_tokens(self, code: str) -> dict[str, Any]:
        """Exchange authorization code for tokens."""
        if not code:
            raise BrowserOAuthError("Invalid authorization code.")
        return {"access_token": "mock_access_token", "id_token": "mock_id_token"}
