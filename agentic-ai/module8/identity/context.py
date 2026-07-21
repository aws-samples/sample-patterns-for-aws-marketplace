from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class UserAuthorizationContext:
    """Validated user claims that are safe to pass into audit construction."""

    issuer: str
    subject: str
    email: str
    audience: str | tuple[str, ...]
    delegated_scopes: frozenset[str]
    token_fingerprint: str
    grant_type: str = "device-code"

    @classmethod
    def from_claims(
        cls,
        claims: dict[str, Any],
        delegated_scopes: set[str],
        token_fingerprint: str,
    ) -> UserAuthorizationContext:
        audience = claims.get("aud", "")
        if isinstance(audience, list):
            normalized_audience: str | tuple[str, ...] = tuple(str(item) for item in audience)
        else:
            normalized_audience = str(audience)

        return cls(
            issuer=str(claims.get("iss", "")),
            subject=str(claims["sub"]),
            email=str(claims.get("email") or claims["sub"]),
            audience=normalized_audience,
            delegated_scopes=frozenset(delegated_scopes),
            token_fingerprint=token_fingerprint,
            grant_type=str(claims.get("gty", "device-code")),
        )

    @property
    def user_identity_hash(self) -> str:
        digest = hashlib.sha256(self.subject.encode("utf-8")).hexdigest()[:12]
        return f"sha256:{digest}"

    def to_audit_record(self) -> dict[str, Any]:
        audience: str | list[str]
        if isinstance(self.audience, tuple):
            audience = list(self.audience)
        else:
            audience = self.audience
        return {
            "issuer": self.issuer,
            "subject": self.subject,
            "email": self.email,
            "audience": audience,
            "delegated_scopes": sorted(self.delegated_scopes),
            "grant_type": self.grant_type,
            "token_fingerprint": self.token_fingerprint,
            "user_identity_hash": self.user_identity_hash,
        }


def mock_user_authorization_context() -> UserAuthorizationContext:
    return UserAuthorizationContext(
        issuer="https://tenant.example.auth0.com/",
        subject="auth0|6a4abce083be200f7de2e06f",
        email="aisha.reed@example.com",
        audience="https://api.devops-companion.internal",
        delegated_scopes=frozenset(
            {"devops:analyze", "devops:iac", "devops:deploy:staging"}
        ),
        token_fingerprint="sha256:usr_7b4f2e91",
    )
