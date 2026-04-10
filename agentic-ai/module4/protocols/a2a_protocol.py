"""
module4/protocols/a2a_protocol.py
==================================
Direct HTTP agent-to-agent communication protocol.

This module implements agent-to-agent communication where the orchestrator
sends HTTP requests to specialist agent endpoints and receives structured
JSON responses. This is the same underlying concept that protocols like
Google's A2A formalize into a full specification (with Agent Cards,
JSON-RPC, task lifecycle, etc.). Here we use a simplified Direct HTTP
approach to demonstrate the pattern.

PATTERN: Hub-and-spoke — orchestrator calls agents via their REST APIs.

In production, agents run as separate services (containers, Lambda, etc.).
In mock mode, responses are simulated locally without network calls.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any

from module4.mock.agent_mocks import get_mock_response


# Mock mode flag
_MOCK = os.getenv("AGENT_MOCK_MODE", "true").lower() == "true"

# Agent endpoint URLs
AGENT_ENDPOINTS = {
    "module1": os.getenv("MODULE1_URL", "http://localhost:8080"),
    "module2": os.getenv("MODULE2_URL", "http://localhost:8081"),
    "module3": os.getenv("MODULE3_URL", "http://localhost:8082"),
}


# ---------------------------------------------------------------------------
# A2A Client
# ---------------------------------------------------------------------------

class A2AClient:
    """
    Agent-to-Agent HTTP client for calling specialist agents.

    In mock mode, returns simulated responses.
    In live mode, sends HTTP POST requests to agent endpoints.

    Parameters
    ----------
    verbose : bool
        Print request/response details.

    Example
    -------
    >>> client = A2AClient(verbose=True)
    >>> result = client.call_agent("module1", "health_check", region="us-east-1")
    >>> print(result["data"]["environment_summary"]["healthy"])
    2
    """

    def __init__(self, verbose: bool = True):
        self.verbose = verbose

    def call_agent(
        self,
        agent_id: str,
        task: str,
        payload: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """
        Call a specialist agent via A2A protocol.

        Parameters
        ----------
        agent_id : str
            Target agent identifier (module1, module2, module3).
        task : str
            Task type to execute (health_check, analyze_repository, etc.).
        payload : dict, optional
            Request payload to send to the agent.
        **kwargs
            Additional parameters passed to mock handlers.

        Returns
        -------
        dict
            Agent response with structured data.
        """
        endpoint = AGENT_ENDPOINTS.get(agent_id)
        if not endpoint:
            return {
                "agent": agent_id,
                "error": f"Unknown agent: {agent_id}",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

        if self.verbose:
            print(f"  [HTTP] POST {endpoint}/{task}")
            if payload:
                print(f"  [HTTP] Payload: {json.dumps(payload, indent=2)[:200]}...")

        if _MOCK:
            response = get_mock_response(agent_id, task, **kwargs)
        else:
            response = self._http_call(agent_id, task, payload or kwargs)

        if self.verbose:
            status = response.get("data", {}).get("error", "OK")
            if status == "OK":
                print(f"  [HTTP] Response: 200 OK from {agent_id}")
            else:
                print(f"  [HTTP] Response: Error from {agent_id}: {status}")

        return response

    def call_agents_sequential(
        self,
        tasks: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """
        Call multiple agents sequentially, passing outputs forward.

        Each task can reference previous results via {prev_result} in its payload.

        Parameters
        ----------
        tasks : list of dict
            List of task definitions, each with:
            - agent_id: str
            - task: str
            - payload: dict (optional)

        Returns
        -------
        list of dict
            Ordered list of agent responses.
        """
        results = []

        for i, task_def in enumerate(tasks):
            if self.verbose:
                print(f"\n  [HTTP Sequential] Step {i+1}/{len(tasks)}: "
                      f"{task_def['agent_id']}/{task_def['task']}")

            result = self.call_agent(
                agent_id=task_def["agent_id"],
                task=task_def["task"],
                payload=task_def.get("payload"),
            )
            results.append(result)

        return results

    def call_agents_parallel(
        self,
        tasks: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """
        Call multiple agents in parallel (simulated in mock mode).

        In production, this would use asyncio or threading for true parallelism.

        Parameters
        ----------
        tasks : list of dict
            List of task definitions to execute concurrently.

        Returns
        -------
        list of dict
            Agent responses (order matches input tasks).
        """
        if self.verbose:
            agent_names = [f"{t['agent_id']}/{t['task']}" for t in tasks]
            print(f"\n  [HTTP Parallel] Dispatching {len(tasks)} tasks: {', '.join(agent_names)}")

        # In mock mode, execute sequentially but present as parallel
        # In production, use concurrent.futures.ThreadPoolExecutor
        results = []
        for task_def in tasks:
            result = self.call_agent(
                agent_id=task_def["agent_id"],
                task=task_def["task"],
                payload=task_def.get("payload"),
            )
            results.append(result)

        if self.verbose:
            print(f"  [HTTP Parallel] All {len(tasks)} tasks completed")

        return results

    def _build_request(
        self,
        agent_id: str,
        task: str,
        payload: dict[str, Any],
    ) -> tuple[str, dict[str, Any]]:
        """
        Translate a generic (agent_id, task) into the module's actual
        endpoint path and payload format.

        Each module has its own API contract:
          - Module 1: POST /invocations  {"prompt": "..."}
          - Module 2: POST /analyze      {"repo_path": "..."}
          - Module 3: POST /generate | /validate | /analyze  (varies)
        """
        endpoint = AGENT_ENDPOINTS.get(agent_id, "")

        if agent_id == "module1":
            # Module 1 uses AgentCore-style single /invocations endpoint
            prompt = payload.get("prompt", "")
            if not prompt:
                # Build a prompt from the task name
                task_prompts = {
                    "health_check": f"Give me a complete health check of our {payload.get('region', 'us-east-1')} environment. "
                                    "If you find anything wrong, tell me what it is and what you'd recommend.",
                    "list_resources": f"List all AWS resources running in {payload.get('region', 'us-east-1')}.",
                }
                prompt = task_prompts.get(task, f"Perform a {task} in {payload.get('region', 'us-east-1')}")
            url = f"{endpoint}/invocations"
            body = {"prompt": prompt, "region": payload.get("region", "us-east-1")}

        elif agent_id == "module2":
            # Module 2 uses POST /analyze with {"repo_path": "..."}
            url = f"{endpoint}/analyze"
            body = {"repo_path": payload.get("repo_path", "/mock/repo/nodejs-app")}

        elif agent_id == "module3":
            # Module 3 has /generate, /validate, /analyze
            task_to_path = {
                "generate_cdk": "generate",
                "validate_cdk": "validate",
                "analyze_requirements": "analyze",
            }
            path = task_to_path.get(task, task)
            url = f"{endpoint}/{path}"
            body = payload

        else:
            url = f"{endpoint}/{task}"
            body = payload

        return url, body

    def _http_call(
        self,
        agent_id: str,
        task: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Make an actual HTTP call to an agent endpoint.

        Used in live mode when agents are running as services.
        Translates the generic task request into each module's actual API format.
        """
        import urllib.request
        import urllib.error

        url, body = self._build_request(agent_id, task, payload)
        data = json.dumps(body).encode("utf-8")

        if self.verbose:
            print(f"  [HTTP] Calling: {url}")

        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                raw = resp.read().decode("utf-8")
                result = json.loads(raw)
                # Wrap in standard format so downstream code works consistently
                return {
                    "agent": agent_id,
                    "task": task,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "data": result,
                }
        except Exception as e:
            # Catch all connection errors (URLError, RemoteDisconnected,
            # ConnectionRefused, timeout, etc.) so the orchestrator can
            # handle failures gracefully instead of crashing.
            error_msg = f"{type(e).__name__}: {e}"
            if self.verbose:
                print(f"  [HTTP] Error calling {agent_id}: {error_msg}")
            return {
                "agent": agent_id,
                "task": task,
                "error": error_msg,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "data": {"error": error_msg},
            }
