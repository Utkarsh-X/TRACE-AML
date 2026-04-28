from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Callable
from uuid import uuid4

from trace_aml.auth.models import AuthIdentity, AuthSessionRecord
from trace_aml.auth.policy import AuthPolicyError


class AuthSessionError(RuntimeError):
    def __init__(self, detail: str, *, code: str = "unauthorized", status_code: int = 401) -> None:
        super().__init__(detail)
        self.detail = detail
        self.code = code
        self.status_code = status_code


@dataclass(slots=True)
class DesktopSessionManager:
    auth_settings: object
    policy_client: object
    now_fn: Callable[[], datetime] | None = None
    _sessions: dict[str, AuthSessionRecord] = field(init=False, default_factory=dict)
    _now: Callable[[], datetime] = field(init=False)

    def __post_init__(self) -> None:
        self._now = self.now_fn or (lambda: datetime.now(UTC))

    def issue_session(self, identity: AuthIdentity) -> AuthSessionRecord:
        policy = self._get_policy()
        if not policy.allows(identity.email):
            raise AuthSessionError(
                policy.message or "This Google account is not approved for TRACE-AML.",
                code="allowlist_denied",
                status_code=403,
            )

        now = self._now()
        record = AuthSessionRecord(
            session_id=uuid4().hex,
            identity=identity,
            issued_at=now,
            expires_at=now + timedelta(minutes=self.auth_settings.session_ttl_minutes),
            last_validated_at=now,
        )
        self._sessions[record.session_id] = record
        return record

    def revoke_session(self, session_id: str | None) -> None:
        if not session_id:
            return
        self._sessions.pop(session_id, None)

    def validate_session(self, session_id: str | None) -> AuthSessionRecord:
        if not session_id:
            raise AuthSessionError("Authentication is required.", code="missing_session")

        record = self._sessions.get(session_id)
        if record is None:
            raise AuthSessionError("Desktop session is missing or no longer valid.", code="invalid_session")

        now = self._now()
        if record.expires_at <= now:
            self._sessions.pop(session_id, None)
            raise AuthSessionError("Desktop session expired. Please sign in again.", code="session_expired")

        age_seconds = (now - record.last_validated_at).total_seconds()
        if age_seconds >= self.auth_settings.validation_interval_seconds:
            policy = self._get_policy()
            if not policy.allows(record.identity.email):
                self._sessions.pop(session_id, None)
                raise AuthSessionError(
                    policy.message or "Access for this Google account has been revoked.",
                    code="session_revoked",
                )
            record.last_validated_at = now
            record.expires_at = now + timedelta(minutes=self.auth_settings.session_ttl_minutes)

        return record

    def _get_policy(self):
        try:
            return self.policy_client.get_policy()
        except AuthPolicyError as exc:
            raise AuthSessionError(
                "Online access validation failed. TRACE-AML cannot be used offline in this build.",
                code="policy_unavailable",
            ) from exc
