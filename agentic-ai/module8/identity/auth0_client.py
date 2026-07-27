from __future__ import annotations

import json
import hashlib
import time
from dataclasses import dataclass
from typing import Callable, Any

import jwt

from module8.config.models import Auth0Config
from module8.mock import auth0_mock


class Auth0Error(RuntimeError):
    """Raised when Auth0 live mode cannot complete the requested flow."""


@dataclass
class DeviceAuthorization:
    device_code: str
    user_code: str
    verification_uri: str
    verification_uri_complete: str
    expires_in: int
    interval: int


def _http_client(client: Any | None = None) -> Any:
    if client is not None:
        return client
    import httpx
    return httpx


def _raise_for_response(response: Any, context: str) -> None:
    if 200 <= response.status_code < 300:
        return
    try:
        payload = response.json()
    except Exception:
        payload = response.text
    raise Auth0Error(f"{context} failed: HTTP {response.status_code}: {payload}")


def fetch_openid_config(config: Auth0Config, http_client: Any | None = None) -> dict:
    config.validate_for_live()
    client = _http_client(http_client)
    response = client.get(config.discovery_url, timeout=10)
    _raise_for_response(response, "Auth0 OIDC discovery")
    discovery = response.json()
    if discovery.get("issuer") != config.issuer:
        raise Auth0Error(
            f"Auth0 issuer mismatch: expected {config.issuer}, got {discovery.get('issuer')}"
        )
    if not discovery.get("jwks_uri"):
        raise Auth0Error("Auth0 discovery document did not include jwks_uri")
    return discovery


def fetch_jwks(jwks_uri: str, http_client: Any | None = None) -> dict:
    client = _http_client(http_client)
    response = client.get(jwks_uri, timeout=10)
    _raise_for_response(response, "Auth0 JWKS retrieval")
    jwks = response.json()
    if not jwks.get("keys"):
        raise Auth0Error("Auth0 JWKS did not include signing keys")
    return jwks


def decode_access_token(
    token: str,
    config: Auth0Config,
    http_client: Any | None = None,
    discovery: dict | None = None,
    jwks: dict | None = None,
) -> dict:
    if config.mock_mode:
        return auth0_mock.decode_token(token)

    discovery = discovery or fetch_openid_config(config, http_client)
    jwks = jwks or fetch_jwks(discovery["jwks_uri"], http_client)

    header = jwt.get_unverified_header(token)
    kid = header.get("kid")
    key_data = None
    for candidate in jwks["keys"]:
        if candidate.get("kid") == kid:
            key_data = candidate
            break
    if key_data is None and len(jwks["keys"]) == 1:
        key_data = jwks["keys"][0]
    if key_data is None:
        raise Auth0Error(f"No Auth0 signing key matched token kid {kid}")

    public_key = jwt.algorithms.RSAAlgorithm.from_jwk(json.dumps(key_data))
    algorithm = key_data.get("alg") or header.get("alg") or "RS256"
    return jwt.decode(
        token,
        public_key,
        algorithms=[algorithm],
        audience=config.audience,
        issuer=config.issuer,
    )


def token_scopes(claims: dict) -> set[str]:
    """Return OAuth scopes from the JWT scope claim."""
    return set(str(claims.get("scope", "")).split())


def validate_user_token_claims(
    claims: dict,
    config: Auth0Config | None = None,
    now: int | None = None,
) -> dict:
    """Validate that decoded claims represent a user-delegated token."""
    subject = str(claims.get("sub", ""))
    grant_type = str(claims.get("gty", "")).replace("_", "-")
    if grant_type == "client-credentials":
        raise Auth0Error("Expected a user delegation token, got a client_credentials token")
    if not subject or subject.endswith("@clients"):
        raise Auth0Error("Expected a user subject, got an Auth0 application subject")

    if config is not None:
        if claims.get("iss") != config.issuer:
            raise Auth0Error(f"Token issuer does not match {config.issuer}")
        audiences = claims.get("aud", [])
        if isinstance(audiences, str):
            audiences = [audiences]
        if config.audience not in audiences:
            raise Auth0Error(f"Token audience does not include {config.audience}")
        expires_at = claims.get("exp")
        if not isinstance(expires_at, (int, float)) or expires_at <= (now or int(time.time())):
            raise Auth0Error("User delegation token has expired")
    return claims


def token_fingerprint(token: str) -> str:
    """Return a non-reversible identifier suitable for logs and audit records."""
    return f"sha256:{hashlib.sha256(token.encode('utf-8')).hexdigest()[:16]}"


def request_device_code(config: Auth0Config, http_client: Any | None = None) -> DeviceAuthorization:
    if config.mock_mode:
        return DeviceAuthorization(
            device_code="mock-device-code",
            user_code="MOCK-CODE",
            verification_uri="https://devops-companion.us.auth0.com/activate",
            verification_uri_complete="https://devops-companion.us.auth0.com/activate?user_code=MOCK-CODE",
            expires_in=300,
            interval=0,
        )

    config.validate_for_live()
    client = _http_client(http_client)
    response = client.post(
        config.device_code_url,
        data={
            "client_id": config.device_client_id,
            "audience": config.audience,
            "scope": " ".join(config.required_scopes),
        },
        timeout=10,
    )
    _raise_for_response(response, "Auth0 device authorization")
    payload = response.json()
    return DeviceAuthorization(
        device_code=payload["device_code"],
        user_code=payload["user_code"],
        verification_uri=payload["verification_uri"],
        verification_uri_complete=payload.get("verification_uri_complete", payload["verification_uri"]),
        expires_in=int(payload.get("expires_in", 300)),
        interval=int(payload.get("interval", 5)),
    )


def poll_device_token(
    config: Auth0Config,
    device_code: str,
    interval: int,
    timeout: int | None = None,
    http_client: Any | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> str:
    if config.mock_mode:
        return auth0_mock.issue_user_token(
            "auth0|6a4abce083be200f7de2e06f",
            config.required_scopes,
            issuer=config.issuer,
            audience=config.audience,
        )["access_token"]

    config.validate_for_live()
    client = _http_client(http_client)
    deadline = time.monotonic() + (timeout or config.device_poll_timeout)
    poll_interval = max(interval, 1)

    while time.monotonic() < deadline:
        response = client.post(
            config.token_url,
            data={
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                "device_code": device_code,
                "client_id": config.device_client_id,
            },
            timeout=10,
        )
        if 200 <= response.status_code < 300:
            payload = response.json()
            return payload["access_token"]

        payload = response.json()
        error = payload.get("error")
        if error == "authorization_pending":
            sleep(poll_interval)
            continue
        if error == "slow_down":
            poll_interval += 5
            sleep(poll_interval)
            continue
        if error == "access_denied":
            raise Auth0Error("Auth0 device authorization was denied by the user")
        if error == "expired_token":
            raise Auth0Error("Auth0 device authorization expired before login completed")
        _raise_for_response(response, "Auth0 device token polling")

    raise Auth0Error("Timed out waiting for Auth0 device authorization")
