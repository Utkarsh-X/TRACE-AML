from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator


def normalize_email(email: str) -> str:
    return str(email or "").strip().lower()


class AuthIdentity(BaseModel):
    email: str
    display_name: str = ""
    avatar_url: str = ""
    subject: str = ""

    @field_validator("email")
    @classmethod
    def _normalize_email(cls, value: str) -> str:
        normalized = normalize_email(value)
        if not normalized:
            raise ValueError("email is required")
        return normalized


class AuthPolicy(BaseModel):
    version: int = 1
    allowed_emails: list[str] = Field(default_factory=list)
    message: str = "This desktop build is restricted to approved accounts."

    @field_validator("allowed_emails")
    @classmethod
    def _normalize_allowed_emails(cls, values: list[str]) -> list[str]:
        normalized = [normalize_email(value) for value in values if normalize_email(value)]
        return list(dict.fromkeys(normalized))

    def allows(self, email: str) -> bool:
        normalized = normalize_email(email)
        return normalized in set(self.allowed_emails)


class AuthSessionRecord(BaseModel):
    session_id: str
    identity: AuthIdentity
    issued_at: datetime
    expires_at: datetime
    last_validated_at: datetime

    @property
    def display(self) -> dict[str, str]:
        return {
            "email": self.identity.email,
            "display_name": self.identity.display_name,
            "avatar_url": self.identity.avatar_url,
        }


class BrowserAuthFlowRecord(BaseModel):
    flow_id: str
    state: str
    next_path: str
    created_at: datetime
    expires_at: datetime
    status: str = "pending"
    detail: str = ""
    session_id: str = ""
    user: dict[str, str] | None = None
