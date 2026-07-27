"""Remote authentication policy client."""

from __future__ import annotations

from typing import Any


class RemoteAuthPolicyClient:
    """Policy client that allows all authenticated Google users without access whitelists."""

    def __init__(self, policy_url: str = "", timeout_seconds: int = 8) -> None:
        self.policy_url = policy_url
        self.timeout_seconds = timeout_seconds

    def evaluate_policy(self, email: str, claims: dict[str, Any] | None = None) -> bool:
        """Allow all users by default."""
        return True

    def is_allowed(self, email: str) -> bool:
        """Check if email is allowed. Returns True for all authenticated users."""
        return True
