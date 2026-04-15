"""
routing-agent/app.py
====================
HTTP server for routing agent.

Provides REST API endpoint for intent classification and routing.
"""

from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

from routing_agent.agent import classify_intent, route_request


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

PORT = int(os.getenv("ROUTING_PORT", "8083"))
HOST = os.getenv("ROUTING_HOST", "0.0.0.0")
VERBOSE = os.getenv("ROUTING_VERBOSE", "false").lower() == "true"


# ---------------------------------------------------------------------------
# HTTP Request Handler
# ---------------------------------------------------------------------------

class RoutingHandler(BaseHTTPRequestHandler):
    """HTTP request handler for routing agent endpoints."""

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
                "service": "routing-agent",
                "version": "0.1.0",
            })
        elif self.path == "/categories":
            # Return available categories
            from routing_agent.prompts.routing_prompts import CATEGORY_DESCRIPTIONS
            self._send_json_response({
                "categories": CATEGORY_DESCRIPTIONS,
            })
        else:
            self._send_error_response("Not found", 404)

    def do_POST(self) -> None:
        """Handle POST requests."""
        try:
            # Parse request body
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length).decode()
            
            try:
                data = json.loads(body) if body else {}
            except json.JSONDecodeError:
                self._send_error_response("Invalid JSON in request body")
                return

            # Route to appropriate handler
            if self.path == "/route":
                self._handle_route(data)
            elif self.path == "/classify":
                self._handle_classify(data)
            else:
                self._send_error_response("Not found", 404)

        except Exception as e:
            self._send_error_response(f"Internal server error: {str(e)}", 500)

    def _handle_route(self, data: dict[str, Any]) -> None:
        """
        Handle /route endpoint - full routing with suggested action.
        
        Request body:
        {
            "request": "User's request text"
        }
        """
        request_text = data.get("request")
        if not request_text:
            self._send_error_response("Missing 'request' in request body")
            return

        try:
            result = route_request(
                request=request_text,
                verbose=VERBOSE,
            )
            
            self._send_json_response({
                "status": "success",
                "routing": result,
            })
        except Exception as e:
            self._send_error_response(f"Routing failed: {str(e)}", 500)

    def _handle_classify(self, data: dict[str, Any]) -> None:
        """
        Handle /classify endpoint - classification only (no routing metadata).
        
        Request body:
        {
            "request": "User's request text"
        }
        """
        request_text = data.get("request")
        if not request_text:
            self._send_error_response("Missing 'request' in request body")
            return

        try:
            result = classify_intent(
                request=request_text,
                verbose=VERBOSE,
            )
            
            self._send_json_response({
                "status": "success",
                "classification": result,
            })
        except Exception as e:
            self._send_error_response(f"Classification failed: {str(e)}", 500)

    def log_message(self, format: str, *args: Any) -> None:
        """Override to customize logging."""
        if VERBOSE:
            print(f"[RoutingAgent] {format % args}")


# ---------------------------------------------------------------------------
# Server
# ---------------------------------------------------------------------------

def run_server(port: int = PORT, host: str = HOST) -> None:
    """
    Run the routing agent HTTP server.

    Parameters
    ----------
    port : int
        Port to listen on. Default 8083.
    host : str
        Host to bind to. Default "0.0.0.0".
    """
    server = HTTPServer((host, port), RoutingHandler)
    print(f"""
╔══════════════════════════════════════════════════════════════════╗
║  Routing Agent: Intent Classification & Request Routing         ║
╚══════════════════════════════════════════════════════════════════╝

  Server running on http://{host}:{port}

  Endpoints:
    GET  /ping              - Health check
    GET  /categories        - List available categories
    POST /classify          - Classify intent only
    POST /route             - Classify and provide routing info

  Categories:
    • repository_analysis    → Module 2 (port 8081)
    • infrastructure_generation → Module 3 (port 8082)
    • aws_infrastructure     → Module 1 (port 8080)
    • deployment_monitoring  → Future capability

  Example:
    curl -X POST http://localhost:{port}/route \\
      -H "Content-Type: application/json" \\
      -d '{{"request": "Analyze my repository at /home/user/app"}}'

  Press Ctrl+C to stop
""")
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n\nShutting down server...")
        server.shutdown()


if __name__ == "__main__":
    run_server()
