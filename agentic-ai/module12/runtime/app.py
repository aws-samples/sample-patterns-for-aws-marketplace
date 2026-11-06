"""Module 12 AgentCore Runtime application."""
from __future__ import annotations

import json
import os
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

try:
    from module12.telemetry import (
        add_sanitized_span_attributes,
        configure_runtime_telemetry,
        force_flush_runtime_telemetry,
        runtime_request_span,
    )
    from module12.workflow import run_gateway_probe, run_workflow
except ImportError:
    from telemetry import (
        add_sanitized_span_attributes,
        configure_runtime_telemetry,
        force_flush_runtime_telemetry,
        runtime_request_span,
    )
    from workflow import run_gateway_probe, run_workflow


class Handler(BaseHTTPRequestHandler):
    server_version = "module12-runtime/0.4"

    def _send(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, sort_keys=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/ping":
            self._send(
                200,
                {
                    "status": "ok",
                    "module": "security_observability",
                    "runtime": "companion",
                },
            )
            return
        self._send(404, {"error": "not_found"})

    def do_POST(self) -> None:  # noqa: N802
        if self.path not in {"/", "/invocations"}:
            self._send(404, {"error": "not_found"})
            return
        length = int(self.headers.get("Content-Length", "0"))
        try:
            request = json.loads(self.rfile.read(length) or b"{}")
            scenario = request.get("scenario", "normal")
            action = str(request.get("action") or "run_workflow")
            workflow_id = str(
                request.get("workflow_id")
                or f"workflow-{uuid.uuid4().hex[:12]}"
            )
            session_id = str(
                request.get("session_id")
                or f"session-{uuid.uuid4().hex}"
            )
            with runtime_request_span(
                action=action,
                workflow_id=workflow_id,
                session_id=session_id,
                scenario=str(scenario),
                carrier={
                    str(key): str(value)
                    for key, value in self.headers.items()
                },
            ) as span:
                if action == "gateway_probe":
                    result = run_gateway_probe(
                        str(request.get("tool") or ""),
                        str(scenario),
                        workflow_id,
                    )
                    add_sanitized_span_attributes(
                        span,
                        {
                            "gateway.status_code": result.get("status_code"),
                        },
                    )
                    response_status = 200
                    response_payload = result
                else:
                    outcome = run_workflow(
                        str(scenario),
                        session_id=session_id,
                        workflow_id=workflow_id,
                        model_output=request.get("model_output"),
                    )
                    policy = outcome.response.get("policy", {})
                    add_sanitized_span_attributes(
                        span,
                        {
                            "workflow.status": outcome.status,
                            "policy.decision": policy.get("decision"),
                            "policy.rule": policy.get("rule"),
                            "deployment.invocation_recorded": (
                                outcome.mutation_recorded
                            ),
                            "smoke_test.status": outcome.smoke_test_status,
                        },
                    )
                    response_status = 200
                    response_payload = outcome.to_dict()
            force_flush_runtime_telemetry()
            self._send(response_status, response_payload)
        except (ValueError, TypeError, json.JSONDecodeError) as error:
            force_flush_runtime_telemetry()
            self._send(400, {"error": str(error)})
        except Exception as error:  # noqa: BLE001
            force_flush_runtime_telemetry()
            print(
                f"module12 runtime execution failed: {type(error).__name__}",
                flush=True,
            )
            self._send(
                500,
                {
                    "error": "runtime_execution_failed",
                    "error_type": type(error).__name__,
                },
            )

    def log_message(self, format: str, *args: object) -> None:
        print(format % args, flush=True)


def main() -> None:
    port = int(os.environ.get("PORT", "8080"))
    telemetry = configure_runtime_telemetry()
    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    print(
        "module12 runtime listening on "
        f"{port}; honeycomb_export={'enabled' if telemetry.export_enabled else 'disabled'}",
        flush=True,
    )
    server.serve_forever()


if __name__ == "__main__":
    main()
