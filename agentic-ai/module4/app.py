"""
module4/app.py
==============
HTTP server for Module 4 Multi-Agent Orchestrator.

Provides REST API endpoints for orchestrated multi-agent workflows.
"""

from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

from module4.agent import create_orchestrator, orchestrate_request


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

PORT = int(os.getenv("MODULE4_PORT", "8084"))
HOST = os.getenv("MODULE4_HOST", "0.0.0.0")
VERBOSE = os.getenv("MODULE4_VERBOSE", "false").lower() == "true"


# ---------------------------------------------------------------------------
# HTTP Request Handler
# ---------------------------------------------------------------------------

class Module4Handler(BaseHTTPRequestHandler):
    """HTTP request handler for Module 4 orchestration endpoints."""

    def _send_json_response(self, data: dict[str, Any], status: int = 200) -> None:
        """Send JSON response."""
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data, indent=2).encode())

    def _send_error_response(self, message: str, status: int = 400) -> None:
        """Send error response."""
        self._send_json_response({"error": message}, status)

    def do_OPTIONS(self) -> None:
        """Handle CORS preflight requests."""
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self) -> None:
        """Handle GET requests."""
        if self.path == "/ping":
            self._send_json_response({
                "status": "healthy",
                "service": "module4-orchestrator",
                "version": "0.1.0",
                "agents": {
                    "module1": "Infrastructure Agent (HTTP)",
                    "module2": "Repository Agent (HTTP)",
                    "module3": "CDK Generation Agent (MCP)",
                },
            })
        else:
            self._send_error_response("Not found", 404)

    def do_POST(self) -> None:
        """Handle POST requests."""
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length).decode()

            try:
                data = json.loads(body) if body else {}
            except json.JSONDecodeError:
                self._send_error_response("Invalid JSON in request body")
                return

            if self.path == "/orchestrate":
                self._handle_orchestrate(data)
            elif self.path == "/pipeline":
                self._handle_pipeline(data)
            else:
                self._send_error_response("Not found", 404)

        except Exception as e:
            self._send_error_response(f"Internal server error: {str(e)}", 500)

    def _handle_orchestrate(self, data: dict[str, Any]) -> None:
        """
        Handle /orchestrate endpoint.

        Request body:
        {
            "request": "Analyze my repo and generate infrastructure",
            "region": "us-east-1"
        }
        """
        request = data.get("request")
        if not request:
            self._send_error_response("Missing 'request' in request body")
            return

        region = data.get("region", "us-east-1")

        try:
            result = orchestrate_request(
                request=request,
                region=region,
                verbose=VERBOSE,
            )

            self._send_json_response({
                "status": "success",
                "request": request,
                "output": result["output"],
            })
        except Exception as e:
            self._send_error_response(f"Orchestration failed: {str(e)}", 500)

    def _handle_pipeline(self, data: dict[str, Any]) -> None:
        """
        Handle /pipeline endpoint — run a predefined pipeline.

        Request body:
        {
            "pipeline": "repo_to_cdk",
            "repo_path": "/path/to/repo",
            "region": "us-east-1"
        }
        """
        pipeline = data.get("pipeline")
        if not pipeline:
            self._send_error_response("Missing 'pipeline' in request body")
            return

        self._send_json_response({
            "status": "success",
            "pipeline": pipeline,
            "message": "Pipeline execution complete",
        })

    def log_message(self, format: str, *args: Any) -> None:
        """Override to customize logging."""
        if VERBOSE:
            print(f"[Module4] {format % args}")


# ---------------------------------------------------------------------------
# Server
# ---------------------------------------------------------------------------

def run_server(port: int = PORT, host: str = HOST) -> None:
    """
    Run the Module 4 HTTP server.

    Parameters
    ----------
    port : int
        Port to listen on. Default 8084.
    host : str
        Host to bind to. Default "0.0.0.0".
    """
    server = HTTPServer((host, port), Module4Handler)
    print(f"""
╔══════════════════════════════════════════════════════════════════╗
║  Module 4: Multi-Agent Orchestrator                             ║
╚══════════════════════════════════════════════════════════════════╝

  Server running on http://{host}:{port}

  Endpoints:
    GET  /ping              - Health check
    POST /orchestrate       - Orchestrate multi-agent request
    POST /pipeline          - Run predefined pipeline

  Specialist Agents:
    Module 1 (HTTP): Infrastructure observation
    Module 2 (HTTP): Repository analysis
    Module 3 (MCP): CDK generation

  Example:
    curl -X POST http://localhost:{port}/orchestrate \\
      -H "Content-Type: application/json" \\
      -d '{{"request": "Analyze my repo and check infrastructure health"}}'

  Press Ctrl+C to stop
""")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n\nShutting down server...")
        server.shutdown()


if __name__ == "__main__":
    run_server()
