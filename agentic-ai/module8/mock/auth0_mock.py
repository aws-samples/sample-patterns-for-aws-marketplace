from __future__ import annotations

import base64
import hashlib
import json


def issue_user_token(
    subject: str,
    scopes: list[str],
    email: str = "aisha.reed@example.com",
    issuer: str = "https://devops-companion.us.auth0.com/",
    audience: str = "https://api.devops-companion.internal",
) -> dict:
    """Mock Auth0 device-code user token issuance."""
    claims = {
        "iss": issuer,
        "sub": subject,
        "aud": audience,
        "scope": " ".join(scopes),
        "iat": 1_700_000_000,
        "exp": 4_000_000_000,
        "email": email,
        "gty": "device-code",
    }
    header = base64.urlsafe_b64encode(json.dumps({"alg": "RS256", "typ": "JWT"}).encode()).rstrip(b"=").decode()
    payload = base64.urlsafe_b64encode(json.dumps(claims).encode()).rstrip(b"=").decode()
    signature = hashlib.sha256(f"{header}.{payload}".encode("utf-8")).digest()
    sig = base64.urlsafe_b64encode(signature).rstrip(b"=").decode()
    token = f"{header}.{payload}.{sig}"
    return {
        "access_token": token,
        "token_type": "Bearer",
        "expires_in": 3600,
        "scope": " ".join(scopes),
    }


def decode_token(token: str) -> dict:
    """Decode a mock JWT token and return claims."""
    parts = token.split(".")
    if len(parts) != 3:
        return {}
    payload = parts[1]
    # Add padding
    payload += "=" * (4 - len(payload) % 4)
    return json.loads(base64.urlsafe_b64decode(payload))


def validate_scope(token: str, required_scope: str) -> bool:
    """Check if the token contains the required scope."""
    claims = decode_token(token)
    token_scopes = claims.get("scope", "").split()
    return required_scope in token_scopes
