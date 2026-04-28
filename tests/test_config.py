import importlib
from pathlib import Path

import pytest

import trace_aml.core.config as config_module


def test_load_settings_defaults(tmp_path: Path) -> None:
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        """
camera:
  device_index: 0
store:
  root: demo_data
  vectors_dir: demo_data/vectors
  screenshots_dir: demo_data/screens
  exports_dir: demo_data/exports
""".strip(),
        encoding="utf-8",
    )
    settings = config_module.load_settings(cfg)
    assert settings.camera.device_index == 0
    assert settings.store.vectors_dir == "demo_data/vectors"
    assert settings.quality.min_valid_images >= 1
    assert settings.temporal.decision_window >= 1
    assert settings.recognition.accept_threshold > settings.recognition.review_threshold
    assert settings.auth.enabled is False
    assert settings.auth.google_client_id == ""
    assert settings.auth.policy_url == ""


def test_rejects_non_zero_camera(tmp_path: Path) -> None:
    cfg = tmp_path / "bad.yaml"
    cfg.write_text(
        """
camera:
  device_index: 1
""".strip(),
        encoding="utf-8",
    )
    with pytest.raises(config_module.ConfigError):
        config_module.load_settings(cfg)


def test_portable_defaults_follow_trace_data_root(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TRACE_DATA_ROOT", "portable_data")
    importlib.reload(config_module)
    try:
        assert config_module.StoreSettings().vectors_dir == "portable_data/vectors"
        assert config_module.PdfReportSettings().output_dir == "portable_data/exports"
        assert config_module.LoggingSettings().file_path == "portable_data/logs/trace_aml.log"
    finally:
        monkeypatch.delenv("TRACE_DATA_ROOT", raising=False)
        importlib.reload(config_module)


def test_load_settings_accepts_auth_block(tmp_path: Path) -> None:
    cfg = tmp_path / "auth.yaml"
    cfg.write_text(
        """
auth:
  enabled: true
  google_client_id: trace-client-id.apps.googleusercontent.com
  policy_url: https://example.com/auth-policy.json
  session_ttl_minutes: 20
  validation_interval_seconds: 75
  request_timeout_seconds: 9
camera:
  device_index: 0
""".strip(),
        encoding="utf-8",
    )
    settings = config_module.load_settings(cfg)
    assert settings.auth.enabled is True
    assert settings.auth.google_client_id.endswith(".apps.googleusercontent.com")
    assert settings.auth.policy_url == "https://example.com/auth-policy.json"
    assert settings.auth.session_ttl_minutes == 20
    assert settings.auth.validation_interval_seconds == 75
    assert settings.auth.request_timeout_seconds == 9


def test_load_settings_env_overrides_yaml_auth(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    cfg = tmp_path / "auth.yaml"
    cfg.write_text(
        """
auth:
  enabled: false
  google_client_id: ""
  policy_url: ""
camera:
  device_index: 0
""".strip(),
        encoding="utf-8",
    )

    monkeypatch.setenv("TRACE_AML_AUTH__ENABLED", "true")
    monkeypatch.setenv(
        "TRACE_AML_AUTH__GOOGLE_CLIENT_ID",
        "desktop-client.apps.googleusercontent.com",
    )
    monkeypatch.setenv(
        "TRACE_AML_AUTH__POLICY_URL",
        "https://example.com/policy.json",
    )
    monkeypatch.setenv("TRACE_AML_AUTH__SESSION_TTL_MINUTES", "12")
    monkeypatch.setenv("TRACE_AML_AUTH__VALIDATION_INTERVAL_SECONDS", "45")

    settings = config_module.load_settings(cfg)

    assert settings.auth.enabled is True
    assert settings.auth.google_client_id == "desktop-client.apps.googleusercontent.com"
    assert settings.auth.policy_url == "https://example.com/policy.json"
    assert settings.auth.session_ttl_minutes == 12
    assert settings.auth.validation_interval_seconds == 45
