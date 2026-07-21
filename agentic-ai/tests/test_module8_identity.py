"""Focused behavior tests for Module 8 identity and credential boundaries."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["AGENT_MOCK_MODE"] = "true"


class FakeResponse:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text

    def json(self):
        return self._payload


class FakeHttp:
    def __init__(self, post_responses=None, get_responses=None):
        self.post_responses = list(post_responses or [])
        self.get_responses = list(get_responses or [])
        self.posts = []
        self.gets = []

    def post(self, url, **kwargs):
        self.posts.append((url, kwargs))
        return self.post_responses.pop(0)

    def get(self, url, **kwargs):
        self.gets.append((url, kwargs))
        return self.get_responses.pop(0)


def _live_auth0_config(monkeypatch):
    monkeypatch.setenv("AGENT_MOCK_MODE", "false")
    from module8.config.models import Auth0Config

    return Auth0Config(
        domain="tenant.us.auth0.com",
        audience="https://api.devops-companion.internal",
        device_client_id="device-client",
        required_scopes=[
            "devops:analyze",
            "devops:iac",
            "devops:deploy:staging",
        ],
    )


def _mock_delegation(monkeypatch, scopes=None):
    monkeypatch.setenv("AGENT_MOCK_MODE", "true")
    from module8.config.models import Auth0Config
    from module8.mock.auth0_mock import issue_user_token

    config = Auth0Config(
        domain="tenant.us.auth0.com",
        audience="https://api.devops-companion.internal",
        device_client_id="device-client",
        required_scopes=[
            "devops:analyze",
            "devops:iac",
            "devops:deploy:staging",
        ],
    )
    token = issue_user_token(
        "auth0|user",
        scopes or config.required_scopes,
        issuer=config.issuer,
        audience=config.audience,
    )["access_token"]
    return config, token


def test_mock_auth0_token_and_fingerprint_are_deterministic():
    from module8.identity.auth0_client import token_fingerprint
    from module8.mock.auth0_mock import issue_user_token

    first = issue_user_token("auth0|user", ["devops:analyze"])["access_token"]
    second = issue_user_token("auth0|user", ["devops:analyze"])["access_token"]

    assert first == second
    assert token_fingerprint(first) == token_fingerprint(second)


def test_live_config_rejects_placeholder_values(monkeypatch):
    monkeypatch.setenv("AGENT_MOCK_MODE", "false")
    from module8.config.models import Auth0Config

    with pytest.raises(ValueError) as exc:
        Auth0Config().validate_for_live()

    assert "AUTH0_DOMAIN" in str(exc.value)
    assert "AUTH0_DEVICE_CLIENT_ID" in str(exc.value)


def test_device_code_request_uses_native_application(monkeypatch):
    from module8.identity.auth0_client import request_device_code

    config = _live_auth0_config(monkeypatch)
    http = FakeHttp(
        post_responses=[
            FakeResponse(
                payload={
                    "device_code": "device-code",
                    "user_code": "USER-CODE",
                    "verification_uri": "https://tenant.us.auth0.com/activate",
                    "verification_uri_complete": (
                        "https://tenant.us.auth0.com/activate?user_code=USER-CODE"
                    ),
                    "expires_in": 300,
                    "interval": 1,
                }
            )
        ]
    )

    device = request_device_code(config, http)

    assert device.device_code == "device-code"
    url, kwargs = http.posts[0]
    assert url == "https://tenant.us.auth0.com/oauth/device/code"
    assert kwargs["data"] == {
        "client_id": "device-client",
        "audience": "https://api.devops-companion.internal",
        "scope": "devops:analyze devops:iac devops:deploy:staging",
    }


def test_device_code_poll_handles_pending_then_success(monkeypatch):
    from module8.identity.auth0_client import poll_device_token

    config = _live_auth0_config(monkeypatch)
    http = FakeHttp(
        post_responses=[
            FakeResponse(403, {"error": "authorization_pending"}),
            FakeResponse(200, {"access_token": "user-token"}),
        ]
    )

    token = poll_device_token(
        config,
        "device-code",
        interval=1,
        timeout=5,
        http_client=http,
        sleep=lambda _: None,
    )

    assert token == "user-token"
    assert len(http.posts) == 2


def test_device_code_poll_reports_user_denial(monkeypatch):
    from module8.identity.auth0_client import Auth0Error, poll_device_token

    config = _live_auth0_config(monkeypatch)
    http = FakeHttp(
        post_responses=[FakeResponse(403, {"error": "access_denied"})]
    )

    with pytest.raises(Auth0Error, match="denied"):
        poll_device_token(
            config,
            "device-code",
            interval=1,
            timeout=5,
            http_client=http,
            sleep=lambda _: None,
        )


def test_oidc_decode_uses_expected_issuer_and_audience(monkeypatch):
    from module8.identity import auth0_client

    config = _live_auth0_config(monkeypatch)
    discovery = {
        "issuer": config.issuer,
        "jwks_uri": "https://tenant.us.auth0.com/.well-known/jwks.json",
    }
    jwks = {"keys": [{"kid": "kid-1", "kty": "RSA", "alg": "RS256"}]}
    monkeypatch.setattr(
        auth0_client.jwt,
        "get_unverified_header",
        lambda _: {"kid": "kid-1", "alg": "RS256"},
    )
    monkeypatch.setattr(
        auth0_client.jwt.algorithms.RSAAlgorithm,
        "from_jwk",
        lambda _: "public-key",
    )
    captured = {}

    def fake_decode(token, key, algorithms, audience, issuer):
        captured.update(
            token=token,
            key=key,
            algorithms=algorithms,
            audience=audience,
            issuer=issuer,
        )
        return {"iss": issuer, "aud": audience, "sub": "auth0|user"}

    monkeypatch.setattr(auth0_client.jwt, "decode", fake_decode)

    claims = auth0_client.decode_access_token(
        "jwt-token",
        config,
        discovery=discovery,
        jwks=jwks,
    )

    assert claims["sub"] == "auth0|user"
    assert captured["audience"] == config.audience
    assert captured["issuer"] == config.issuer


def test_user_token_validator_rejects_application_subject():
    from module8.identity.auth0_client import Auth0Error, validate_user_token_claims

    with pytest.raises(Auth0Error, match="client_credentials"):
        validate_user_token_claims(
            {
                "sub": "orchestrator-client@clients",
                "gty": "client-credentials",
            }
        )


@pytest.mark.parametrize(
    ("claim_update", "message"),
    [
        ({"iss": "https://wrong.example/"}, "issuer"),
        ({"aud": "https://wrong.example/api"}, "audience"),
        ({"exp": 1}, "expired"),
    ],
)
def test_user_token_validator_rejects_invalid_security_claims(
    monkeypatch,
    claim_update,
    message,
):
    from module8.identity.auth0_client import Auth0Error, validate_user_token_claims

    config = _live_auth0_config(monkeypatch)
    claims = {
        "iss": config.issuer,
        "aud": config.audience,
        "sub": "auth0|user",
        "exp": 4_000_000_000,
    }
    claims.update(claim_update)

    with pytest.raises(Auth0Error, match=message):
        validate_user_token_claims(claims, config, now=2_000_000_000)


def test_same_user_context_reaches_each_agent(monkeypatch):
    from module8.identity.delegation import AGENT_POLICIES, authorize_agent_call

    config, token = _mock_delegation(monkeypatch)
    calls = (
        (AGENT_POLICIES[0], "coordinate_analysis", "devops:analyze"),
        (AGENT_POLICIES[1], "analyze_repository", "devops:analyze"),
        (AGENT_POLICIES[2], "generate_iac", "devops:iac"),
        (AGENT_POLICIES[3], "deploy_staging", "devops:deploy:staging"),
    )

    decisions = [
        authorize_agent_call(token, config, policy, operation, scope)
        for policy, operation, scope in calls
    ]

    assert {decision.subject for decision in decisions} == {"auth0|user"}
    assert len({decision.token_fingerprint for decision in decisions}) == 1
    assert len({decision.a2a_principal for decision in decisions}) == 4
    assert len({decision.iam_role_arn for decision in decisions}) == 4


def test_specialists_use_distinct_target_credentials():
    from module8.identity.delegation import AGENT_POLICIES

    analysis, iac, deploy = AGENT_POLICIES[1:]

    assert analysis.downstream_access != iac.downstream_access
    assert "GitHub App installation token" in analysis.downstream_access
    assert "GitHub App installation token" in iac.downstream_access
    assert "AWS account IAM role" in deploy.downstream_access


def test_agent_policy_cannot_expand_user_scopes(monkeypatch):
    from module8.identity.delegation import AGENT_POLICIES, authorize_agent_call

    config, token = _mock_delegation(monkeypatch)
    decision = authorize_agent_call(
        token,
        config,
        AGENT_POLICIES[1],
        "analyze_repository",
        "devops:analyze",
    )

    assert decision.effective_scopes == {"devops:analyze"}


def test_missing_user_scope_denies_production_deployment(monkeypatch):
    from module8.identity.auth0_client import Auth0Error
    from module8.identity.delegation import AGENT_POLICIES, authorize_agent_call

    config, token = _mock_delegation(monkeypatch)

    with pytest.raises(Auth0Error, match="did not delegate"):
        authorize_agent_call(
            token,
            config,
            AGENT_POLICIES[3],
            "deploy_production",
            "devops:deploy:production",
        )


def test_agent_permission_ceiling_denies_production_deployment(monkeypatch):
    from module8.identity.auth0_client import Auth0Error
    from module8.identity.delegation import AGENT_POLICIES, authorize_agent_call

    config, token = _mock_delegation(
        monkeypatch,
        [
            "devops:analyze",
            "devops:iac",
            "devops:deploy:staging",
            "devops:deploy:production",
        ],
    )

    with pytest.raises(Auth0Error, match="does not permit"):
        authorize_agent_call(
            token,
            config,
            AGENT_POLICIES[3],
            "deploy_production",
            "devops:deploy:production",
        )


def test_authorization_context_serializes_without_raw_token():
    from module8.identity.context import UserAuthorizationContext

    context = UserAuthorizationContext.from_claims(
        {
            "iss": "https://tenant.example.auth0.com/",
            "sub": "auth0|user",
            "email": "user@example.com",
            "aud": ["https://api.devops-companion.internal"],
            "gty": "device-code",
        },
        {"devops:analyze"},
        "sha256:fingerprint",
    )
    serialized = json.dumps(context.to_audit_record())

    assert context.email == "user@example.com"
    assert "access_token" not in serialized
    assert "refresh_token" not in serialized
    assert "raw_token" not in serialized


def test_identity_trace_is_compact_and_uses_one_correlation_key():
    from module8.audit.trail import generate_identity_trace
    from module8.identity.context import mock_user_authorization_context

    trace = generate_identity_trace(
        "wf-trace-test",
        mock_user_authorization_context(),
    )

    assert set(trace) == {
        "workflow_execution_id",
        "evidence_records",
        "representative_cloudtrail_event",
        "reverse_investigation",
    }
    assert len(trace["evidence_records"]) == 7
    assert {
        record["workflow_execution_id"]
        for record in trace["evidence_records"]
    } == {"wf-trace-test"}
    assert "deployment_run_id" not in json.dumps(trace)


def test_identity_trace_preserves_principals_and_policy_decisions():
    from module8.audit.trail import POLICY_VERSION, generate_identity_trace
    from module8.identity.context import mock_user_authorization_context

    trace = generate_identity_trace(
        "wf-principals",
        mock_user_authorization_context(),
    )
    records = trace["evidence_records"]
    analysis = next(record for record in records if record["trace_point"] == "Repository analysis")
    iac = next(record for record in records if record["trace_point"] == "Generated IaC")
    deploy = next(record for record in records if record["trace_point"] == "Deploy authorization")

    assert analysis["target_principal"] != iac["target_principal"]
    assert analysis["required_scope"] == "devops:analyze"
    assert iac["required_scope"] == "devops:iac"
    assert deploy["decision"] == "ALLOW"
    assert deploy["details"]["policy_version"] == POLICY_VERSION


def test_identity_trace_cloudtrail_uses_workflow_as_source_identity():
    from module8.audit.trail import generate_identity_trace
    from module8.identity.context import mock_user_authorization_context

    event = generate_identity_trace(
        "wf-cloudtrail",
        mock_user_authorization_context(),
    )["representative_cloudtrail_event"]

    assert event["eventName"] == "ExecuteChangeSet"
    assert (
        event["userIdentity"]["sessionContext"]["sourceIdentity"]
        == "wf-cloudtrail"
    )


def test_identity_trace_reverses_from_aws_to_user():
    from module8.audit.trail import generate_identity_trace
    from module8.identity.context import mock_user_authorization_context

    reverse = generate_identity_trace(
        "wf-reverse",
        mock_user_authorization_context(),
    )["reverse_investigation"]

    assert reverse[0]["trace_point"] == "CloudTrail deployment"
    assert reverse[-1]["trace_point"] == "Original delegation"


def test_identity_trace_rejects_missing_workflow_scope():
    from module8.audit.trail import generate_identity_trace
    from module8.identity.context import UserAuthorizationContext

    context = UserAuthorizationContext(
        issuer="https://tenant.example.auth0.com/",
        subject="auth0|limited",
        email="limited@example.com",
        audience="https://api.devops-companion.internal",
        delegated_scopes=frozenset({"devops:analyze"}),
        token_fingerprint="sha256:limited",
    )

    with pytest.raises(ValueError, match="devops:deploy:staging, devops:iac"):
        generate_identity_trace("wf-limited", context)


def test_identity_trace_contains_no_raw_credentials():
    from module8.audit.trail import generate_identity_trace
    from module8.identity.context import mock_user_authorization_context

    serialized = json.dumps(
        generate_identity_trace(
            "wf-sanitized",
            mock_user_authorization_context(),
        )
    ).lower()

    for forbidden in (
        "access_token",
        "refresh_token",
        "secret_access_key",
        "github_token",
        "private_key",
    ):
        assert forbidden not in serialized


def test_mock_identity_trace_is_deterministic():
    from module8.audit.trail import generate_identity_trace
    from module8.identity.context import mock_user_authorization_context

    context = mock_user_authorization_context()

    assert generate_identity_trace("wf-stable", context) == generate_identity_trace(
        "wf-stable",
        context,
    )


def test_full_demo_passes_sanitized_context_from_section_2_to_section_3(monkeypatch):
    from demos import module8_demo
    from module8.identity.context import mock_user_authorization_context

    context = mock_user_authorization_context()
    captured = []
    monkeypatch.setattr(
        module8_demo,
        "SECTIONS",
        {
            1: ("one", lambda: None),
            2: ("two", lambda: context),
            3: ("three", lambda value: captured.append(value)),
            4: ("four", lambda: None),
        },
    )

    module8_demo.run_all()

    assert captured == [context]
    assert "access_token" not in context.to_audit_record()


def test_full_demo_stops_when_user_authorization_fails(monkeypatch):
    from demos import module8_demo

    visited = []
    monkeypatch.setattr(
        module8_demo,
        "SECTIONS",
        {
            1: ("one", lambda: visited.append(1)),
            2: ("two", lambda: None),
            3: ("three", lambda value: visited.append(3)),
            4: ("four", lambda: visited.append(4)),
        },
    )

    module8_demo.run_all()

    assert visited == [1]


def test_section_four_is_credential_isolation():
    from demos import module8_demo

    title, function = module8_demo.SECTIONS[4]

    assert title == "Credential Isolation"
    assert function is module8_demo.section_4_credential_isolation


def _agent_guard_config(tmp_path, aws_profile=None):
    from module8.agent_guard_live import AgentGuardLiveConfig

    return AgentGuardLiveConfig(
        repo_root=tmp_path,
        aws_profile=aws_profile,
        aws_region="us-east-1",
        secret_id="devops-companion-github-token",
        secret_env_var="GITHUB_TOKEN",
        audit_log_file=tmp_path / "agent-guard-audit.log",
    )


def test_agent_guard_proxy_process_uses_secret_reference(tmp_path):
    from module8.agent_guard_live import build_proxy_process

    process = build_proxy_process(_agent_guard_config(tmp_path))

    assert process["command"].endswith("/agentic-ai/.venv/bin/agc")
    assert process["args"][:4] == ["mcp-proxy", "start", "--cap", "audit"]
    assert "aws://devops-companion-github-token/GITHUB_TOKEN" in process["args"]
    assert "module8.mcp.secret_probe_server" in process["args"]
    assert process["env"]["AWS_REGION"] == "us-east-1"
    assert "AWS_PROFILE" not in process["env"]


def test_agent_guard_proxy_process_propagates_explicit_profile(tmp_path):
    from module8.agent_guard_live import build_proxy_process

    process = build_proxy_process(_agent_guard_config(tmp_path, "demo-profile"))

    assert process["env"]["AWS_PROFILE"] == "demo-profile"


def test_agent_guard_audit_matches_only_new_request_and_response(tmp_path):
    from module8.agent_guard_live import read_audit_evidence

    audit_log = tmp_path / "agent-guard-audit.log"
    old_log = "Request to CallTool: request_id='old'\n"
    audit_log.write_text(
        old_log
        + "Request to CallTool: request_id='live-1'\n"
        + "Response from CallTool: request_id='live-1'\n",
        encoding="utf-8",
    )

    evidence = read_audit_evidence(
        audit_log,
        start_offset=len(old_log),
        request_id="live-1",
    )

    assert evidence.request_recorded is True
    assert evidence.response_recorded is True


def test_agent_guard_probe_refuses_parent_process_secret(tmp_path, monkeypatch):
    from module8.agent_guard_live import AgentGuardProbeError, probe_mcp

    monkeypatch.setenv("GITHUB_TOKEN", "already-in-parent")

    with pytest.raises(AgentGuardProbeError, match="only credential injection boundary"):
        probe_mcp(_agent_guard_config(tmp_path))


def test_agent_guard_probe_error_preserves_process_output():
    from module8.agent_guard_live import AgentGuardProbeError

    error = AgentGuardProbeError(
        "protected process failed",
        "secret retrieval failed",
    )

    assert str(error) == "protected process failed"
    assert error.captured_stderr == "secret retrieval failed"


def test_protected_tool_allows_operation_without_secret_metadata(monkeypatch):
    from module8.mcp.secret_probe_server import evaluate_guarded_action

    monkeypatch.setenv("GITHUB_TOKEN", "safe-demo-value")
    result = evaluate_guarded_action(
        "list_private_repositories",
        "request-1",
    )

    assert result["decision"] == "allowed"
    assert result["executed"] is True
    assert result["credential_state"] == {"present": True}
    assert result["result"]["count"] == 3
    assert "length" not in json.dumps(result)
    assert "fingerprint" not in json.dumps(result)
    assert "safe-demo-value" not in json.dumps(result)


def test_protected_tool_blocks_unlisted_operation(monkeypatch):
    from module8.mcp.secret_probe_server import evaluate_guarded_action

    monkeypatch.setenv("GITHUB_TOKEN", "safe-demo-value")
    result = evaluate_guarded_action("unlisted_action", "request-2")

    assert result["decision"] == "blocked"
    assert result["blocked"] is True
    assert result["executed"] is False
    assert "result" not in result


def test_agent_guard_boundary_requires_isolation_injection_and_audit():
    from module8.agent_guard_live import (
        AgentGuardAuditEvidence,
        AgentGuardBoundaryEvidence,
        boundary_evidence_failures,
    )

    evidence = AgentGuardBoundaryEvidence(
        agent_process_before_has_secret=False,
        agent_process_after_has_secret=False,
        secret_source="aws://secret/GITHUB_TOKEN",
        operation_result={
            "decision": "allowed",
            "blocked": False,
            "executed": True,
            "credential_present_in_protected_process": True,
        },
        operation_audit=AgentGuardAuditEvidence(True, True),
    )

    assert boundary_evidence_failures(evidence) == []


def test_mock_agent_guard_evidence_matches_live_shape():
    from module8.mock.cyberark_mock import generate_boundary_evidence

    evidence = generate_boundary_evidence()
    serialized = json.dumps(evidence)

    assert evidence["agent_process"] == {
        "credential_present_before": False,
        "credential_present_after": False,
    }
    assert evidence["operation"]["credential_present_in_protected_process"] is True
    assert evidence["operation_audit"] == {
        "request_recorded": True,
        "response_recorded": True,
    }
    assert "fingerprint" not in serialized
    assert "length" not in serialized


def test_aws_secret_check_does_not_report_secret_metadata(monkeypatch, tmp_path):
    from module8.agent_guard_live import aws_secret_check

    class FakeClient:
        def __init__(self, service):
            self.service = service

        def get_caller_identity(self):
            return {"Account": "123456789012"}

        def get_secret_value(self, SecretId):
            assert SecretId == "devops-companion-github-token"
            return {"SecretString": "raw-secret-value"}

    class FakeSession:
        def __init__(self, profile_name, region_name):
            assert profile_name is None
            assert region_name == "us-east-1"

        def client(self, service):
            return FakeClient(service)

    fake_boto3 = type("FakeBoto3", (), {"Session": FakeSession})
    monkeypatch.setitem(sys.modules, "boto3", fake_boto3)

    ok, detail = aws_secret_check(_agent_guard_config(tmp_path))

    assert ok is True
    assert "raw-secret-value" not in detail
    assert "length" not in detail
    assert "fingerprint" not in detail


def test_auth0_preflight_checks_device_flow_without_management_token(monkeypatch):
    from module8.live_check import run_checks

    config = _live_auth0_config(monkeypatch)
    http = FakeHttp(
        get_responses=[
            FakeResponse(
                payload={
                    "issuer": config.issuer,
                    "jwks_uri": "https://tenant.us.auth0.com/jwks",
                }
            ),
            FakeResponse(payload={"keys": [{"kid": "one"}]}),
        ],
        post_responses=[
            FakeResponse(
                payload={
                    "device_code": "device-code",
                    "user_code": "USER-CODE",
                    "verification_uri": "https://tenant.us.auth0.com/activate",
                    "expires_in": 300,
                    "interval": 1,
                }
            )
        ],
    )

    results = run_checks(config, http)

    assert all(result.ok for result in results)
    assert [result.name for result in results] == [
        "live configuration",
        "OIDC discovery",
        "JWKS",
        "device authorization",
        "Management API inspection",
    ]
