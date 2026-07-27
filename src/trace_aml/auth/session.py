"""Session management and browser OAuth flow tracking."""

from __future__ import annotations

import secrets
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from trace_aml.auth.policy import RemoteAuthPolicyClient


class AuthSessionError(Exception):
    """Raised when session validation or flow consumption fails."""

    def __init__(self, detail: str, status_code: int = 401, code: str = "AUTH_REQUIRED") -> None:
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code
        self.code = code


@dataclass
class AuthSessionRecord:
    session_id: str
    user_email: str
    display: dict[str, Any]
    expires_at: datetime
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class BrowserFlowRecord:
    flow_id: str
    state: str
    status: str  # "pending", "authenticated", "failed"
    next_path: str
    detail: str = ""


class DesktopSessionManager:
    """Manages active desktop and web sessions."""

    def __init__(
        self,
        auth_settings: Any,
        policy_client: RemoteAuthPolicyClient | None = None,
        now_fn: Any | None = None,
    ) -> None:
        self.auth_settings = auth_settings
        self.policy_client = policy_client or RemoteAuthPolicyClient()
        self.now_fn = now_fn
        self._sessions: dict[str, AuthSessionRecord] = {}

    def _now(self) -> datetime:
        if self.now_fn is not None:
            val = self.now_fn()
            if isinstance(val, (int, float)):
                return datetime.fromtimestamp(val, tz=timezone.utc)
            if isinstance(val, datetime):
                return val if val.tzinfo is not None else val.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc)

    def issue_session(self, identity: Any) -> AuthSessionRecord:
        """Issue a new session for an authenticated user."""
        email = getattr(identity, "email", "user@example.com")
        name = getattr(identity, "name", email.split("@")[0])
        picture = getattr(identity, "picture", "")

        ttl_minutes = getattr(self.auth_settings, "session_ttl_minutes", 15)
        expires_at = self._now() + timedelta(minutes=ttl_minutes)
        session_id = f"sess_{secrets.token_urlsafe(24)}"

        record = AuthSessionRecord(
            session_id=session_id,
            user_email=email,
            display={"email": email, "name": name, "picture": picture},
            expires_at=expires_at,
        )
        self._sessions[session_id] = record
        return record

    def validate_session(self, session_id: str | None) -> AuthSessionRecord:
        """Validate an active session by ID."""
        if not session_id or session_id not in self._sessions:
            raise AuthSessionError("Invalid or expired session token.", status_code=401, code="AUTH_REQUIRED")
        record = self._sessions[session_id]
        if self._now() > record.expires_at:
            self._sessions.pop(session_id, None)
            raise AuthSessionError("Session has expired.", status_code=401, code="AUTH_EXPIRED")
        if self.policy_client:
            if hasattr(self.policy_client, "is_allowed"):
                if not self.policy_client.is_allowed(record.user_email):
                    self._sessions.pop(session_id, None)
                    raise AuthSessionError("Access revoked by remote policy.", status_code=401, code="POLICY_REVOKED")
            elif hasattr(self.policy_client, "get_policy"):
                pol = self.policy_client.get_policy()
                allowed = getattr(pol, "allowed_emails", None)
                if allowed is not None and record.user_email not in allowed:
                    self._sessions.pop(session_id, None)
                    raise AuthSessionError("Access revoked by remote policy.", status_code=401, code="POLICY_REVOKED")
        return record

    def revoke_session(self, session_id: str | None) -> None:
        """Revoke a session."""
        if session_id:
            self._sessions.pop(session_id, None)


class BrowserAuthFlowManager:
    """Tracks state and completion for browser-based OAuth logins."""

    def __init__(
        self,
        session_manager: DesktopSessionManager,
        now_fn: Callable[[], float] | None = None,
    ) -> None:
        self.session_manager = session_manager
        self.now_fn = now_fn or time.time
        self._flows: dict[str, BrowserFlowRecord] = {}
        self._state_to_flow: dict[str, str] = {}
        self._completed_sessions: dict[str, AuthSessionRecord] = {}

    def create_flow(self, next_path: str = "/ui/live_ops/index.html") -> BrowserFlowRecord:
        flow_id = f"flow_{secrets.token_urlsafe(16)}"
        state = f"state_{secrets.token_urlsafe(16)}"
        record = BrowserFlowRecord(
            flow_id=flow_id,
            state=state,
            status="pending",
            next_path=next_path,
        )
        self._flows[flow_id] = record
        self._state_to_flow[state] = flow_id
        return record

    def get_status(self, flow_id: str) -> BrowserFlowRecord:
        if flow_id not in self._flows:
            raise AuthSessionError("OAuth flow not found or expired.", status_code=404)
        return self._flows[flow_id]

    def mark_completed(self, state: str, session_record: AuthSessionRecord) -> None:
        flow_id = self._state_to_flow.get(state)
        if flow_id and flow_id in self._flows:
            self._flows[flow_id].status = "authenticated"
            self._completed_sessions[flow_id] = session_record

    def mark_failed(self, state: str, detail: str) -> None:
        flow_id = self._state_to_flow.get(state)
        if flow_id and flow_id in self._flows:
            self._flows[flow_id].status = "failed"
            self._flows[flow_id].detail = detail

    def consume_session(self, flow_id: str) -> AuthSessionRecord:
        if flow_id not in self._flows:
            raise AuthSessionError("OAuth flow not found.", status_code=404)
        flow = self._flows[flow_id]
        if flow.status != "authenticated":
            raise AuthSessionError("Flow is not authenticated.", status_code=400)
        session = self._completed_sessions.get(flow_id)
        if not session:
            # Generate fallback session if needed
            session = self.session_manager.issue_session(None)
        return session
