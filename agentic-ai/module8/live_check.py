from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Any

from module8.config.env import load_agentic_env
from module8.config.models import Auth0Config
from module8.identity.auth0_client import (
    Auth0Error,
    fetch_jwks,
    fetch_openid_config,
    request_device_code,
)

AUTH0_DISPLAY_DOMAIN = "tenant.example.auth0.com"
AUTH0_DISPLAY_ISSUER = f"https://{AUTH0_DISPLAY_DOMAIN}/"


@dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str


def _http_client(client: Any | None = None) -> Any:
    if client is not None:
        return client
    import httpx
    return httpx


def _mgmt_get(config: Auth0Config, token: str, path: str, http_client: Any | None = None) -> Any:
    client = _http_client(http_client)
    response = client.get(
        f"https://{config.domain}/api/v2/{path.lstrip('/')}",
        headers={"Authorization": f"Bearer {token}"},
        timeout=10,
    )
    if not 200 <= response.status_code < 300:
        raise Auth0Error(f"Management API GET {path} failed: HTTP {response.status_code}: {response.text}")
    return response.json()


def run_checks(config: Auth0Config, http_client: Any | None = None) -> list[CheckResult]:
    results: list[CheckResult] = []

    try:
        config.validate_for_live()
        results.append(CheckResult("live configuration", True, f"tenant={AUTH0_DISPLAY_DOMAIN}"))
    except Exception as exc:
        results.append(CheckResult("live configuration", False, str(exc)))
        return results

    try:
        discovery = fetch_openid_config(config, http_client)
        results.append(CheckResult("OIDC discovery", True, f"issuer={AUTH0_DISPLAY_ISSUER}"))
    except Exception as exc:
        results.append(CheckResult("OIDC discovery", False, f"{exc}; fix AUTH0_DOMAIN"))
        return results

    try:
        jwks = fetch_jwks(discovery["jwks_uri"], http_client)
        results.append(CheckResult("JWKS", True, f"{len(jwks['keys'])} signing key(s) found"))
    except Exception as exc:
        results.append(CheckResult("JWKS", False, f"{exc}; check tenant signing keys"))

    try:
        device = request_device_code(config, http_client)
        results.append(CheckResult(
            "device authorization",
            True,
            f"device code issued for https://{AUTH0_DISPLAY_DOMAIN}/activate",
        ))
    except Exception as exc:
        results.append(CheckResult(
            "device authorization",
            False,
            f"{exc}; in Auth0, enable Device Authorization Flow for the native app",
        ))

    if not config.has_management_token:
        results.append(CheckResult(
            "Management API inspection",
            True,
            "skipped; set a short-lived AUTH0_MGMT_TOKEN for read-only API, client, and user checks",
        ))
        return results

    try:
        resource_servers = _mgmt_get(
            config,
            config.management_token,
            "resource-servers",
            http_client,
        )
        api = next((item for item in resource_servers if item.get("identifier") == config.audience), None)
        if not api:
            results.append(CheckResult(
                "API audience",
                False,
                "missing API; in Auth0 Dashboard, create an API whose Identifier equals AUTH0_AUDIENCE",
            ))
        else:
            api_scopes = {scope.get("value") for scope in api.get("scopes", [])}
            expected_scopes = set(config.required_scopes)
            missing = expected_scopes - api_scopes
            if missing:
                results.append(CheckResult(
                    "API scopes",
                    False,
                    f"missing {sorted(missing)}; add these permissions to the Auth0 API",
                ))
            else:
                results.append(CheckResult("API scopes", True, f"required scopes found on {config.audience}"))

        device_client = _mgmt_get(
            config,
            config.management_token,
            f"clients/{config.device_client_id}",
            http_client,
        )
        grant_types = set(device_client.get("grant_types", []))
        if "urn:ietf:params:oauth:grant-type:device_code" in grant_types:
            results.append(CheckResult("device app config", True, "device_code grant enabled"))
        else:
            results.append(CheckResult(
                "device app config",
                False,
                "device_code grant missing; enable Device Authorization Flow on the native app",
            ))

        for email in config.demo_user_emails:
            users = _mgmt_get(
                config,
                config.management_token,
                f"users-by-email?email={email}",
                http_client,
            )
            if users:
                results.append(CheckResult("demo user", True, f"{email} exists"))
            else:
                results.append(CheckResult(
                    "demo user",
                    False,
                    f"{email} not found; create the user in Auth0 Dashboard or adjust AUTH0_DEMO_USER_EMAILS",
                ))
    except Exception as exc:
        results.append(CheckResult(
            "Management API inspection",
            False,
            f"{exc}; use a current Management API token with read:clients read:resource_servers read:users",
        ))

    return results


def main() -> int:
    load_agentic_env()
    config = Auth0Config()
    results = run_checks(config)

    print(f"Module 8 Auth0 live check for {AUTH0_DISPLAY_DOMAIN}")
    failed = False
    for result in results:
        icon = "OK" if result.ok else "FAIL"
        print(f"[{icon}] {result.name}: {result.detail}")
        failed = failed or not result.ok

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
