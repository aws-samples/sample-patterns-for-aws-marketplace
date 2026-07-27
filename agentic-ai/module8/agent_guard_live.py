from __future__ import annotations

import argparse
import asyncio
import json
import os
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path

from module8.config.env import load_agentic_env


@dataclass(frozen=True)
class AgentGuardLiveConfig:
    repo_root: Path
    aws_profile: str | None
    aws_region: str
    secret_id: str
    secret_env_var: str
    audit_log_file: Path

    @property
    def agentic_root(self) -> Path:
        return self.repo_root / "agentic-ai"

    @property
    def python_bin(self) -> Path:
        return self.agentic_root / ".venv" / "bin" / "python"

    @property
    def agc_bin(self) -> Path:
        return self.agentic_root / ".venv" / "bin" / "agc"

    @property
    def secret_uri(self) -> str:
        return f"aws://{self.secret_id}/{self.secret_env_var}"


@dataclass(frozen=True)
class AgentGuardAuditEvidence:
    request_recorded: bool = False
    response_recorded: bool = False

    def to_dict(self) -> dict:
        return {
            "request_recorded": self.request_recorded,
            "response_recorded": self.response_recorded,
        }


@dataclass(frozen=True)
class AgentGuardBoundaryEvidence:
    agent_process_before_has_secret: bool
    agent_process_after_has_secret: bool
    secret_source: str
    operation_result: dict
    operation_audit: AgentGuardAuditEvidence
    captured_stderr: str = ""

    def to_dict(self) -> dict:
        return {
            "agent_process": {
                "credential_present_before": self.agent_process_before_has_secret,
                "credential_present_after": self.agent_process_after_has_secret,
            },
            "secret_source": self.secret_source,
            "operation": self.operation_result,
            "operation_audit": self.operation_audit.to_dict(),
        }


class AgentGuardProbeError(RuntimeError):
    def __init__(self, message: str, captured_stderr: str = "") -> None:
        super().__init__(message)
        self.captured_stderr = captured_stderr


def boundary_evidence_failures(evidence: AgentGuardBoundaryEvidence) -> list[str]:
    failures: list[str] = []
    if evidence.agent_process_before_has_secret:
        failures.append("credential was already present in the agent process")
    if evidence.agent_process_after_has_secret:
        failures.append("credential remained in the agent process after the MCP call")
    operation = evidence.operation_result
    if not (
        operation["decision"] == "allowed"
        and not operation["blocked"]
        and operation["executed"]
    ):
        failures.append("protected MCP tool did not execute the allowed operation")
    if not operation["credential_present_in_protected_process"]:
        failures.append("credential was absent during the protected MCP operation")
    if not (
        evidence.operation_audit.request_recorded
        and evidence.operation_audit.response_recorded
    ):
        failures.append("Agent Guard did not record both sides of the MCP operation")
    return failures


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _path_from_env(name: str, default: Path, base: Path) -> Path:
    value = os.getenv(name)
    path = Path(value) if value else default
    return path if path.is_absolute() else base / path


def load_config() -> AgentGuardLiveConfig:
    load_agentic_env()
    repo_root = _repo_root()
    agentic_root = repo_root / "agentic-ai"
    default_generated = agentic_root / "module8" / "generated"
    return AgentGuardLiveConfig(
        repo_root=repo_root,
        aws_profile=os.getenv("AWS_PROFILE") or None,
        aws_region="us-east-1",
        secret_id=os.getenv("MODULE8_AGC_SECRET_ID", "devops-companion-github-token"),
        secret_env_var=os.getenv("MODULE8_AGC_SECRET_ENV", "GITHUB_TOKEN"),
        audit_log_file=_path_from_env(
            "MODULE8_AGC_AUDIT_LOG",
            default_generated / "agent-guard-audit.log",
            agentic_root,
        ),
    )


def build_proxy_process(config: AgentGuardLiveConfig) -> dict:
    server_env = {
        "AWS_REGION": config.aws_region,
        "PYTHONPATH": str(config.agentic_root),
    }
    if config.aws_profile:
        server_env["AWS_PROFILE"] = config.aws_profile

    return {
        "command": str(config.agc_bin),
        "args": [
            "mcp-proxy",
            "start",
            "--cap",
            "audit",
            "--secret-uri",
            config.secret_uri,
            "--audit-log-file",
            str(config.audit_log_file),
            "--",
            str(config.python_bin),
            "-m",
            "module8.mcp.secret_probe_server",
        ],
        "env": server_env,
    }


def local_checks(config: AgentGuardLiveConfig) -> list[tuple[str, bool, str]]:
    checks: list[tuple[str, bool, str]] = []
    checks.append(("local agc binary", config.agc_bin.exists(), str(config.agc_bin)))
    checks.append(("local python binary", config.python_bin.exists(), str(config.python_bin)))
    try:
        import agent_guard_core  # noqa: F401
        checks.append(("agent_guard_core import", True, "installed"))
    except Exception as exc:  # pragma: no cover - environment dependent
        checks.append(("agent_guard_core import", False, str(exc)))
    try:
        import mcp  # noqa: F401
        checks.append(("mcp import", True, "installed"))
    except Exception as exc:  # pragma: no cover - environment dependent
        checks.append(("mcp import", False, str(exc)))
    return checks


def aws_secret_check(config: AgentGuardLiveConfig) -> tuple[bool, str]:
    import boto3
    from botocore.exceptions import ClientError

    session = boto3.Session(
        profile_name=config.aws_profile,
        region_name=config.aws_region,
    )
    credential_source = config.aws_profile or "default credential chain"
    sts = session.client("sts")
    identity = sts.get_caller_identity()
    secrets = session.client("secretsmanager")
    try:
        response = secrets.get_secret_value(SecretId=config.secret_id)
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "ClientError")
        if code == "ResourceNotFoundException":
            return False, (
                f"credentials={credential_source}, account={identity.get('Account')}, "
                f"secret={config.secret_id} not found in {config.aws_region}"
            )
        return False, f"{code}: {exc.response.get('Error', {}).get('Message', str(exc))}"
    value = response.get("SecretString", "")
    if not value:
        return False, f"Secret {config.secret_id!r} has no SecretString"
    return True, (
        f"credentials={credential_source}, account={identity.get('Account')}, "
        f"secret={config.secret_id}, region={config.aws_region}"
    )


def _tool_payload(result: object) -> dict:
    dumped = result.model_dump(mode="json")
    content = dumped.get("content") or []
    tool_text = content[0].get("text", "{}") if content else "{}"
    try:
        payload = json.loads(tool_text)
    except json.JSONDecodeError:
        payload = {"error": "Protected tool returned a non-JSON response."}
    return payload if isinstance(payload, dict) else {"result": payload}


def _sanitize_operation_result(payload: dict) -> dict:
    credential_state = payload.get("credential_state")
    if not isinstance(credential_state, dict):
        credential_state = {}
    result = payload.get("result")
    if not isinstance(result, dict):
        result = {}
    repositories = result.get("repositories")
    if not isinstance(repositories, list):
        repositories = []
    return {
        "request_id": payload.get("request_id"),
        "action": payload.get("action"),
        "policy": payload.get("policy"),
        "decision": payload.get("decision"),
        "blocked": bool(payload.get("blocked")),
        "executed": bool(payload.get("executed")),
        "credential_present_in_protected_process": bool(credential_state.get("present")),
        "target_result": "representative",
        "result": {
            "repositories": [str(repository) for repository in repositories],
            "count": int(result.get("count", len(repositories))),
        },
    }


def read_audit_evidence(
    audit_log_file: Path,
    *,
    start_offset: int,
    request_id: str,
) -> AgentGuardAuditEvidence:
    if not audit_log_file.exists():
        return AgentGuardAuditEvidence()

    with audit_log_file.open("r", encoding="utf-8", errors="replace") as audit_file:
        audit_file.seek(start_offset)
        new_log = audit_file.read()

    matching_lines = [line for line in new_log.splitlines() if request_id in line]
    request_line = next((line for line in matching_lines if "Request to CallTool" in line), "")
    response_line = next((line for line in matching_lines if "Response from CallTool" in line), "")
    return AgentGuardAuditEvidence(bool(request_line), bool(response_line))


async def _probe_mcp_async(
    config: AgentGuardLiveConfig,
    *,
    agent_process_before_has_secret: bool,
) -> AgentGuardBoundaryEvidence:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    process = build_proxy_process(config)
    operation_request_id = f"repository-list-{uuid.uuid4().hex[:12]}"
    audit_offset = config.audit_log_file.stat().st_size if config.audit_log_file.exists() else 0
    params = StdioServerParameters(
        command=process["command"],
        args=process["args"],
        env=process["env"],
        cwd=str(config.agentic_root),
    )
    with tempfile.TemporaryFile(mode="w+", encoding="utf-8") as captured_stderr:
        try:
            async with stdio_client(params, errlog=captured_stderr) as streams:
                async with ClientSession(*streams) as session:
                    await session.initialize()
                    operation_payload = _tool_payload(
                        await session.call_tool(
                            "execute_guarded_action",
                            arguments={
                                "action": "list_private_repositories",
                                "request_id": operation_request_id,
                                "env_var": config.secret_env_var,
                            },
                        )
                    )
        except Exception as exc:
            captured_stderr.flush()
            captured_stderr.seek(0)
            raise AgentGuardProbeError(str(exc), captured_stderr.read()) from exc
        captured_stderr.flush()
        captured_stderr.seek(0)
        captured_process_output = captured_stderr.read()

    evidence = AgentGuardBoundaryEvidence(
        agent_process_before_has_secret=agent_process_before_has_secret,
        agent_process_after_has_secret=os.environ.get(config.secret_env_var) is not None,
        secret_source=config.secret_uri,
        operation_result=_sanitize_operation_result(operation_payload),
        operation_audit=read_audit_evidence(
            config.audit_log_file,
            start_offset=audit_offset,
            request_id=operation_request_id,
        ),
        captured_stderr=captured_process_output,
    )
    failures = boundary_evidence_failures(evidence)
    if failures:
        raise AgentGuardProbeError(
            "Agent Guard boundary verification failed: " + "; ".join(failures),
            captured_process_output,
        )
    return evidence


def probe_mcp(config: AgentGuardLiveConfig) -> AgentGuardBoundaryEvidence:
    agent_process_before_has_secret = os.environ.get(config.secret_env_var) is not None
    if agent_process_before_has_secret:
        raise AgentGuardProbeError(
            f"Refusing to run: the agent process already has {config.secret_env_var}. "
            "Remove it so Agent Guard is the only credential injection boundary."
        )
    config.audit_log_file.parent.mkdir(parents=True, exist_ok=True)
    return asyncio.run(
        _probe_mcp_async(
            config,
            agent_process_before_has_secret=agent_process_before_has_secret,
        )
    )


def _print_checks(checks: list[tuple[str, bool, str]]) -> None:
    for name, ok, detail in checks:
        marker = "PASS" if ok else "WARN"
        print(f"{marker:4} {name}: {detail}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Module 8 CyberArk Agent Guard live helper")
    parser.add_argument(
        "command",
        choices=["check-local", "check-aws", "probe-mcp"],
        help="Run local/AWS preflight checks or the live MCP probe.",
    )
    args = parser.parse_args()

    config = load_config()

    if args.command == "check-local":
        _print_checks(local_checks(config))
        print(f"AGC secret URI: {config.secret_uri}")
        return

    if args.command == "probe-mcp":
        result = probe_mcp(config)
        print(json.dumps(result.to_dict(), indent=2))
        return

    ok, detail = aws_secret_check(config)
    marker = "PASS" if ok else "FAIL"
    print(f"{marker} AWS Secrets Manager: {detail}")


if __name__ == "__main__":
    main()
