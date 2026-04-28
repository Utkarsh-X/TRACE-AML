from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi.testclient import TestClient

from trace_aml.auth.models import AuthIdentity, AuthPolicy
from trace_aml.auth.session import DesktopSessionManager
from trace_aml.core.config import load_settings
from trace_aml.core.streaming import InMemoryEventStreamPublisher
from trace_aml.service.app import create_service_app
from trace_aml.store.vector_store import VectorStore


class _MutableClock:
    def __init__(self, start: datetime | None = None) -> None:
        self.current = start or datetime(2026, 4, 28, 12, 0, tzinfo=UTC)

    def now(self) -> datetime:
        return self.current

    def advance(self, *, seconds: int = 0, minutes: int = 0) -> None:
        self.current += timedelta(seconds=seconds, minutes=minutes)


class _StubPolicyClient:
    def __init__(self, allowed_emails: list[str]) -> None:
        self.allowed_emails = allowed_emails

    def get_policy(self) -> AuthPolicy:
        return AuthPolicy(
            version=1,
            allowed_emails=list(self.allowed_emails),
            message="Authorized desktop users only.",
        )


class _StubGoogleVerifier:
    def __init__(self, identity: AuthIdentity) -> None:
        self.identity = identity

    def verify(self, credential: str) -> AuthIdentity:
        assert credential == "good-token"
        return self.identity


def _settings(tmp_path: Path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        f"""
auth:
  enabled: true
  google_client_id: trace-client-id.apps.googleusercontent.com
  policy_url: https://example.com/auth-policy.json
  session_ttl_minutes: 15
  validation_interval_seconds: 60
camera:
  device_index: 0
store:
  root: {tmp_path.as_posix()}/data
  vectors_dir: {tmp_path.as_posix()}/data/vectors
  screenshots_dir: {tmp_path.as_posix()}/data/screens
  exports_dir: {tmp_path.as_posix()}/data/exports
""".strip(),
        encoding="utf-8",
    )
    return load_settings(cfg)


def test_auth_enabled_blocks_api_without_session_and_redirects_ui(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    store = VectorStore(settings)
    publisher = InMemoryEventStreamPublisher()

    app = create_service_app(settings=settings, store=store, stream_publisher=publisher)
    client = TestClient(app)

    snapshot = client.get("/api/v1/live/snapshot")
    assert snapshot.status_code == 401

    ui = client.get("/ui/live_ops/index.html", follow_redirects=False)
    assert ui.status_code in {302, 307}
    assert "/ui/auth/index.html" in ui.headers["location"]


def test_google_login_creates_session_cookie_and_unlocks_protected_api(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    store = VectorStore(settings)
    publisher = InMemoryEventStreamPublisher()
    clock = _MutableClock()
    policy_client = _StubPolicyClient(["allowed@example.com"])
    identity = AuthIdentity(
        email="allowed@example.com",
        display_name="Allowed User",
        avatar_url="https://example.com/avatar.png",
        subject="google-subject-1",
    )
    auth_runtime = {
        "identity_verifier": _StubGoogleVerifier(identity),
        "policy_client": policy_client,
        "session_manager": DesktopSessionManager(
            settings.auth,
            policy_client=policy_client,
            now_fn=clock.now,
        ),
    }

    app = create_service_app(
        settings=settings,
        store=store,
        stream_publisher=publisher,
        auth_runtime=auth_runtime,
    )
    client = TestClient(app)

    login = client.post("/api/v1/auth/google", json={"credential": "good-token"})
    assert login.status_code == 200
    assert login.cookies.get("trace_aml_session")

    snapshot = client.get("/api/v1/live/snapshot")
    assert snapshot.status_code == 200


def test_remote_policy_revocation_invalidates_existing_session(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    store = VectorStore(settings)
    publisher = InMemoryEventStreamPublisher()
    clock = _MutableClock()
    policy_client = _StubPolicyClient(["allowed@example.com"])
    identity = AuthIdentity(
        email="allowed@example.com",
        display_name="Allowed User",
        avatar_url="https://example.com/avatar.png",
        subject="google-subject-1",
    )
    session_manager = DesktopSessionManager(
        settings.auth,
        policy_client=policy_client,
        now_fn=clock.now,
    )
    auth_runtime = {
        "identity_verifier": _StubGoogleVerifier(identity),
        "policy_client": policy_client,
        "session_manager": session_manager,
    }

    app = create_service_app(
        settings=settings,
        store=store,
        stream_publisher=publisher,
        auth_runtime=auth_runtime,
    )
    client = TestClient(app)

    login = client.post("/api/v1/auth/google", json={"credential": "good-token"})
    assert login.status_code == 200

    assert client.get("/api/v1/live/snapshot").status_code == 200

    policy_client.allowed_emails.clear()
    clock.advance(seconds=settings.auth.validation_interval_seconds + 1)

    revoked = client.get("/api/v1/auth/session")
    assert revoked.status_code == 401

    snapshot = client.get("/api/v1/live/snapshot")
    assert snapshot.status_code == 401
