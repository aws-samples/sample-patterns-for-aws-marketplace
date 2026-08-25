#!/usr/bin/env python3
"""
demos/module1_demo.py
=====================
Live workshop demonstration for Module 1: Introduction to AI Agents.

Walks through every major concept from the slides using the real agent
running against simulated (mock) AWS data so no credentials are needed.

USAGE
-----
  # Recommended: mock mode (no AWS account needed)
  AGENT_MOCK_AWS=true python demos/module1_demo.py

  # Live AWS mode
  python demos/module1_demo.py --live

  # Run just one section
  AGENT_MOCK_AWS=true python demos/module1_demo.py --section 3

SECTIONS
--------
  1  Architecture anatomy  — the three layers in code before running
  2  The loop              — Think → Act → Observe, single query
  3  Multi-step reasoning  — compound question, multiple tool calls
  4  Human-in-the-loop     — agent finds a problem, escalates properly
  5  Model-agnostic swap   — one-line model change (Anthropic ↔ HF)
  6  Context window        — multi-turn memory demonstration
"""

from __future__ import annotations

import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ---------------------------------------------------------------------------
# Rich output helpers
# ---------------------------------------------------------------------------

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.rule import Rule
    _c = Console()

    def header(text: str, color: str = "cyan") -> None:
        _c.rule(f"[bold {color}]{text}[/bold {color}]", style=color)

    def concept(text: str) -> None:
        _c.print(f"\n[bold yellow]💡 Module 1 Concept:[/bold yellow] [yellow]{text}[/yellow]")

    def user_says(text: str) -> None:
        _c.print(f"\n[bold green]USER ›[/bold green] [italic]{text}[/italic]")

    def box(title: str, body: str) -> None:
        _c.print(Panel(f"[dim]{body}[/dim]", title=f"[bold]{title}[/bold]", border_style="cyan"))

except ImportError:
    def header(text: str, color: str = "cyan") -> None:  # type: ignore[misc]
        print(f"\n{'═' * 62}\n  {text}\n{'═' * 62}")

    def concept(text: str) -> None:  # type: ignore[misc]
        print(f"\n💡 Concept: {text}")

    def user_says(text: str) -> None:  # type: ignore[misc]
        print(f"\nUSER › {text}")

    def box(title: str, body: str) -> None:  # type: ignore[misc]
        print(f"\n[ {title} ]\n{body}")


def pause(msg: str = "  ↵  Press Enter to continue...") -> None:
    try:
        input(msg)
    except KeyboardInterrupt:
        sys.exit(0)


# ---------------------------------------------------------------------------
# Section 1 — Architecture anatomy (no agent call)
# ---------------------------------------------------------------------------

def section_1_three_layers() -> None:
    header("SECTION 1 — The Three Layers", "cyan")
    box(
        "Architecture: Module 1 Skeleton",
        "Before we run anything, let's look at how the three layers are assembled in code.",
    )

    print("""
  ┌─────────────────────────────────────────────────────────────────┐
  │  REASONING LAYER  (config/models.py)                           │
  │                                                                 │
  │    model = BedrockModel(                                        │
  │        model_id="us.anthropic.claude-sonnet-4-6",            │
  │        temperature=0.1,    ← low = deterministic infra work    │
  │    )                                                            │
  │                                                                 │
  │    # One-line swap to Hugging Face via Bedrock Marketplace:    │
  │    model = BedrockModel(model_id=hf_endpoint_arn)              │
  └─────────────────────────────────────────────────────────────────┘
              │
  ┌─────────────────────────────────────────────────────────────────┐
  │  ORCHESTRATION LAYER  (agent.py)                               │
  │                                                                 │
  │    agent = Agent(                                               │
  │        model=model,                                             │
  │        system_prompt=SYSTEM_PROMPT,                            │
  │        tools=ALL_TOOLS,                                         │
  │        conversation_manager=SlidingWindowConversationManager(  │
  │            window_size=10    ← short-term memory: 10 turns     │
  │        ),                                                       │
  │        callback_handler=LoopObserver(),  ← prints loop steps  │
  │    )                                                            │
  └─────────────────────────────────────────────────────────────────┘
              │
  ┌─────────────────────────────────────────────────────────────────┐
  │  TOOLS LAYER  (tools/aws_tools.py)                             │
  │                                                                 │
  │    @tool                         ← Strands registers this      │
  │    def list_aws_resources(       ← docstring = LLM-visible API │
  │        service_type: str,        ← LLM generates these args    │
  │        region: str,              │
  │    ) -> str:                     │
  │        '''List running AWS       │
  │        resources ...'''          │
  │        return boto3...           ← Python executes this        │
  └─────────────────────────────────────────────────────────────────┘
              │
  ┌─────────────────────────────────────────────────────────────────┐
  │  DEPLOYMENT  (app.py)                                          │
  │                                                                 │
  │    app = BedrockAgentCoreApp()   ← AgentCore wraps the agent   │
  │                                                                 │
  │    @app.entrypoint               ← same agent, managed runtime │
  │    def invoke(payload):                                         │
  │        return agent(payload["prompt"])                          │
  └─────────────────────────────────────────────────────────────────┘
""")

    concept(
        "The model is interchangeable. Swap BedrockModel(model_id=...) "
        "and NOTHING ELSE changes — tools, prompt, and AgentCore wrapper are identical."
    )
    pause()


# ---------------------------------------------------------------------------
# Section 2 — The loop (single query, watch it run)
# ---------------------------------------------------------------------------

def section_2_the_loop(agent) -> None:
    header("SECTION 2 — Think → Act → Observe", "green")
    box(
        "The agent loop running live",
        "Watch the callback handler print each step. "
        "Notice that the agent calls a tool rather than guessing the answer.",
    )

    concept(
        "This is the fundamental difference from request-response AI. "
        "The agent uses tools to get current data, then reasons over it. "
        "It cannot hallucinate what services are running — it must look."
    )

    q = "How many ECS services are running in us-east-1?"
    user_says(q)
    print()
    response = agent(q)
    print(f"\n  AGENT › {response}\n")
    pause()


# ---------------------------------------------------------------------------
# Section 3 — Multi-step reasoning
# ---------------------------------------------------------------------------

def section_3_multi_step(agent) -> None:
    header("SECTION 3 — Multi-Step Reasoning", "blue")
    box(
        "Compound query requiring a plan across multiple tools",
        "The agent must decompose the goal, choose tools in sequence, and synthesise findings.",
    )

    concept(
        "A single tool call can't answer this. The agent must plan: "
        "1) get overview, 2) identify problems, 3) drill in, 4) assess health. "
        "Watch how many ACT steps appear."
    )

    q = (
        "Give me a complete health check of our us-east-1 environment. "
        "If you find anything wrong, tell me what it is and what you'd recommend."
    )
    user_says(q)
    print()
    response = agent(q)
    print(f"\n  AGENT › {response}\n")

    concept(
        "The agent decomposed a broad goal into a sequence of tool calls. "
        "This is the planning capability of modern LLMs — no explicit workflow was coded."
    )
    pause()


# ---------------------------------------------------------------------------
# Section 4 — Human-in-the-loop
# ---------------------------------------------------------------------------

def section_4_hitl(agent) -> None:
    header("SECTION 4 — Human-in-the-Loop Pattern", "yellow")
    box(
        "Agent finds a problem and escalates — it does NOT act unilaterally",
        "This is Phase 1 (Assist) behaviour: observe, analyse, recommend, hand off.",
    )

    concept(
        "In Module 1, every proposed write operation goes through request_human_review. "
        "The agent's boundary is the analysis and the escalation ticket — not the fix. "
        "Trust is built by demonstrating accuracy before expanding autonomy."
    )

    q = (
        "The notification-svc ECS service seems to have an issue. "
        "Investigate it and, if it needs attention, raise a review request for the team."
    )
    user_says(q)
    print()
    response = agent(q)
    print(f"\n  AGENT › {response}\n")

    concept(
        "Note the 🔔 HUMAN REVIEW REQUIRED block above. "
        "The agent investigated (three tool calls), identified the root cause, "
        "formed a recommendation, and raised a structured escalation — "
        "but did NOT restart the service. Explicit escalation, not silent action."
    )
    pause()


# ---------------------------------------------------------------------------
# Section 5 — Model-agnostic swap
# ---------------------------------------------------------------------------

def section_5_models() -> None:
    header("SECTION 5 — Model-Agnostic Architecture", "magenta")
    box(
        "One-line model swap — everything else unchanged",
        "The Strands framework decouples the reasoning engine from the agent logic.",
    )

    from module1.config.models import PROVIDER_INFO, print_provider_info

    print("\n  PROVIDER A — Anthropic Claude Sonnet 4")
    print_provider_info("anthropic")

    print("\n  PROVIDER B — Hugging Face (via Bedrock Marketplace)")
    print_provider_info("huggingface")

    print("""
  ┌─────────────────────────────────────────────────────────┐
  │  # Default: Claude Sonnet 4 (Anthropic on Bedrock)      │
  │  agent = create_agent()                                  │
  │                                                          │
  │  # Switch to Hugging Face — ONE LINE change:            │
  │  agent = create_agent(                                   │
  │      hf_endpoint_arn=os.environ["HF_ENDPOINT_ARN"]     │
  │  )                                                       │
  │                                                          │
  │  # Tools, system prompt, AgentCore wrapper:             │
  │  # ← all unchanged ─────────────────────────────────── │
  └─────────────────────────────────────────────────────────┘

  How to set up a Hugging Face Bedrock Marketplace endpoint:
    1. AWS Console → Amazon Bedrock → Model Catalog
    2. Filter by Provider: "Hugging Face"
    3. Choose model (e.g. Mistral-7B-Instruct — no subscription fee)
    4. Click Deploy → select instance → wait for "In service"
    5. Copy the SageMaker endpoint ARN
    6. export HF_ENDPOINT_ARN="arn:aws:sagemaker:..."
    7. Run: python demos/module1_demo.py --hf

  Guide: https://huggingface.co/blog/bedrock-marketplace
""")

    # If HF endpoint is configured, run a side-by-side comparison
    hf_arn = os.getenv("HF_ENDPOINT_ARN")
    if hf_arn:
        from module1.agent import create_agent
        q = "How many ECS services are running in us-east-1?"
        print("  Running side-by-side comparison...\n")

        print("  [Claude Sonnet 4]")
        a_claude = create_agent(verbose=False)
        t0 = time.time()
        r_claude = a_claude(q)
        print(f"  Response: {str(r_claude)[:200]}")
        print(f"  Latency : {time.time()-t0:.2f}s\n")

        print("  [Hugging Face via Bedrock Marketplace]")
        a_hf = create_agent(hf_endpoint_arn=hf_arn, verbose=False)
        t0 = time.time()
        r_hf = a_hf(q)
        print(f"  Response: {str(r_hf)[:200]}")
        print(f"  Latency : {time.time()-t0:.2f}s")
    else:
        print("  (Set HF_ENDPOINT_ARN to run a live side-by-side comparison)")

    pause()


# ---------------------------------------------------------------------------
# Section 6 — Context window / short-term memory
# ---------------------------------------------------------------------------

def section_6_context(agent) -> None:
    header("SECTION 6 — Context Window & Short-Term Memory", "red")
    box(
        "Multi-turn conversation — the agent remembers earlier turns",
        "SlidingWindowConversationManager keeps the last 10 turns in context.",
    )

    concept(
        "Short-term memory lives INSIDE the context window. "
        "The agent can refer back to what it said in the same session using "
        "vague references like 'that service' or 'the issue you found'. "
        "Long-term memory across sessions (DynamoDB / vector store) comes in Module 7."
    )

    turns = [
        "List all ECS services in us-east-1.",
        "Which of those has an issue?",                           # vague reference
        "What would you recommend we investigate first?",         # builds on previous
        "What was the ticket ID in the review request you raised?",  # memory reach-back
    ]

    print()
    for i, q in enumerate(turns, 1):
        user_says(f"[Turn {i}] {q}")
        print()
        response = agent(q)
        print(f"\n  AGENT › {response}\n")
        if i < len(turns):
            time.sleep(0.3)

    concept(
        "The agent resolved 'those', 'that', and 'you raised' correctly "
        "because the earlier turns are still in the sliding window. "
        "After turn 11 the oldest turn would be discarded."
    )
    pause()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Module 1 Workshop Demo")
    parser.add_argument("--section", "-s", type=int, choices=range(1, 7), metavar="1-6")
    parser.add_argument("--live", action="store_true", help="Use real AWS credentials")
    parser.add_argument("--hf",   action="store_true", help="Use HF model (needs HF_ENDPOINT_ARN)")
    args = parser.parse_args()

    if not args.live:
        os.environ["AGENT_MOCK_AWS"] = "true"
        print("  Mock mode ON  (pass --live to use real AWS credentials)\n")

    from module1.agent import create_agent

    hf_arn = os.getenv("HF_ENDPOINT_ARN") if args.hf else None
    agent = create_agent(hf_endpoint_arn=hf_arn, verbose=True, window_size=10)

    header("AWS INFRASTRUCTURE AGENT — MODULE 1 DEMO", "bold cyan")
    print("""
  Use case: AWS Infrastructure Engineer building an agentic system
  to provision infrastructure, deploy microservices, and observe
  services running in AWS.

  Module 1 scope: OBSERVE AND ANALYSE only.
  No infrastructure is created or modified.
  All proposed actions go through request_human_review.
""")
    pause("  ↵  Press Enter to begin...")

    sections = {
        1: section_1_three_layers,
        2: lambda: section_2_the_loop(agent),
        3: lambda: section_3_multi_step(agent),
        4: lambda: section_4_hitl(agent),
        5: section_5_models,
        6: lambda: section_6_context(agent),
    }

    if args.section:
        sections[args.section]()
    else:
        for fn in sections.values():
            fn()

    header("DEMO COMPLETE", "bold green")
    print("""
  ✅ You've seen:
     • Three layers assembled in code
     • Think → Act → Observe loop running live
     • Multi-step reasoning across multiple tool calls
     • Human-in-the-loop escalation pattern
     • Model-agnostic architecture (Anthropic ↔ Hugging Face in one line)
     • Short-term memory via sliding context window

  🔜 Next: Module 2 — Agent Frameworks & Building Blocks
""")


if __name__ == "__main__":
    main()
