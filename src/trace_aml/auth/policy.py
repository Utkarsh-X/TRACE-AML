from __future__ import annotations

from dataclasses import dataclass

import httpx

from trace_aml.auth.models import AuthPolicy


class AuthPolicyError(RuntimeError):
    """Raised when remote access policy cannot be loaded or parsed."""


@dataclass(slots=True)
class RemoteAuthPolicyClient:
    policy_url: str
    timeout_seconds: int = 8

    def get_policy(self) -> AuthPolicy:
        if not str(self.policy_url or "").strip():
            raise AuthPolicyError("Remote auth policy URL is not configured.")

        try:
            response = httpx.get(
                self.policy_url,
                headers={"Accept": "application/json"},
                timeout=self.timeout_seconds,
                follow_redirects=True,
            )
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:  # pragma: no cover - exercised through app/service tests.
            raise AuthPolicyError("Unable to refresh remote access policy.") from exc

        try:
            return AuthPolicy.model_validate(payload)
        except Exception as exc:  # pragma: no cover - schema error path.
            raise AuthPolicyError("Remote access policy payload is invalid.") from exc

