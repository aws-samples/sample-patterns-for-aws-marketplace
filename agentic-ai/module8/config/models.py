from __future__ import annotations

import os
from dataclasses import dataclass, field
from urllib.parse import urlparse


def _mock_mode() -> bool:
    return os.getenv("AGENT_MOCK_MODE", "true").lower() == "true"


def _split_scopes(value: str | None) -> list[str]:
    if not value:
        return ["devops:analyze", "devops:iac", "devops:deploy:staging"]
    normalized = value.replace(",", " ")
    return [scope.strip() for scope in normalized.split() if scope.strip()]


def _split_emails(value: str | None) -> list[str]:
    if not value:
        return []
    normalized = value.replace(",", " ")
    return [email.strip() for email in normalized.split() if email.strip()]


def _normalize_domain(domain: str) -> str:
    value = (domain or "").strip()
    if value.startswith("http://") or value.startswith("https://"):
        parsed = urlparse(value)
        value = parsed.netloc
    return value.strip("/")


@dataclass
class Auth0Config:
    domain: str = field(default_factory=lambda: os.getenv("AUTH0_DOMAIN", "devops-companion.us.auth0.com"))
    audience: str = field(default_factory=lambda: os.getenv("AUTH0_AUDIENCE", "https://api.devops-companion.internal"))
    device_client_id: str = field(default_factory=lambda: os.getenv("AUTH0_DEVICE_CLIENT_ID", "mock-device-client-id"))
    required_scopes: list[str] = field(default_factory=lambda: _split_scopes(os.getenv("AUTH0_REQUIRED_SCOPES")))
    demo_user_emails: list[str] = field(default_factory=lambda: _split_emails(os.getenv("AUTH0_DEMO_USER_EMAILS")))
    management_token: str = field(default_factory=lambda: os.getenv("AUTH0_MGMT_TOKEN", ""))
    device_poll_timeout: int = field(default_factory=lambda: int(os.getenv("AUTH0_DEVICE_POLL_TIMEOUT", "300")))

    def __post_init__(self) -> None:
        self.domain = _normalize_domain(self.domain)

    @property
    def mock_mode(self) -> bool:
        return _mock_mode()

    @property
    def issuer(self) -> str:
        return f"https://{self.domain}/"

    @property
    def token_url(self) -> str:
        return f"https://{self.domain}/oauth/token"

    @property
    def device_code_url(self) -> str:
        return f"https://{self.domain}/oauth/device/code"

    @property
    def discovery_url(self) -> str:
        return f"https://{self.domain}/.well-known/openid-configuration"

    @property
    def management_audience(self) -> str:
        return f"https://{self.domain}/api/v2/"

    @property
    def has_management_token(self) -> bool:
        return bool(self.management_token)

    def validate_for_live(self) -> None:
        if self.mock_mode:
            return

        errors = []
        placeholders = {"devops-companion.us.auth0.com", "your-tenant.us.auth0.com"}
        if not self.domain or self.domain in placeholders or "your-" in self.domain or "<" in self.domain:
            errors.append("AUTH0_DOMAIN must be your real Auth0 tenant domain")
        if "/" in self.domain or "." not in self.domain:
            errors.append("AUTH0_DOMAIN must be a domain like example.us.auth0.com, without a path")

        required = {
            "AUTH0_AUDIENCE": self.audience,
            "AUTH0_DEVICE_CLIENT_ID": self.device_client_id,
        }
        for name, value in required.items():
            if (
                not value
                or value.startswith("mock-")
                or "your-" in value
                or "<" in value
                or value.startswith("REPLACE_WITH_")
            ):
                errors.append(f"{name} must be set for live Auth0 mode")

        if not self.required_scopes:
            errors.append("AUTH0_REQUIRED_SCOPES must include at least one scope")

        if errors:
            details = "\n- ".join(errors)
            raise ValueError(f"Auth0 live configuration is incomplete:\n- {details}")
