from __future__ import annotations

import io
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from urllib.parse import parse_qs, urlsplit

from module12 import telemetry as telemetry_module
from demos import module12_demo as demo
from module12.cedar_policy import (
    MUTATION_TOOLS,
    READ_ONLY_TOOLS,
    build_cedar_policy,
    build_cedar_statements,
)
from module12.contracts import GovernanceContext
from module12.gateway_client import GatewayInvocationError
from module12.gateway_interceptor import GOVERNANCE_SOURCE, transform_request
from module12.honeycomb_local import LocalHoneycombDataset
from module12.posture import (
    RECORDED_SNYK_REPORT,
    build_finding_event_from_snyk_report,
    live_scan_plan,
    load_recorded_snyk_report,
    normalize_snyk_report,
    posture_from_detail,
)
from module12.posture_handler import _live_request, publish_finding
from module12.strands_intervention import (
    INTERVENTION_LAYER,
    INTERVENTION_NAME,
    run_strands_tool_call,
)
from module12.telemetry import (
    STRANDS_REDACTION_TOKENS,
    configure_strands_redaction,
    sanitize_attributes,
)
from module12.telemetry_queries import honeycomb_query_template_link
from module12.tools.handler import handler
from module12.workflow import InMemoryWorkflowStore, run_gateway_probe, run_workflow


def test_short_session_is_extended_for_agentcore() -> None:
    session_id = demo._session_id("module12-test")

    assert session_id.startswith("module12-test-")
    assert len(session_id) == demo.MIN_AGENTCORE_SESSION_LENGTH


def test_default_session_fits_presentation_json() -> None:
    session_id = demo._session_id()

    assert demo.MIN_AGENTCORE_SESSION_LENGTH <= len(session_id)
    assert len(session_id) <= demo.MAX_DEMO_SESSION_LENGTH


def test_intro_explains_the_demo_without_configuration_dump(capsys) -> None:
    context = demo.DemoContext(
        no_pause=True,
        session_id=demo._session_id("intro-test"),
        region="us-east-1",
    )

    demo.show_intro(context)

    output = capsys.readouterr().out
    normalized_output = " ".join(output.split())
    assert "Demo configuration" not in output
    assert "more than a single agent" in output
    assert "useful proposal is not the same as authority" in normalized_output
    assert "The scenario we will follow" in output
    assert "What the three sections demonstrate" in output
    assert "Framework and tool-boundary enforcement" in output
    assert "internal" in output
    assert "external enforcement boundaries" in normalized_output
    assert "Strands" not in output
    assert "AgentCore" not in output
    assert "Supply-chain containment and recovery" in output
    assert "preserve read-only work" in output
    assert "Observability and investigation" in output
    assert "BubbleUp" not in output
    assert "observed quarantine" in output
    assert "recovery window" in output
    assert "workflow trace" not in normalized_output
    assert "Snyk" not in output
    assert "Honeycomb" not in output


def test_section_1_runs_locally_without_pauses(capsys) -> None:
    assert demo.main(["--section", "1", "--no-pause", "--session", "test-one"]) == 0

    output = capsys.readouterr()
    assert "How a proposed mutation is evaluated" not in output.out
    assert "Control flow" not in output.out
    assert "Strands Agents SDK" in output.out
    assert "connects the model, tools, and lifecycle hooks" in output.out
    assert "Framework enforcement" in output.out
    assert "before_tool_call intervention evaluates workflow-owned state" in output.out
    assert "AgentCore Gateway" in output.out
    assert "fully managed, secure entry point" in output.out
    assert "integration, authentication, and routing" in output.out
    assert "Lambda function as an MCP-compatible Companion tool" in output.out
    assert "Gateway authorization policy" in output.out
    assert "View the deployed policy" in output.out
    assert "available from the deployed" in output.out
    assert "authorization policies in the AWS Management Console" in output.out
    assert "CLEAN REPOSITORY BASELINE" not in output.out
    assert output.out.count("Workflow path") == 2
    assert "ANALYSIS" in output.out
    assert "IAC" in output.out
    assert "DEPLOYMENT" in output.out
    assert "STRANDS GATE" in output.out
    assert "OUTCOME" in output.out
    assert "Repository inspection found no session taint" in output.out
    assert "Untrusted instructions were detected" in output.out
    assert "Tool: apply_infrastructure" in output.out
    assert "Rule: allow_environment_deployment" in output.out
    assert "Rule: deny_tainted_deployment" in output.out
    assert "the proposal alone granted no authority" in output.out
    assert "one GovernanceContext object" in output.out
    assert "injected it into Strands invocation_state" in output.out
    assert "Strands did not fetch or derive them" in output.out
    assert "five rows summarize six checks" in output.out
    assert "PASS  Session" in output.out
    assert "PASS  Posture" in output.out
    assert "PASS  Approvals" in output.out
    assert "PASS  Artifact" in output.out
    assert "PASS  Target" in output.out
    assert "computed: classifier ->" in output.out
    assert "fetched: posture store ->" in output.out
    assert "fetched: governance store ->" in output.out
    assert "computed + fetched review ->" in output.out
    assert "before_tool_call intervention read that injected context" in output.out
    assert "Decision: ALLOW / allow_environment_deployment" in output.out
    assert "advanced the proposed tool call to AgentCore Gateway" in output.out
    assert "Gateway must independently authorize it" in output.out
    assert "The local simulation evaluated the five governance checks" in output.out
    assert "local governance state" in output.out
    assert "How the local Gateway policy simulation reached ALLOW" in output.out
    assert output.out.count("PASS  Session") == 2
    assert output.out.count("PASS  Posture") == 2
    assert output.out.count("PASS  Approvals") == 2
    assert output.out.count("PASS  Artifact") == 2
    assert output.out.count("PASS  Target") == 2
    assert "A live Gateway also checks the Runtime principal" in output.out
    assert "Decision: ALLOW — the local governance checks passed" in output.out
    assert "Implemented Cedar permit — apply_infrastructure" not in output.out
    assert "Data supplied to this Cedar evaluation" not in output.out
    assert "infrastructure changed" not in output.out.casefold()
    assert "Expressed in Cedar" in output.out
    assert "Request path in this demo" not in output.out
    assert "deterministic policy language" in output.out
    assert "Local AgentCore Gateway policy simulation is ready." in output.out
    assert "Snyk" not in output.out
    assert "Honeycomb" not in output.out
    assert "BubbleUp" not in output.out
    assert "baseline configuration" not in output.out.casefold()
    assert "SECTION 1 — ESTABLISH CLEAN BASELINE" not in output.out
    assert "Publishing the remediated deployment tool" not in output.out
    assert "Waiting for trusted posture to become healthy" not in output.out
    assert "Running the DevOps Companion workflow against the poisoned" in output.out
    assert "Sending the tainted deployment request" in output.out
    assert "LOCAL SIMULATION — Running the DevOps Companion workflow" in output.out
    assert "LOCAL RESULT — The local workflow completed with Strands decision" in output.out
    assert output.out.count("LOCAL SIMULATION —") == output.out.count(
        "LOCAL RESULT —"
    )
    assert output.out.count("LOCAL SETUP —") == output.out.count(
        "LOCAL SETUP COMPLETE —"
    )
    assert "apply_infrastructure returned ALLOW" in output.out
    assert "fresh apply_infrastructure probe matched" not in output.out
    assert "Local AgentCore Gateway policy simulation: DENY" in output.out
    assert "Why the path stopped" not in output.out
    assert "Why the model could not override the decision" in output.out
    assert "Section 1 summary" in output.out
    probe_index = output.out.index(
        "Evaluating a fresh apply_infrastructure probe"
    )
    allow_index = output.out.index(
        "apply_infrastructure returned ALLOW"
    )
    explanation_index = output.out.index(
        "How the local Gateway policy simulation reached ALLOW"
    )
    assert probe_index < allow_index < explanation_index
    layers_index = output.out.index("Strands Agents SDK")
    expected_path_index = output.out.index("SECTION 1 — EXPECTED REQUEST PATH")
    assert layers_index < expected_path_index
    poisoned_start_index = output.out.index(
        "Running the DevOps Companion workflow against the poisoned repository"
    )
    poisoned_result_index = output.out.index(
        "The local workflow completed with Strands decision DENY; no deployment was recorded"
    )
    poisoned_explanation_index = output.out.index(
        "Workflow path",
        poisoned_result_index,
    )
    assert (
        poisoned_start_index
        < poisoned_result_index
        < poisoned_explanation_index
    )
    assert output.err == ""


def test_gateway_policy_validation_exposes_live_readiness(
    monkeypatch, capsys
) -> None:
    monkeypatch.setattr(demo, "RICH", False)
    evidence = {
        "gateway_status": "READY",
        "policy_count": 8,
        "policy_status": "ACTIVE",
        "policy_enforcement": "ENFORCE",
        "protocol_version": "2025-06-18",
        "statement": "permit(principal, action, resource);",
    }
    context = SimpleNamespace(
        cloud=True,
        gateway_policy_evidence=lambda: evidence,
    )

    assert demo.validate_gateway_policy_evidence(context) == evidence

    output = capsys.readouterr().out
    assert "Validating the deployed AgentCore Gateway authorization policies" in output
    assert "Gateway READY" in output
    assert "8 authorization policies ACTIVE" in output
    assert "ENFORCE" in output
    assert "MCP 2025-06-18" in output


def test_cloud_gateway_explanation_follows_the_completed_live_probe(capsys) -> None:
    outcome = run_workflow("normal").to_dict()

    demo.show_gateway_policy_evaluation(
        outcome=outcome,
        target_name=demo.TOOL_TARGET_NAME,
        cloud=True,
    )

    output = capsys.readouterr().out
    assert "How AgentCore Gateway reached ALLOW" in output
    assert "signed Gateway probe completed after Strands returned Proceed" in output
    assert "AgentCore Gateway then evaluated these governance checks" in output
    assert "authorization policy, which is expressed in Cedar" in output
    assert "interceptor: posture store" in output
    assert "PASS  Principal" in output
    assert "PASS  Action" in output
    assert "PASS  Resource" in output
    assert "Decision: ALLOW" in output
    assert "reloaded externally governed values from DynamoDB" not in output


def test_strands_intervention_proceeds_and_executes_the_tool() -> None:
    calls: list[dict] = []
    context = GovernanceContext(
        artifact_digest="sha256:reviewed",
        reviewed_artifact_digest="sha256:reviewed",
    )

    decision = run_strands_tool_call(
        context=context,
        proposal={
            "requested_tool": "apply_infrastructure",
            "proposal_summary": "Apply reviewed staging infrastructure.",
        },
        execute_tool=lambda arguments: (
            calls.append(dict(arguments))
            or {
                "status": "simulated",
                "simulated_mutation": True,
                "infrastructure_changed": False,
            }
        ),
    )

    assert decision.policy.decision == "ALLOW"
    assert decision.policy.rule == "allow_environment_deployment"
    assert decision.intervention_action == "proceed"
    assert decision.tool_executed is True
    assert calls == [
        {"proposal_summary": "Apply reviewed staging infrastructure."}
    ]


def test_strands_intervention_denies_quarantine_before_tool_execution() -> None:
    calls: list[dict] = []
    context = GovernanceContext(
        snyk_posture="quarantine",
        artifact_digest="sha256:reviewed",
        reviewed_artifact_digest="sha256:reviewed",
    )

    decision = run_strands_tool_call(
        context=context,
        proposal={"requested_tool": "apply_infrastructure"},
        execute_tool=lambda arguments: calls.append(dict(arguments)) or {},
    )

    assert decision.policy.decision == "DENY"
    assert decision.policy.rule == "deny_quarantined_posture"
    assert decision.intervention_action == "deny"
    assert decision.tool_executed is False
    assert calls == []


def test_strands_intervention_denies_an_unexpected_deployment_tool() -> None:
    calls: list[dict] = []
    context = GovernanceContext(
        artifact_digest="sha256:reviewed",
        reviewed_artifact_digest="sha256:reviewed",
    )

    decision = run_strands_tool_call(
        context=context,
        proposal={"requested_tool": "rollback_infrastructure"},
        execute_tool=lambda arguments: calls.append(dict(arguments)) or {},
    )

    assert decision.policy.decision == "DENY"
    assert decision.policy.rule == "deny_unexpected_deployment_tool"
    assert decision.policy.tool == "rollback_infrastructure"
    assert decision.tool_executed is False
    assert calls == []


def test_one_runtime_request_runs_three_agents_and_routes_mutation_to_gateway() -> None:
    class FakeAgentSession:
        def __init__(self) -> None:
            self.calls: list[tuple[str, str]] = []

        def invoke(self, role: str, *, scenario: str) -> dict:
            self.calls.append((role, scenario))
            return {
                "role": role,
                "model_id": f"test.{role.casefold()}",
                "reply": f"{role} mock ready.",
                "stop_reason": "end_turn",
                "usage": {
                    "input_tokens": 10,
                    "output_tokens": 4,
                    "total_tokens": 14,
                },
            }

    class FakeGatewayInvoker:
        def __init__(self) -> None:
            self.calls: list[tuple[str, dict]] = []

        def invoke(
            self,
            tool: str,
            *,
            workflow_id: str,
            trusted_context: dict,
        ) -> dict:
            self.calls.append((tool, workflow_id, dict(trusted_context)))
            return {
                "tool": tool,
                "status": "simulated",
                "mutation": True,
                "simulated_mutation": True,
                "infrastructure_changed": False,
                "_gateway": {
                    "source": "agentcore_gateway_authorization",
                    "gateway_id": "gateway-test",
                    "target_name": "companion-tools",
                    "tool_action": "companion-tools___apply_infrastructure",
                    "status_code": 200,
                    "request_id": "request-test",
                },
            }

    agents = FakeAgentSession()
    gateway = FakeGatewayInvoker()
    outcome = run_workflow(
        "normal",
        session_id="module12-test-runtime-session-0000000000001",
        agent_session=agents,
        gateway_invoker=gateway,
    ).to_dict()

    assert agents.calls == [
        ("Analysis", "normal"),
        ("IaC", "normal"),
        ("Deployment", "normal"),
    ]
    assert [call[0] for call in gateway.calls] == ["apply_infrastructure"]
    assert gateway.calls[0][1] == outcome["workflow_id"]
    assert outcome["status"] == "completed"
    assert outcome["mutation_recorded"] is True
    execution = outcome["response"]["agent_execution"]
    assert execution["mode"] == "bedrock_agentcore_runtime"
    assert execution["handoff_mode"] == "independent_steps_in_one_runtime_request"
    assert [agent["role"] for agent in execution["agents"]] == [
        "Analysis",
        "IaC",
        "Deployment",
    ]
    assert outcome["response"]["gateway_invocations"][0]["source"] == (
        "agentcore_gateway_authorization"
    )
    spans = {span["name"]: span for span in outcome["spans"]}
    assert spans["agent.analysis"]["attributes"]["agent.model.id"] == (
        "test.analysis"
    )
    assert spans["agent.analysis"]["attributes"]["agent.input_tokens"] == 10
    assert spans["agent.analysis"]["attributes"]["agent.output_tokens"] == 4
    assert spans["agent.analysis"]["attributes"]["agent.total_tokens"] == 14
    assert "reply" not in spans["agent.analysis"]["attributes"]
    assert all(span["trace_id"] for span in outcome["spans"])
    assert all(span["span_id"] for span in outcome["spans"])


def test_honeycomb_allowlist_keeps_usage_but_excludes_agent_content() -> None:
    attributes = sanitize_attributes(
        {
            "agent.model.id": "us.openai.gpt-5.6-luna",
            "agent.input_tokens": 18,
            "agent.output_tokens": 6,
            "agent.total_tokens": 24,
            "agent.reply": "must not be exported",
            "gen_ai.input.messages": "must not be exported",
            "tool.arguments": {"must": "not be exported"},
        }
    )

    assert attributes == {
        "content.exported": False,
        "agent.model.id": "us.openai.gpt-5.6-luna",
        "agent.input_tokens": 18,
        "agent.output_tokens": 6,
        "agent.total_tokens": 24,
    }


def test_strands_otel_configuration_redacts_all_sensitive_content(
    monkeypatch,
) -> None:
    monkeypatch.delenv("OTEL_SEMCONV_STABILITY_OPT_IN", raising=False)

    configured = configure_strands_redaction()

    assert all(token in configured.split(",") for token in STRANDS_REDACTION_TOKENS)
    assert "gen_ai_unredacted_attributes=" in configured.split(",")


def test_honeycomb_exporter_uses_complete_ingest_key(
    monkeypatch,
) -> None:
    captured: dict[str, Any] = {}

    class FakeExporter:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    import opentelemetry.exporter.otlp.proto.http.trace_exporter as exporter_module

    monkeypatch.setattr(exporter_module, "OTLPSpanExporter", FakeExporter)
    monkeypatch.setattr(
        telemetry_module,
        "load_honeycomb_config",
        lambda: {
            "endpoint": "https://api.honeycomb.io/v1/traces",
            "ingest_key": "not-a-real-key",
            "service_name": "module12-security-observability",
        },
    )

    exporter = telemetry_module.create_honeycomb_exporter()

    assert isinstance(exporter, FakeExporter)
    assert captured["endpoint"] == "https://api.honeycomb.io/v1/traces"
    assert captured["headers"] == {"x-honeycomb-team": "not-a-real-key"}
    assert captured["timeout"] == 10


def test_honeycomb_config_reads_raw_ingest_key(monkeypatch) -> None:
    import boto3

    class FakeSecretsManager:
        def get_secret_value(self, **kwargs):
            assert kwargs == {"SecretId": "arn:aws:secretsmanager:test"}
            return {"SecretString": "unit-test-ingest-key"}

    monkeypatch.setenv(
        "MODULE12_HONEYCOMB_SECRET_ARN",
        "arn:aws:secretsmanager:test",
    )
    monkeypatch.setenv(
        "MODULE12_HONEYCOMB_OTLP_ENDPOINT",
        "https://api.honeycomb.io/v1/traces",
    )
    monkeypatch.setattr(boto3, "client", lambda *args, **kwargs: FakeSecretsManager())
    telemetry_module.load_honeycomb_config.cache_clear()

    config = telemetry_module.load_honeycomb_config()

    assert config == {
        "endpoint": "https://api.honeycomb.io/v1/traces",
        "ingest_key": "unit-test-ingest-key",
        "service_name": "module12-security-observability",
    }
    telemetry_module.load_honeycomb_config.cache_clear()


def test_section_2_runs_locally_without_pauses(capsys) -> None:
    assert demo.main(["--section", "2", "--no-pause", "--session", "test-two"]) == 0

    output = capsys.readouterr()
    assert "deny_quarantined_posture" in output.out
    assert "allow_read_only" in output.out
    assert "The agentic risk Snyk helps us see" in output.out
    assert "Agents load skills, call tools exposed through MCP" in output.out
    assert "reuse third-party packages" in output.out
    assert "Snyk Open Source scan" in output.out
    assert "tool—not a workflow execution" in output.out
    assert "Quarantine threshold" in output.out
    assert "The control path" not in output.out
    assert "What the live demonstration will prove" not in output.out
    assert "Cedar enforcement policy" not in output.out
    assert "Cedar" not in output.out
    assert "Honeycomb" not in output.out
    assert "BubbleUp" not in output.out
    assert "lodash@4.17.15" in output.out
    assert "SNYK-JS-LODASH-15869625" in output.out
    assert "5 high / 3 medium" in output.out
    assert "lodash@4.18.1" in output.out
    assert "never installed or executed" in output.out
    assert "What Snyk reported" in output.out
    assert "observed during a particular workflow execution" in output.out
    assert "REVIEW THE SNYK PROJECT" in output.out
    assert "DevOps Companion Tool Supply Chain" in output.out
    assert "Target reference: module12-demo" in output.out
    assert "durable Snyk record" in output.out
    assert "tracking remediation" in output.out
    assert "comparing future scans" in output.out
    assert "Snyk is the finding system of record" in output.out
    assert "not a record or trace of an execution" in output.out
    assert "Starting the supply-chain scan" in output.out
    assert "Running the DevOps Companion workflow with quarantine active" in output.out
    assert "Sending the read_repository probe" in output.out
    assert "read_repository returned ALLOW" in output.out
    assert "Sending the apply_infrastructure probe" in output.out
    assert "apply_infrastructure returned DENY" in output.out
    assert "Publishing the remediated deployment tool" in output.out
    assert "Running the DevOps Companion workflow with the recovered posture" in output.out
    assert (
        "Evaluating the recovered request with the local AgentCore Gateway"
        in output.out
    )
    assert "LOCAL SIMULATION" in output.out
    assert "LOCAL RESULT" in output.out
    assert output.out.count("LOCAL SIMULATION —") == output.out.count(
        "LOCAL RESULT —"
    )
    assert "What Gateway enforced" in output.out
    assert output.out.count("Workflow path") == 2
    assert "Repository inspection found no session taint" in output.out
    assert "Rule: deny_quarantined_posture" in output.out
    assert "Trusted signal: supply_chain_posture = quarantine" in output.out
    assert "Rule: allow_environment_deployment" in output.out
    assert "No deployment invocation was recorded" in output.out
    assert "The authorized tool invocation completed" in output.out
    normalized_output = " ".join(output.out.split())
    assert "protect the integrity of an agentic workflow" in normalized_output
    assert "AgentCore Gateway enforces" in normalized_output
    assert "restoring authority after reviewed" in output.out
    assert output.err == ""


def test_show_code_renders_copyable_json_without_panel_borders(capsys) -> None:
    demo.show_code(
        "Paste-ready Honeycomb Query JSON",
        '{"calculations": [{"op": "COUNT"}]}',
    )

    output = capsys.readouterr().out
    assert "Paste-ready Honeycomb Query JSON" in output
    json_line = next(line for line in output.splitlines() if "calculations" in line)
    assert "│" not in json_line
    assert "┃" not in json_line


def test_compact_json_wraps_at_valid_json_boundaries() -> None:
    value = {
        "calculations": [{"op": "COUNT"}],
        "filters": [
            {
                "column": "name",
                "op": "=",
                "value": "policy.authorize",
            }
        ],
        "time_range": 7200,
    }

    rendered = demo.compact_json(value, width=48)

    assert "\n" in rendered
    assert json.loads(rendered) == value
    assert all(line.endswith(",") for line in rendered.splitlines()[:-1])


def test_all_honeycomb_query_json_is_valid_and_fits_the_demo_terminal() -> None:
    session_id = demo._session_id()
    queries = (
        demo.HONEYCOMB_POLICY_POPULATION_QUERY,
        demo._honeycomb_quarantine_window_query(session_id),
    )

    for query in queries:
        rendered = demo.compact_json(query)
        assert json.loads(rendered) == query
        assert max(len(line) for line in rendered.splitlines()) <= (
            demo.HONEYCOMB_QUERY_WIDTH
        )


def test_honeycomb_query_template_link_prefills_the_query() -> None:
    query = {"calculations": [{"op": "COUNT"}], "time_range": 7200}

    link = honeycomb_query_template_link(
        dataset="module12-security-observability",
        query=query,
        base_url=(
            "https://ui.honeycomb.io/agentic-systems/environments/test/"
            "send-data/experience-picker"
        ),
    )

    assert link is not None
    parsed = urlsplit(link)
    assert parsed.path == (
        "/agentic-systems/environments/test/datasets/"
        "module12-security-observability/"
    )
    assert json.loads(parse_qs(parsed.query)["query"][0]) == query


def test_honeycomb_quarantine_window_uses_existing_exported_observations() -> None:
    def outcome(
        workflow_id: str,
        *,
        posture: str,
        decision: str,
    ) -> dict[str, Any]:
        return {
            "workflow_id": workflow_id,
            "session_id": "session-quarantine-window",
            "scenario": "normal",
            "mutation_recorded": False,
            "response": {
                "snyk_posture": posture,
                "policy": {
                    "decision": decision,
                    "rule": (
                        "deny_quarantined_posture"
                        if decision == "DENY"
                        else "allow_environment_deployment"
                    ),
                    "context": {"session_tainted": False},
                },
                "telemetry": {
                    "honeycomb_export_enabled": True,
                },
            },
        }

    session_id = demo._quarantine_window_session(
        [
            outcome(
                "workflow-quarantined",
                posture="quarantine",
                decision="DENY",
            ),
            outcome(
                "workflow-recovered",
                posture="healthy",
                decision="ALLOW",
            ),
        ]
    )
    query = demo._honeycomb_quarantine_window_query(str(session_id))

    assert session_id == "session-quarantine-window"
    assert query["calculated_fields"] == [
        {
            "name": "event_epoch",
            "expression": "EVENT_TIMESTAMP()",
        }
    ]
    assert query["formulas"] == [
        {
            "name": "observed_quarantine_seconds",
            "expression": "$recovery_seen - $quarantine_seen",
        }
    ]
    rendered_query = json.dumps(query)
    assert "snyk" not in rendered_query.casefold()


def test_section_1_resets_quarantine_before_clean_baseline(capsys) -> None:
    context = demo.DemoContext(
        no_pause=True,
        session_id=demo._session_id("stale-quarantine"),
        region="us-east-1",
    )
    context._local_posture["snyk_posture"] = "quarantine"

    demo.section_1(context)

    output = capsys.readouterr()
    assert context._local_posture["snyk_posture"] == "healthy"
    assert "baseline configuration" not in output.out.casefold()
    assert "reviewed tool digest" not in output.out.casefold()
    assert "trusted posture to become healthy" not in output.out.casefold()
    assert "allow_environment_deployment" in output.out


def test_recorded_snyk_report_drives_quarantine_and_policy_denial() -> None:
    report = load_recorded_snyk_report()
    finding = normalize_snyk_report(report)
    event = build_finding_event_from_snyk_report(
        report,
        tool_digest="sha256:observed",
        reviewed_tool_digest="sha256:reviewed",
    )
    transition = posture_from_detail(event["posture"])

    assert finding["package_name"] == "lodash"
    assert finding["package_version"] == "4.17.15"
    assert finding["finding_id"] == "SNYK-JS-LODASH-15869625"
    assert finding["title"] == "Arbitrary Code Injection"
    assert finding["issue_count"] == 8
    assert finding["severity_counts"] == {"high": 5, "medium": 3}
    assert finding["recommended_upgrade"] == "4.18.1"
    assert finding["quarantine_required"] is True
    assert transition.posture == "quarantine"
    assert transition.reason == "high_or_critical_snyk_finding"

    outcome = run_workflow(
        "normal",
        store=InMemoryWorkflowStore(
            {transition.posture_field: transition.posture}
        ),
    ).to_dict()
    assert outcome["status"] == "denied"
    assert outcome["response"]["policy"]["rule"] == "deny_quarantined_posture"
    assert outcome["mutation_recorded"] is False


def test_local_publisher_updates_the_posture_consumed_by_workflow() -> None:
    context = demo.DemoContext(
        no_pause=True,
        session_id=demo._session_id("snyk-posture-test"),
        region="us-east-1",
    )

    published = context.publish_posture(
        action="publish_finding",
        tool_digest=demo.CHANGED_TOOL_DIGEST,
        reviewed_tool_digest=demo.REVIEWED_TOOL_DIGEST,
    )
    observed = context.wait_for_posture("quarantine")
    quarantined = context.invoke("normal")

    assert published["finding"]["package"] == "lodash"
    assert observed["source"] == "in_memory_posture_controller"
    assert quarantined["response"]["snyk_posture"] == "quarantine"
    assert quarantined["response"]["policy"]["rule"] == "deny_quarantined_posture"

    context.publish_posture(
        action="recover_digest",
        tool_digest=demo.REVIEWED_TOOL_DIGEST,
        reviewed_tool_digest=demo.REVIEWED_TOOL_DIGEST,
    )
    context.wait_for_posture("healthy")
    recovered = context.invoke("normal")
    assert recovered["response"]["snyk_posture"] == "healthy"
    assert recovered["response"]["policy"]["decision"] == "ALLOW"


def test_clean_snyk_report_does_not_require_quarantine(tmp_path) -> None:
    report = {
        "ok": True,
        "projectName": "module12-companion-tools",
        "packageManager": "npm",
        "targetFile": "package-lock.json",
        "dependencyCount": 1,
        "vulnerabilities": [],
    }
    report_path = tmp_path / "snyk-clean.json"
    report_path.write_text(json.dumps(report))

    finding = normalize_snyk_report(report)
    request = _live_request(str(report_path))

    assert finding["severity"] == "none"
    assert finding["quarantine_required"] is False
    assert request["action"] == "recover_digest"


def test_snyk_publisher_persists_evidence_and_emits_quarantine(
    monkeypatch,
) -> None:
    class FakeS3:
        def __init__(self) -> None:
            self.objects: list[dict] = []

        def put_object(self, **request) -> None:
            self.objects.append(request)

    class FakeEvents:
        def __init__(self) -> None:
            self.entries: list[dict] = []

        def put_events(self, *, Entries):
            self.entries.extend(Entries)
            return {"Entries": [{"EventId": "event-123"}]}

    monkeypatch.setenv("MODULE12_EVIDENCE_BUCKET", "module12-evidence")
    monkeypatch.setenv("MODULE12_POSTURE_EVENT_BUS", "module12-posture")
    s3 = FakeS3()
    events = FakeEvents()

    result = publish_finding(
        _live_request(str(RECORDED_SNYK_REPORT)),
        s3_client=s3,
        events_client=events,
    )
    emitted = json.loads(events.entries[0]["Detail"])

    assert len(s3.objects) == 2
    assert all(
        request["ServerSideEncryption"] == "AES256"
        for request in s3.objects
    )
    assert events.entries[0]["Source"] == "module12.snyk"
    assert events.entries[0]["DetailType"] == "SnykFinding"
    assert emitted["posture"] == "quarantine"
    assert emitted["finding_id"] == "SNYK-JS-LODASH-15869625"
    assert result["event_id"] == "event-123"


def test_live_snyk_plan_publishes_reports_when_findings_exist() -> None:
    plan = live_scan_plan()
    buildspec = plan["buildspec"]

    assert plan["enabled_by_default"] is True
    assert plan["snyk_cli_version"] == "1.1308.3"
    assert "npm install --global snyk@1.1308.3" in buildspec
    assert "--json-file-output=/tmp/snyk.json" in buildspec
    assert '|| [ "$?" -eq 1 ]' in buildspec
    assert "snyk monitor" in buildspec
    assert (
        '--project-name="DevOps Companion Tool Supply Chain"'
        in buildspec
    )
    assert "--target-reference=module12-demo" in buildspec
    assert plan["monitor_project_name"] == "DevOps Companion Tool Supply Chain"
    assert plan["monitor_target_reference"] == "module12-demo"
    assert (
        "python3 -m module12.posture_handler --action publish-live"
        in buildspec
    )


def test_cloud_publisher_runs_codebuild_and_reads_live_evidence(
    monkeypatch,
) -> None:
    event = build_finding_event_from_snyk_report(
        load_recorded_snyk_report(),
        tool_digest=demo.CHANGED_TOOL_DIGEST,
        reviewed_tool_digest=demo.REVIEWED_TOOL_DIGEST,
    )
    scan_digest = event["posture"]["scan_digest"]
    finding_id = event["finding"]["finding_id"]
    evidence = json.dumps(event).encode("utf-8")

    class FakeCodeBuild:
        def __init__(self) -> None:
            self.started: list[dict] = []

        def start_build(self, **request):
            self.started.append(request)
            return {"build": {"id": "m12-scan:build-123"}}

        def batch_get_builds(self, *, ids):
            assert ids == ["m12-scan:build-123"]
            return {
                "builds": [
                    {
                        "id": ids[0],
                        "buildStatus": "SUCCEEDED",
                        "logs": {"deepLink": "https://console.example/build-123"},
                    }
                ]
            }

    class FakeS3:
        def __init__(self) -> None:
            self.requests: list[dict] = []

        def get_object(self, **request):
            self.requests.append(request)
            return {"Body": io.BytesIO(evidence)}

    codebuild = FakeCodeBuild()
    s3 = FakeS3()

    class FakeSession:
        def client(self, service_name, region_name=None):
            assert region_name == "us-east-1"
            return {"codebuild": codebuild, "s3": s3}[service_name]

    context = demo.DemoContext(
        no_pause=True,
        session_id=demo._session_id("live-snyk-test"),
        region="us-east-1",
        stack="module12-demo",
        outputs={
            "snykScanBuildProjectName": "m12-module12-demo-snyk-scan",
            "evidenceBucketName": "m12-evidence",
        },
    )
    context._aws_session = FakeSession()
    monkeypatch.setattr(
        context,
        "wait_for_posture",
        lambda expected, timeout=30.0: {
            "posture": expected,
            "findingId": finding_id,
            "scanDigest": scan_digest,
        },
    )

    published = context.publish_posture(
        action="publish_finding",
        tool_digest=demo.CHANGED_TOOL_DIGEST,
        reviewed_tool_digest=demo.REVIEWED_TOOL_DIGEST,
    )

    assert codebuild.started == [
        {"projectName": "m12-module12-demo-snyk-scan"}
    ]
    assert published["mode"] == "aws_codebuild_snyk_cli"
    assert published["build_status"] == "SUCCEEDED"
    assert published["finding"]["finding_id"] == finding_id
    assert s3.requests == [
        {
            "Bucket": "m12-evidence",
            "Key": f"findings/{finding_id}/{scan_digest}.json",
        }
    ]


def test_snyk_secret_is_injected_only_into_scanner_codebuild() -> None:
    infrastructure = (
        Path(demo.ROOT)
        / "module12"
        / "infrastructure"
        / "pulumi"
        / "posture_infrastructure.py"
    ).read_text()
    stack = (
        Path(demo.ROOT)
        / "module12"
        / "infrastructure"
        / "pulumi"
        / "__main__.py"
    ).read_text()

    assert '"name": "SNYK_TOKEN"' in infrastructure
    assert '"type": "SECRETS_MANAGER"' in infrastructure
    assert '"Action": "secretsmanager:GetSecretValue"' in infrastructure
    assert '"Resource": values[2]' in infrastructure
    runtime_policy = stack[
        stack.index("runtime_policy ="):stack.index(
            'aws.iam.RolePolicy(\n    "runtime-permissions"'
        )
    ]
    assert "snyk_secret.arn" not in runtime_policy


def test_honeycomb_export_is_configured_only_on_agentcore_runtime() -> None:
    security_controls = (
        Path(demo.ROOT)
        / "module12"
        / "infrastructure"
        / "pulumi"
        / "security_controls.py"
    ).read_text()
    stack = (
        Path(demo.ROOT)
        / "module12"
        / "infrastructure"
        / "pulumi"
        / "__main__.py"
    ).read_text()

    assert '"MODULE12_HONEYCOMB_SECRET_ARN": honeycomb_secret.arn' in (
        security_controls
    )
    assert '"MODULE12_HONEYCOMB_OTLP_ENDPOINT": honeycomb_endpoint' in (
        security_controls
    )
    assert '"OTEL_SERVICE_NAME": honeycomb_dataset' in security_controls
    assert "gen_ai_unredacted_attributes=" in security_controls
    assert '"honeycombDataset": honeycomb_dataset' in security_controls
    runtime_policy = stack[
        stack.index("runtime_policy ="):stack.index(
            'aws.iam.RolePolicy(\n    "runtime-permissions"'
        )
    ]
    assert '"Sid": "TelemetrySecretRead"' in runtime_policy
    assert '"Resource": values[6]' in runtime_policy
    assert 'config.require_secret("honeycombIngestKey")' in stack
    assert "aws.secretsmanager.SecretVersion(" in stack


def test_section_3_is_independently_runnable_locally(capsys) -> None:
    assert demo.main(["--section", "3", "--no-pause", "--session", "test-three"]) == 0

    output = capsys.readouterr()
    assert "LOCAL HONEYCOMB SIMULATION" in output.out
    assert "Dimensions overrepresented in denied workflows" in output.out
    assert "First unsafe transition" not in output.out
    assert "Section 3 summary" in output.out
    assert "strands_before_tool_call" in output.out
    assert "companion-governance" in output.out
    assert "Snyk" not in output.out
    assert "SECTION 3 — BLAST RADIUS" not in output.out
    assert "Denied workflows with mutation" not in output.out
    assert output.err == ""


def test_local_honeycomb_compares_taint_and_quarantine_evidence() -> None:
    normal = run_workflow("normal").to_dict()
    tainted = run_workflow("tainted_repository").to_dict()
    quarantined = run_workflow(
        "normal",
        store=InMemoryWorkflowStore({"snyk_posture": "quarantine"}),
    ).to_dict()
    dataset = LocalHoneycombDataset.from_outcomes(
        [normal, tainted, quarantined]
    )

    policy_events = dataset.where(name="policy.authorize")
    assert all(
        event.get("policy.layer") == INTERVENTION_LAYER
        and event.get("policy.handler") == INTERVENTION_NAME
        and event.get("intervention.action") in {"proceed", "deny"}
        for event in policy_events
    )
    denied = [
        event
        for event in policy_events
        if event.get("policy.decision") == "DENY"
    ]
    allowed = [
        event
        for event in policy_events
        if event.get("policy.decision") == "ALLOW"
    ]
    comparison = dataset.compare_populations(denied, allowed)
    comparison_values = {
        (row["field"], row["value"]) for row in comparison
    }

    assert dataset.trace_count == 3
    assert ("session.tainted", True) in comparison_values
    assert ("snyk.posture", "quarantine") in comparison_values


def test_cedar_policy_scopes_specific_gateway_actions() -> None:
    gateway_arn = (
        "arn:aws:bedrock-agentcore:us-east-1:ACCOUNT_ID:gateway/gateway-123"
    )
    policy = build_cedar_policy(gateway_arn)

    assert (
        'action == AgentCore::Action::"companion-tools___read_repository"'
        in policy
    )
    assert (
        'action == AgentCore::Action::"companion-tools___apply_infrastructure"'
        in policy
    )
    assert f'resource == AgentCore::Gateway::"{gateway_arn}"' in policy
    assert 'context.input.snyk_posture != "quarantine"' in policy
    assert 'AgentCore::Action::"Http"' not in policy
    assert 'AgentCore::Action::"CallTool"' not in policy


def test_cedar_policy_scopes_the_runtime_principal() -> None:
    principal_id = (
        "arn:aws:sts::ACCOUNT_ID:assumed-role/m12-demo-runtime"
    )
    policy = build_cedar_policy(
        "arn:aws:bedrock-agentcore:us-east-1:ACCOUNT_ID:gateway/gateway-123",
        principal_ids=[principal_id],
    )

    assert f'principal.id == "{principal_id}"' in policy


def test_agentcore_cedar_resources_receive_one_statement_each() -> None:
    gateway_arn = (
        "arn:aws:bedrock-agentcore:us-east-1:ACCOUNT_ID:gateway/gateway-123"
    )
    statements = build_cedar_statements(gateway_arn)

    assert tuple(statements) == (*READ_ONLY_TOOLS, *MUTATION_TOOLS)
    assert all(statement.count("permit(") == 1 for statement in statements.values())
    assert (
        'context.input.snyk_posture != "quarantine"'
        in statements["apply_infrastructure"]
    )
    assert 'context.input.artifact_digest != ""' in statements["apply_infrastructure"]
    assert (
        'context.input.reviewed_artifact_digest != ""'
        in statements["apply_infrastructure"]
    )
    assert "context.input.mutation == false" in statements["read_repository"]
    assert "context.input.snyk_posture" not in statements["read_repository"]


def test_gateway_interceptor_reloads_external_governance_before_cedar() -> None:
    class GovernanceTable:
        def get_item(self, **kwargs: Any) -> dict[str, Any]:
            assert kwargs == {
                "Key": {"workflowId": "workflow-test"},
                "ConsistentRead": True,
            }
            return {
                "Item": {
                    "companion_posture": "healthy",
                    "security_review": "approved",
                    "financial_approval": "approved",
                    "reviewed_artifact_digest": "sha256:reviewed",
                    "environment": "staging",
                }
            }

    class PostureTable:
        def query(self, **kwargs: Any) -> dict[str, Any]:
            assert kwargs["ScanIndexForward"] is False
            assert kwargs["Limit"] == 1
            assert kwargs["ConsistentRead"] is True
            return {
                "Items": [
                    {
                        "postureField": "snyk_posture",
                        "posture": "quarantine",
                    }
                ]
            }

    request = {
        "mcp": {
            "gatewayRequest": {
                "body": {
                    "jsonrpc": "2.0",
                    "method": "tools/call",
                    "params": {
                        "name": "companion-tools___apply_infrastructure",
                        "arguments": {
                            "workflow_id": "workflow-test",
                            "mutation": True,
                            "session_tainted": False,
                            "artifact_digest": "sha256:proposed",
                            "snyk_posture": "healthy",
                            "financial_approval": "rejected",
                        },
                    },
                }
            }
        }
    }

    transformed = transform_request(
        request,
        governance_table=GovernanceTable(),
        posture_table=PostureTable(),
    )
    arguments = transformed["params"]["arguments"]

    assert arguments["session_tainted"] is False
    assert arguments["artifact_digest"] == "sha256:proposed"
    assert arguments["snyk_posture"] == "quarantine"
    assert arguments["financial_approval"] == "approved"
    assert arguments["reviewed_artifact_digest"] == "sha256:reviewed"
    assert arguments["environment"] == "staging"
    assert arguments["governance_source"] == GOVERNANCE_SOURCE


def test_gateway_interceptor_missing_state_fails_closed() -> None:
    class EmptyGovernanceTable:
        def get_item(self, **kwargs: Any) -> dict[str, Any]:
            return {}

    class EmptyPostureTable:
        def query(self, **kwargs: Any) -> dict[str, Any]:
            return {"Items": []}

    transformed = transform_request(
        {
            "mcp": {
                "gatewayRequest": {
                    "body": {
                        "method": "tools/call",
                        "params": {
                            "arguments": {
                                "workflow_id": "workflow-missing",
                                "session_tainted": False,
                                "artifact_digest": "sha256:proposed",
                            }
                        },
                    }
                }
            }
        },
        governance_table=EmptyGovernanceTable(),
        posture_table=EmptyPostureTable(),
    )
    arguments = transformed["params"]["arguments"]

    assert arguments["companion_posture"] == "quarantine"
    assert arguments["snyk_posture"] == "quarantine"
    assert arguments["security_review"] == "pending"
    assert arguments["financial_approval"] == "pending"
    assert arguments["reviewed_artifact_digest"] == ""
    assert arguments["environment"] == "production"


def test_gateway_probe_uses_runtime_context_and_reports_cedar_denial() -> None:
    class DenyingGateway:
        def invoke(
            self,
            tool: str,
            *,
            workflow_id: str,
            trusted_context: dict[str, Any],
        ) -> dict[str, Any]:
            assert tool == "apply_infrastructure"
            assert workflow_id == "workflow-probe"
            assert trusted_context["session_tainted"] is True
            raise GatewayInvocationError("AgentCore Gateway returned HTTP 403")

    result = run_gateway_probe(
        "apply_infrastructure",
        "tainted_repository",
        "workflow-probe",
        store=InMemoryWorkflowStore(),
        gateway_invoker=DenyingGateway(),
    )

    assert result["allowed"] is False
    assert result["source"] == "agentcore_gateway_authorization"
    assert result["status_code"] == 403


def test_gateway_lambda_contract_returns_direct_tool_result() -> None:
    context = SimpleNamespace(
        client_context=SimpleNamespace(
            custom={
                "bedrockAgentCoreToolName": (
                    "companion-tools___apply_infrastructure"
                )
            }
        )
    )
    result = handler(
        {
            "mutation": True,
            "session_tainted": False,
            "companion_posture": "healthy",
            "snyk_posture": "healthy",
            "security_review": "approved",
            "financial_approval": "approved",
            "environment": "staging",
            "artifact_digest": "sha256:approved",
            "reviewed_artifact_digest": "sha256:approved",
        },
        context,
    )

    assert result["tool"] == "apply_infrastructure"
    assert result["status"] == "simulated"
    assert result["infrastructure_changed"] is False
    assert "statusCode" not in result


def test_sections_clear_before_scenario_transitions(monkeypatch, capsys) -> None:
    screens: list[str] = []
    headers: list[tuple[str, str]] = []

    def record_header(title: str, color: str = "cyan") -> None:
        screens.append(title)
        headers.append((title, color))

    monkeypatch.setattr(demo, "clear_screen", lambda: screens.append("clear"))
    monkeypatch.setattr(demo, "header", record_header)
    context = demo.DemoContext(
        no_pause=True,
        session_id=demo._session_id("screen-test"),
        region="us-east-1",
    )

    demo.section_1(context)
    assert screens[:12] == [
        "clear",
        "SECTION 1 — ENFORCEMENT LAYERS",
        "clear",
        "SECTION 1 — EXPECTED REQUEST PATH",
        "clear",
        "SECTION 1 — STRANDS POLICY DECISION",
        "clear",
        "SECTION 1 — AGENTCORE GATEWAY AUTHORIZATION — EXPECTED REQUEST",
        "clear",
        "SECTION 1 — POISONED REPOSITORY",
        "clear",
        "SECTION 1 — AGENTCORE GATEWAY AUTHORIZATION — TAINTED REQUEST",
    ]

    screens.clear()
    demo.section_2(context)
    assert screens == [
        "clear",
        "SECTION 2 — SNYK FOR AGENTIC SYSTEMS",
        "clear",
        "SECTION 2 — THE TOOL SNYK WILL SCAN",
        "clear",
        "SECTION 2 — PUBLISH HIGH-SEVERITY SNYK FINDING",
        "clear",
        "SECTION 2 — REVIEW THE SNYK PROJECT",
        "clear",
        "SECTION 2 — QUARANTINED TOOL BEHAVIOR",
        "clear",
        "SECTION 2 — AGENTCORE GATEWAY ENFORCEMENT",
        "clear",
        "SECTION 2 — RECOVER AFTER TOOL REMEDIATION",
    ]

    screens.clear()
    demo.section_3(context)
    assert screens[:2] == [
        "clear",
        "SECTION 3 — INVESTIGATE WORKFLOW BEHAVIOR",
    ]

    screens.clear()
    cloud_context = SimpleNamespace(
        cloud=True,
        no_pause=True,
        outcomes=[
            {
                "workflow_id": "workflow-screen-test",
                "session_id": "session-screen-test",
                "scenario": "tainted_repository",
                "mutation_recorded": False,
                "response": {
                    "snyk_posture": "healthy",
                    "policy": {
                        "decision": "DENY",
                        "rule": "deny_tainted_deployment",
                        "context": {"session_tainted": True},
                    },
                    "telemetry": {
                        "honeycomb_export_enabled": True,
                    },
                },
            }
        ],
    )
    capsys.readouterr()
    demo.section_3(cloud_context)
    cloud_section_3_output = capsys.readouterr().out
    assert "Snyk" not in cloud_section_3_output
    assert "AI-ready observability platform" in cloud_section_3_output
    assert "questions they did not know" in cloud_section_3_output
    assert "Why traces matter" not in cloud_section_3_output
    assert "Query AgentCore Gateway authorization" not in cloud_section_3_output
    assert "Open one complete request trace" not in cloud_section_3_output
    assert "What to inspect in the trace" not in cloud_section_3_output
    assert "Section 3 summary" in cloud_section_3_output
    assert "heatmap" not in cloud_section_3_output.casefold()
    assert "Paste-ready Honeycomb trace query JSON" not in cloud_section_3_output
    assert screens == [
        "clear",
        "SECTION 3 — INVESTIGATE WORKFLOW BEHAVIOR",
        "clear",
        "SECTION 3 — HONEYCOMB WORKFLOW OUTCOMES",
        "clear",
        "SECTION 3 — BUBBLEUP DENIED WORKFLOWS",
    ]
    section_colors = {
        section: {
            color
            for title, color in headers
            if title.startswith(f"SECTION {section} —")
        }
        for section in (1, 2, 3)
    }
    assert section_colors == {
        1: {demo.SECTION_1_COLOR},
        2: {demo.SECTION_2_COLOR},
        3: {demo.SECTION_3_COLOR},
    }
    assert len(
        {
            demo.SECTION_1_COLOR,
            demo.SECTION_2_COLOR,
            demo.SECTION_3_COLOR,
        }
    ) == 3


def test_section_2_waits_for_each_demo_beat(monkeypatch) -> None:
    prompts: list[str] = []
    monkeypatch.setattr(
        "builtins.input",
        lambda message: prompts.append(message) or "",
    )
    context = demo.DemoContext(
        no_pause=False,
        session_id=demo._session_id("pause-test"),
        region="us-east-1",
    )

    demo.section_2(context)

    assert prompts == [
        "  Press Enter to inspect the Companion tool dependency Snyk will scan...",
        "  Press Enter to publish the high-severity Snyk finding...",
        "  Press Enter to open the Snyk project...",
        "  Press Enter after reviewing the findings in Snyk...",
        "  Press Enter to send the same calls through AgentCore Gateway...",
        "  Press Enter to remediate the tool and restore authority...",
        "  Press Enter to continue...",
    ]


def test_wrap_up_matches_the_three_section_outcomes(capsys) -> None:
    context = demo.DemoContext(
        no_pause=True,
        session_id=demo._session_id("wrap-up-test"),
        region="us-east-1",
    )

    demo.show_wrap_up(context)

    output = " ".join(capsys.readouterr().out.split())
    assert "Section 1 — Enforce two authority boundaries" in output
    assert "Strands stopped unsafe calls inside the agent lifecycle" in output
    assert "AgentCore Gateway independently protected" in output
    assert "Section 2 — Snyk: turn supply-chain risk into containment" in output
    assert "Read-only work continued" in output
    assert "deployment remained denied" in output
    assert "updated the vulnerable dependency pin" in output
    assert "published the remediated tool" in output
    assert "Section 3 — Honeycomb: investigate behavior across workflows" in output
    assert (
        "Honeycomb showed what distinguished denied workflows from successful ones"
        in output
    )
    assert "BubbleUp" not in output
    assert "measured the observed quarantine and recovery window" in output
    assert "protected boundary was crossed" not in output
    assert "sanitized" not in output.casefold()
