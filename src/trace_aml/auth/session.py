from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Callable
from uuid import uuid4

from trace_aml.auth.models import AuthIdentity, AuthSessionRecord, BrowserAuthFlowRecord
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


@dataclass(slots=True)
class BrowserAuthFlowManager:
    session_manager: DesktopSessionManager
    now_fn: Callable[[], datetime] | None = None
    flow_ttl_minutes: int = 10
    _flows_by_id: dict[str, BrowserAuthFlowRecord] = field(init=False, default_factory=dict)
    _flow_ids_by_state: dict[str, str] = field(init=False, default_factory=dict)
    _now: Callable[[], datetime] = field(init=False)

    def __post_init__(self) -> None:
        self._now = self.now_fn or (lambda: datetime.now(UTC))

    def create_flow(self, next_path: str) -> BrowserAuthFlowRecord:
        self._prune_expired()
        now = self._now()
        record = BrowserAuthFlowRecord(
            flow_id=uuid4().hex,
            state=uuid4().hex,
            next_path=next_path,
            created_at=now,
            expires_at=now + timedelta(minutes=self.flow_ttl_minutes),
        )
        self._flows_by_id[record.flow_id] = record
        self._flow_ids_by_state[record.state] = record.flow_id
        return record

    def mark_completed(self, state: str, session_record: AuthSessionRecord) -> BrowserAuthFlowRecord:
        record = self._require_by_state(state)
        record.status = "authenticated"
        record.detail = "TRACE-AML authorization complete. Return to the desktop app."
        record.session_id = session_record.session_id
        record.user = session_record.display
        record.expires_at = min(
            record.expires_at,
            session_record.expires_at,
        )
        return record

    def mark_failed(self, state: str, detail: str) -> BrowserAuthFlowRecord:
        record = self._require_by_state(state)
        record.status = "failed"
        record.detail = detail
        record.session_id = ""
        record.user = None
        return record

    def get_status(self, flow_id: str) -> BrowserAuthFlowRecord:
        self._prune_expired()
        record = self._flows_by_id.get(flow_id)
        if record is None:
            raise AuthSessionError(
                "Authorization request is missing or expired.",
                code="flow_missing",
                status_code=404,
            )
        return record

    def consume_session(self, flow_id: str) -> AuthSessionRecord:
        record = self.get_status(flow_id)
        if record.status != "authenticated" or not record.session_id:
            raise AuthSessionError(
                "Authorization request is not ready yet.",
                code="flow_pending",
                status_code=409,
            )

        session_record = self.session_manager.validate_session(record.session_id)
        self._drop_flow(record)
        return session_record

    def _require_by_state(self, state: str) -> BrowserAuthFlowRecord:
        self._prune_expired()
        flow_id = self._flow_ids_by_state.get(state)
        if not flow_id:
            raise AuthSessionError(
                "Authorization request is missing or expired.",
                code="flow_missing",
                status_code=404,
            )
        record = self._flows_by_id.get(flow_id)
        if record is None:
            raise AuthSessionError(
                "Authorization request is missing or expired.",
                code="flow_missing",
                status_code=404,
            )
        return record

    def _prune_expired(self) -> None:
        now = self._now()
        expired_flow_ids = [
            flow_id
            for flow_id, record in self._flows_by_id.items()
            if record.expires_at <= now
        ]
        for flow_id in expired_flow_ids:
            record = self._flows_by_id.pop(flow_id, None)
            if record is not None:
                self._flow_ids_by_state.pop(record.state, None)

    def _drop_flow(self, record: BrowserAuthFlowRecord) -> None:
        self._flows_by_id.pop(record.flow_id, None)
        self._flow_ids_by_state.pop(record.state, None)
