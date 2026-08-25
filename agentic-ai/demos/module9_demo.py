# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""
demos/module9_demo.py
======================
Module 9: Data Pipelines and Lineage, a 9-section interactive demo.

A raw operational event becomes governed, fresh, provenance-tracked
knowledge the DevOps Companion can safely answer from. Act 1 streams the
event through Confluent (managed Kafka); Act 2 lands it in Databricks
Delta Lake under Unity Catalog governance, then chunks, validates,
embeds, and loads it into the Module 7 knowledge base with full lineage.

Usage:
    # fully offline, no credentials (the newcomer path)
    AGENT_MOCK_PIPELINE=true AGENT_MOCK_MEMORY=true python demos/module9_demo.py

    python demos/module9_demo.py --section 5   # jump to one section
    python demos/module9_demo.py --no-pause    # run all without pausing
    python demos/module9_demo.py --mock        # force both mock flags
    python demos/module9_demo.py --live        # force live Confluent/Databricks

Sections:
    1. The Stale Agent Problem
    2. Act 1: Streaming the Event with Confluent
    3. Act 2: Landing in Delta Lake with Unity Catalog Lineage
    4. The Lineage Metadata Schema (Appendix B)
    5. Data Quality Gates
    6. Freshness Strategies and SLAs
    7. Lineage: Why Did the Agent Say This?
    8. Access Control at Ingestion and Retrieval (Module 8)
    9. Full Loop: From Kafka Offset to Governed Answer
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from typing import Callable

# ---------------------------------------------------------------------------
# Auto-load .env from the agentic-ai directory if present
# ---------------------------------------------------------------------------

def _load_dotenv() -> None:
    """Load .env file if present. WARNING: Never commit .env to version control.
    Ensure .env is listed in .gitignore before adding credentials.
    """
    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.dirname(here)
    env_path = os.path.join(root, ".env")
    if os.path.exists(env_path):
        gitignore_path = os.path.join(root, ".gitignore")
        if os.path.exists(gitignore_path):
            with open(gitignore_path) as gi:
                if ".env" not in gi.read():
                    print("WARNING: .env exists but '.env' is not in .gitignore. "
                          "Do not commit credentials to version control.",
                          file=sys.stderr)
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    if k not in os.environ:
                        os.environ[k] = v

_load_dotenv()

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Module 8 identity defaults to mock mode unless configured otherwise.
os.environ.setdefault("AGENT_MOCK_MODE", "true")

# ---------------------------------------------------------------------------
# Rich / plain-text output helpers (mirrors module7 pattern)
# ---------------------------------------------------------------------------

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich import box as rich_box
    _c = Console()

    def header(n: int, title: str) -> None:
        _c.print()
        _c.print(Panel(
            f"[bold white]Section {n}[/bold white]  [cyan]{title}[/cyan]",
            style="bold cyan",
            border_style="cyan",
            padding=(0, 2),
        ))

    def concept(text: str) -> None:
        _c.print()
        _c.print(Panel(
            f"[yellow]{text}[/yellow]",
            title="[bold yellow]Key Point[/bold yellow]",
            border_style="yellow",
            padding=(0, 1),
        ))
        _c.print()

    def user_says(text: str) -> None:
        _c.print(f"\n[bold bright_green]USER >[/bold bright_green] [italic white]{text}[/italic white]")

    def box(title: str, body: str) -> None:
        _c.print(Panel(
            f"[dim]{body}[/dim]",
            title=f"[bold cyan]{title}[/bold cyan]",
            border_style="bright_black",
            padding=(0, 1),
        ))

    def show(label: str, data) -> None:
        data = _redact(data)
        if isinstance(data, dict):
            t = Table(show_header=False, box=rich_box.SIMPLE, padding=(0, 1))
            t.add_column(style="green", no_wrap=True)
            t.add_column(style="white")
            for k, v in data.items():
                t.add_row(str(k), str(v))
            _c.print(f"[green]{label}[/green]")
            _c.print(t)
        elif isinstance(data, list):
            _c.print(f"[green]{label}:[/green]")
            for item in data:
                if isinstance(item, dict):
                    parts = "  ".join(f"[dim]{k}[/dim] [white]{v}[/white]" for k, v in item.items())
                    _c.print(f"  * {parts}")
                else:
                    _c.print(f"  * [white]{item}[/white]")
        else:
            _c.print(f"[green]{label}:[/green] [white]{data}[/white]")

    def show_json(label: str, data) -> None:
        _c.print(f"[green]{label}:[/green]")
        _c.print_json(json.dumps(_redact(data), default=str))

    def info(text: str) -> None:
        _c.print(f"  [bright_black]{_redact(text)}[/bright_black]")

    def stage(name: str, detail: str = "") -> None:
        _c.print(f"  [bold magenta]STAGE[/bold magenta]  [magenta]{name}[/magenta]  [dim]{detail}[/dim]")

    def act(tool: str, args: str = "") -> None:
        _c.print(f"  [bold magenta]ACT[/bold magenta]   [magenta]{tool}[/magenta][dim]({args})[/dim]")

    def observe(tool: str, result: str) -> None:
        _c.print(f"  [bold green]OBS[/bold green]   [dim]{tool} ->[/dim] [white]{result}[/white]")

    def agent_says(text: str) -> None:
        _c.print()
        _c.print(Panel(
            text,
            title="[bold cyan]DEVOPS COMPANION[/bold cyan]",
            border_style="cyan",
            padding=(0, 1),
        ))
        _c.print()

except ImportError:
    _c = None  # type: ignore[assignment]

    def header(n: int, title: str) -> None:
        print(f"\n{'='*62}\n  Section {n}: {title}\n{'='*62}")

    def concept(text: str) -> None:
        print(f"\nKey Point: {text}\n")

    def user_says(text: str) -> None:
        print(f"\nUSER > {text}")

    def box(title: str, body: str) -> None:
        print(f"\n[ {title} ]\n{body}")

    def show(label: str, data) -> None:
        data = _redact(data)
        if isinstance(data, (dict, list)):
            print(f"{label}:\n{json.dumps(data, indent=2, default=str)}")
        else:
            print(f"{label}: {data}")

    def show_json(label: str, data) -> None:
        data = _redact(data)
        print(f"{label}:\n{json.dumps(data, indent=2, default=str)}")

    def info(text: str) -> None:
        print(f"  {_redact(text)}")

    def stage(name: str, detail: str = "") -> None:
        print(f"  STAGE  {name}  {detail}")

    def act(tool: str, args: str = "") -> None:
        print(f"  ACT   {tool}({args})")

    def observe(tool: str, result: str) -> None:
        print(f"  OBS   {tool} -> {result}")

    def agent_says(text: str) -> None:
        print(f"\nDEVOPS COMPANION > {text}\n")


_NO_PAUSE = False      # set by --no-pause flag
_FRESH_TOPIC = False   # set by --fresh-topic flag
_REDACT_DATES = False  # set by --redact-dates flag

# Digit lookarounds rather than \b: in an ISO timestamp the date is followed
# by "T", and both "0" and "T" are word characters, so a trailing \b never
# matches there.
_DATE_RE = re.compile(r"(?<!\d)(?:19|20)\d{2}-\d{2}-\d{2}(?!\d)")


def _redact(value):
    """Replace calendar dates in displayed values with a visible placeholder.

    Used when recording a session that will stream later, so the output does
    not pin itself to a calendar day. Times of day are left alone: they carry
    no date information. This changes display only. The records themselves
    keep their real timestamps, which is why the substitution is an obvious
    placeholder rather than a plausible different date.
    """
    if not _REDACT_DATES:
        return value
    if isinstance(value, str):
        return _DATE_RE.sub("YYYY-MM-DD", value)
    if isinstance(value, dict):
        return {k: _redact(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_redact(v) for v in value]
    return value


def pause(msg: str | None = None) -> None:
    """Wait for the presenter to advance.

    Any lead-in text is shown above a consistent prompt, so every pause looks
    like a pause. Earlier versions let a custom message replace the prompt,
    which produced beats that appeared to hang.
    """
    if _NO_PAUSE:
        return
    prompt = "press Enter to continue"
    try:
        if _c is not None:
            if msg:
                _c.print(f"\n[bright_black]{msg}[/bright_black]")
                _c.print(f"[dim]  ({prompt})[/dim]")
            else:
                _c.print(f"\n[dim]  {prompt}...[/dim]")
            input()
        else:
            if msg:
                print(f"\n{msg}")
            input(f"  ({prompt}) ")
    except KeyboardInterrupt:
        sys.exit(0)


def _run_prep(reset: bool) -> None:
    """Prepare the environment and print a compact readout."""
    from module9.demo_prep import prepare_environment

    if _c is not None:
        _c.print("[bright_black]  Preparing demo environment...[/bright_black]")
    else:
        print("  Preparing demo environment...")

    if _REDACT_DATES:
        note = (
            "  Calendar dates in displayed output are shown as YYYY-MM-DD. "
            "Times of day and all stored records are unchanged."
        )
        if _c is not None:
            _c.print(f"[yellow]{note}[/yellow]")
        else:
            print(note)

    report = prepare_environment(reset=reset, fresh_topic=_FRESH_TOPIC)

    for step in report.steps:
        if not step.ok:
            label, style = "WARN", "yellow"
        elif step.degraded:
            label, style = "MOCK", "yellow"
        else:
            label, style = "OK", "green"
        if _c is not None:
            _c.print(f"    [{style}]{label:<4}[/{style}] "
                     f"[white]{step.name}[/white]  [dim]{step.detail}[/dim]")
        else:
            print(f"    {label:<4} {step.name}  {step.detail}")

    # Preparation seeds the corpora and waits for them to be retrievable, so
    # the sections do not need to.
    _STATE["seeded"] = True

    degraded = report.degraded_partners
    if degraded:
        msg = (f"  {', '.join(degraded)} unavailable, running that layer in "
               "mock mode. The demo flow is unchanged.")
        if _c is not None:
            _c.print(f"[yellow]{msg}[/yellow]")
        else:
            print(msg)
    print()


def _sink_label() -> str:
    """One-line description of the active knowledge sink, for display."""
    try:
        from module9.ingestion.kb_sink import (
            BACKEND_BEDROCK_KB,
            BACKEND_MODULE7,
            resolve_sink,
        )

        info = resolve_sink().info()
        if info.backend == BACKEND_BEDROCK_KB:
            return f"{info.display_name} [dim](no vector store to run)[/dim]"
        if info.backend == BACKEND_MODULE7:
            return f"{info.display_name} [dim](Module 7 semantic memory)[/dim]"
        return f"{info.display_name}"
    except Exception:
        return "resolved at run time"


def _full_mock() -> bool:
    """True when both partner and memory layers are mocked: the offline path."""
    return (
        os.getenv("AGENT_MOCK_PIPELINE", "").lower() == "true"
        and os.getenv("AGENT_MOCK_MEMORY", "").lower() == "true"
    )


# ---------------------------------------------------------------------------
# Cross-section state (sections stay standalone via the _ensure helpers)
# ---------------------------------------------------------------------------

_STATE: dict = {}


def _ensure_seeds() -> None:
    """Warm the three corpora with seed docs (idempotent).

    The preparation step normally does this, and waits for the chunks to be
    retrievable. This covers a single-section run started with --no-prep.
    """
    if _STATE.get("seeded"):
        return
    from module9.demo_prep import seed_corpora_and_wait

    seed_corpora_and_wait()
    _STATE["seeded"] = True
    info("Seed corpora loaded across the service, policy, and history corpora.")


def _ensure_event_produced() -> dict:
    """Produce the deployment event to the topic once; return the report."""
    if "produce_report" not in _STATE:
        from module9.producers.devops_event_producer import produce_event

        _STATE["produce_report"] = produce_event()
    return _STATE["produce_report"]


def _ensure_landed():
    """Consume and land the produced event once; returns (consumed, delta)."""
    if "landed" not in _STATE:
        from module9.config.settings import ConfluentSettings
        from module9.ingestion.delta_writer import land_event
        from module9.ingestion.stream_consumer import create_stream_source

        _ensure_event_produced()
        source = create_stream_source(ConfluentSettings())
        try:
            events = source.poll_events(max_records=1)
            if not events:
                info("No event waiting on the stream; producing one now.")
                from module9.producers.devops_event_producer import produce_event

                produce_event()
                events = source.poll_events(max_records=1)
        finally:
            # Release the partition assignment. A consumer left open stays a
            # live member of the group and starves the later sections that
            # consume under the same group id.
            source.close()
        consumed = events[0]
        delta = land_event(consumed)
        _STATE["landed"] = (consumed, delta)
    return _STATE["landed"]


def _newest_history_result(results: list[dict]) -> dict | None:
    """Pick the freshest retrieval result by ingested_at."""
    dated = [r for r in results if r.get("ingested_at")]
    if not dated:
        return results[0] if results else None
    return max(dated, key=lambda r: str(r.get("ingested_at")))


def _baseline_agent_answer(question: str) -> str:
    """The agent as it exists BEFORE Module 9: retrieval with no freshness
    instrumentation and no provenance.

    This is the Section 1 baseline, and it is deliberately not the governed
    agent. It retrieves from the knowledge base and answers, with no way to
    know the corpus is stale, which is exactly the quiet failure the module
    is about. Section 9 runs the governed agent for contrast.
    """
    from module9.config.models import get_chat_bedrock_model
    from module9.tools.pipeline_tools import governed_recall

    user_says(question)
    print()
    act("recall_semantic_memory", "corpus=history (no freshness check available)")
    recall = governed_recall(question, corpus="history", top_k=5, role="DeployObserve")
    results = recall.get("results", [])
    if not results:
        agent_says("(knowledge base returned nothing; run section 9 first)")
        return ""
    dated = [r for r in results if r.get("ingested_at")]
    top = min(dated, key=lambda r: str(r.get("ingested_at"))) if dated else results[0]
    observe("recall_semantic_memory", f"{len(results)} result(s) retrieved")

    model = get_chat_bedrock_model()
    response = model.invoke([
        (
            "system",
            "You are the DevOps Companion, an AWS infrastructure assistant. "
            "Answer the user's question using the knowledge base content "
            "provided. The content is the authoritative record. Answer "
            "directly and concisely in plain prose, 4 lines maximum. Use no "
            "markdown formatting: no asterisks, bold, headers, or bullets. "
            "Do not speculate about whether the content might be out of date.",
        ),
        (
            "user",
            f"Knowledge base content:\n{top['content']}\n\nQuestion: {question}",
        ),
    ])
    agent_says(response.content)
    return top["id"]


def _scripted_answer(
    question: str, prefer_fresh: bool, with_freshness_check: bool = True
) -> str | None:
    """Deterministic no-LLM agent path for the fully offline run.

    Retrieves as the DeployObserve role and composes the answer from the
    top result, so the ingest-to-answer loop runs with zero credentials.
    Returns the doc_id answered from.

    with_freshness_check=False models the naive agent of Section 1, which
    answers confidently without checking freshness (the quiet failure).
    """
    from module9.ingestion.freshness import check_freshness
    from module9.tools.pipeline_tools import governed_recall

    user_says(question)
    print()
    act("recall_semantic_memory", "corpus=history, role=DeployObserve")
    recall = governed_recall(question, corpus="history", top_k=5, role="DeployObserve")
    if recall["access"] != "granted" or not recall["results"]:
        agent_says(
            "The history corpus has no record I can answer that from, and I "
            "will not guess. Run the ingestion pipeline and ask again."
        )
        return None
    observe("recall_semantic_memory", f"{len(recall['results'])} result(s), filter={recall['filter']}")

    if prefer_fresh:
        top = _newest_history_result(recall["results"])
    else:
        dated = [r for r in recall["results"] if r.get("ingested_at")]
        top = min(dated, key=lambda r: str(r.get("ingested_at"))) if dated else recall["results"][0]

    answer = top["content"]
    if with_freshness_check:
        act("check_freshness", "corpus=history")
        verdict = check_freshness("history")
        observe("check_freshness", f"status={verdict['status']}")
        if verdict["status"] == "fresh":
            answer += (
                " (Answered from the history corpus, which is fresh: newest "
                f"chunk is {verdict['newest_chunk_age_hours']} hours old.)"
            )
        else:
            answer += (
                " (Caution: the history corpus is "
                f"{verdict['status']}, so this may not reflect the latest state.)"
            )
    agent_says(answer)
    return top["id"]


# ---------------------------------------------------------------------------
# Section 1: The Stale Agent Problem (beat B1)
# ---------------------------------------------------------------------------

def demo_stale_agent() -> None:
    box(
        "The Problem",
        "This is the DevOps Companion as it exists before Module 9: it can\n"
        "retrieve from its knowledge base, but it has no freshness signal and\n"
        "no provenance. Asked about the latest checkout-api deployment, it\n"
        "answers confidently from stale knowledge. Nothing in the retrieved\n"
        "content tells it, or us, that the answer is out of date.",
    )
    _ensure_seeds()
    pause()

    question = "What was the most recent checkout-api deployment to production?"

    if _full_mock():
        _scripted_answer(question, prefer_fresh=False, with_freshness_check=False)
    else:
        try:
            _baseline_agent_answer(question)
        except Exception as exc:
            info(f"(Live model unavailable: {exc})")
            _scripted_answer(
                question, prefer_fresh=False, with_freshness_check=False
            )

    from module9.ingestion.freshness import explain_staleness

    verdict = explain_staleness("history")
    show("Freshness check on the history corpus", {
        "status": verdict["status"],
        "newest_chunk_age_hours": verdict["newest_chunk_age_hours"],
        "sla_hours": verdict["sla_hours"],
    })
    info(verdict["explanation"])

    concept(
        "The agent cited the previous release because the newest record in "
        "its knowledge base predates today's deployment. This failure is "
        "quiet: retrieval succeeded, similarity scores looked healthy, and "
        "the answer was wrong. The fix is a pipeline that moves operational "
        "events into the knowledge base as they happen, with freshness "
        "monitoring that flags the gap. That is Module 9."
    )
    pause()


# ---------------------------------------------------------------------------
# Section 2: Act 1, Streaming with Confluent (beat B2)
# ---------------------------------------------------------------------------

def demo_confluent_stream() -> None:
    box(
        "Act 1: Confluent (Real-Time Stream Consumption)",
        "A production deployment event is produced to the Confluent Cloud\n"
        "Kafka topic devops-events and consumed live. This is the module's\n"
        "real-time stream pattern, and the managed-Kafka alternative to\n"
        "Amazon Kinesis: consumer groups track their own offsets, so\n"
        "several agents can read the same stream independently and replay\n"
        "history from any point.",
    )
    pause()

    from module9.config.settings import ConfluentSettings, is_mock_pipeline
    from module9.ingestion.stream_consumer import KafkaStreamSource

    report = _ensure_event_produced()
    mode = "mock (in-process topic)" if is_mock_pipeline() else "live (Confluent Cloud)"
    show("Produced event", {
        "mode": mode,
        "topic": report["topic"],
        "partition": report["partition"],
        "offset": report["offset"],
        "key": report["event"].get("service", ""),
    })
    show_json("Event payload", report["event"])

    pause("  Consume it live with a second consumer group...")

    # A fresh viewer group each run, so the ingestion group's offsets are
    # untouched and the replay is deterministic no matter how many events
    # the topic has accumulated across rehearsals. This is the
    # consumer-group independence beat.
    viewer_settings = ConfluentSettings()
    viewer_settings.group_id = f"module9-demo-viewer-{int(time.time())}"
    viewer = KafkaStreamSource(viewer_settings)
    events = viewer.poll_events(max_records=50)
    viewer.close()

    ours = next((e for e in events if e.offset == report["offset"]), None)
    info(f"Viewer consumer group replayed the topic from the beginning and "
         f"read {len(events)} event(s).")
    if ours is not None:
        info("The event we just produced:")
        info(f"  {ours.source_uri}")
        info(f"  service={ours.event.get('service', '?')}  "
             f"status={ours.event.get('status', '?')}  "
             f"version={ours.event.get('version', '?')}")
    else:
        info("(the produced event was not in the replay window; "
             "check the topic retention settings)")

    concept(
        "The (topic, partition, offset) triple is durable provenance: it "
        "pins this exact event forever, and it will ride on every chunk the "
        "pipeline produces from it. The viewer group read the event without "
        "disturbing the ingestion group's position, which is core to the "
        "Kafka consumer model: every reader tracks its own offsets and can "
        "replay from any point. Confluent adds Schema Registry on top, so "
        "producers using the registry cannot publish events that break the "
        "agreed contract."
    )
    pause()


# ---------------------------------------------------------------------------
# Section 3: Act 2, Landing in Delta Lake (beats B3, B5 table level)
# ---------------------------------------------------------------------------

def demo_delta_landing() -> None:
    box(
        "Act 2: Databricks (Land, Normalize, Govern)",
        "The consumer lands the raw event in the Delta Lake bronze table,\n"
        "then writes the normalized silver row. Unity Catalog captures the\n"
        "bronze-to-silver table lineage automatically as the data moves;\n"
        "nobody instruments anything.",
    )
    pause()

    from module9.config.settings import DatabricksSettings, is_mock_pipeline
    from module9.ingestion.delta_writer import create_lakehouse, normalize_event

    consumed, delta = _ensure_landed()
    settings = DatabricksSettings()

    stage("consume", f"offset {consumed.offset} from {consumed.topic}")
    stage("land bronze", f"{delta.bronze_table} now at Delta version {delta.bronze_version}")
    stage("normalize to silver", f"{delta.silver_table} now at Delta version {delta.silver_version}")

    show("Silver row (normalized)", normalize_event(consumed.event))

    pause("  Read the Unity Catalog lineage edge...")

    lakehouse = create_lakehouse(settings)
    lineage_records = lakehouse.table_lineage(settings.silver_full_name)
    mode = "mock" if is_mock_pipeline() else "live (system.access.table_lineage)"
    if lineage_records:
        show(f"Unity Catalog table lineage ({mode})", lineage_records[-3:])
    else:
        show(f"Unity Catalog table lineage ({mode})", {
            "status": "pending",
            "source_table": delta.bronze_table,
            "target_table": delta.silver_table,
            "target_delta_version": delta.silver_version,
        })
        info("Lineage system tables are populated in batch, so an edge written "
             "seconds ago is usually not queryable yet.")
        info("The graph is visible in near real time in Catalog Explorer: "
             f"Catalog > {settings.catalog} > {settings.silver_schema} > "
             f"{settings.silver_table} > Lineage.")

    concept(
        "Bronze holds the raw payload untouched; silver holds the "
        "normalized schema the chunker consumes. Every write increments the "
        "Delta table version, and that version number is the second "
        "provenance anchor. Unity Catalog recorded the bronze-to-silver "
        "edge automatically, so the knowledge base's source tables sit "
        "under the same governance model as the rest of the data estate."
    )
    pause()


# ---------------------------------------------------------------------------
# Section 4: The Lineage Metadata Schema (beat B4)
# ---------------------------------------------------------------------------

def demo_metadata_schema() -> None:
    box(
        "Metadata Enrichment: The Appendix B Lineage Schema",
        "The structured record becomes a natural-language chunk, and every\n"
        "chunk carries the full lineage schema: source identity, pipeline\n"
        "run, content hash, chunking parameters, embedding model, access\n"
        "stamps, plus the Confluent offset and Databricks Delta version.",
    )
    _ensure_seeds()
    pause()

    from module9.config.corpora import get_corpus
    from module9.ingestion.chunk import chunk_record
    from module9.ingestion.load import load_chunk
    from module9.ingestion.pipeline_run import new_run_id

    consumed, delta = _ensure_landed()
    spec = get_corpus("history")

    chunks = chunk_record("", "history", event=consumed.event)
    info(f"Chunking strategy for the history corpus: {spec.chunking_strategy} "
         f"(one record per chunk, Appendix A)")
    show("Rendered chunk (what gets embedded)", chunks[0].content)

    pause("  Load it and inspect the metadata that rides with it...")

    run_id = new_run_id()
    result = load_chunk(
        chunks[0],
        spec,
        pipeline_run_id=run_id,
        source_uri=consumed.source_uri,
        source_type="structured-record",
        source_modified=consumed.event_time,
        consumed=consumed,
        delta=delta,
    )
    _STATE["loaded_doc_id"] = result.doc_id

    # The pipeline also records the lineage edges here, exactly as
    # run_pipeline does, so Section 7 can show the graph.
    from module9.ingestion.lineage import ensure_lineage_graph

    ensure_lineage_graph(
        f"confluent://{consumed.topic}",
        delta.silver_table,
        "history",
        delta_version=delta.silver_version,
        unity_catalog_lineage_id=delta.unity_catalog_lineage_id,
        pipeline_run_id=run_id,
        access_level=spec.access_level,
    )

    if result.action == "stored":
        from module9.ingestion.kb_sink import resolve_sink

        show(
            f"Loaded into the knowledge base "
            f"({resolve_sink().info().display_name})",
            f"doc_id={result.doc_id} (corpus=history, memory_type=consolidated)",
        )
        show_json("Chunk metadata (every Appendix B field populated)", result.metadata)
    else:
        info(f"Chunk already loaded in this session ({result.action}); "
             f"doc_id={result.doc_id}")
        from module9.ingestion.lineage import get_registry
        show_json("Chunk metadata (every Appendix B field populated)",
                  get_registry().chunks.get(result.doc_id, {}))

    concept(
        "Metadata is what makes the difference between a searchable text "
        "blob and governed knowledge. The content hash powers dedup and "
        "incremental refresh, access_level and allowed_agent_roles power "
        "row-level security, and the Kafka offset plus Delta version make "
        "every answer traceable to its exact origin."
    )
    pause()


# ---------------------------------------------------------------------------
# Section 5: Data Quality Gates (beat B6)
# ---------------------------------------------------------------------------

def demo_quality_gates() -> None:
    box(
        "Data Quality Gates",
        "Quality has to be engineered into the pipeline, not discovered\n"
        "later through agent evaluation. Before anything is embedded, four\n"
        "gates run: non-empty, 50-token minimum, structural validation, and\n"
        "dedup by SHA-256 content hash. Now we push a bad record through\n"
        "and watch it get rejected.",
    )
    pause()

    from module9.ingestion.chunk import chunk_record, render_history_record
    from module9.ingestion.quality import get_dedup_index, run_quality_gates
    from module9.mock.sample_events import bad_event, deployment_event

    bad = bad_event()
    show_json("A malformed event arrives", bad)
    rendered = render_history_record(bad)
    show("Rendered chunk", rendered)

    report = run_quality_gates(rendered, get_dedup_index())
    show(f"Quality verdict is {report.verdict.upper()}, gate by gate", [
        {"check": c["check"], "passed": c["passed"], "detail": c["detail"]}
        for c in report.checks
    ])
    info("Rejected before embedding: no tokens spent, no noise in retrieval.")

    pause("  Now the duplicate case: the same good record, twice...")

    good = render_history_record(deployment_event())
    chunk = chunk_record("", "history", event=deployment_event())[0]
    first = run_quality_gates(chunk.content, get_dedup_index())
    if first.verdict == "pass":
        get_dedup_index().record(first.content_hash, "kb-his-demo")
    second = run_quality_gates(good, get_dedup_index())
    show("Second arrival of identical content", {
        "verdict": second.verdict,
        "content_hash": second.content_hash[:26] + "...",
        "detail": second.checks[-1]["detail"],
    })

    concept(
        "Duplicates hurt retrieval twice: near-identical chunks crowd the "
        "top-k results, and they waste embedding spend. The content hash "
        "comparison is also the incremental refresh mechanism: unchanged "
        "records are skipped, only changed ones are re-embedded. On the "
        "live path, Databricks Delta Live Tables expectations enforce "
        "schema and null checks at the lakehouse layer as well."
    )
    pause()


# ---------------------------------------------------------------------------
# Section 6: Freshness Strategies (beat B7)
# ---------------------------------------------------------------------------

def demo_freshness() -> None:
    box(
        "Three Freshness Strategies, Three Corpora",
        "Each corpus refreshes on the cadence its content demands:\n"
        "  service  ->  scheduled weekly full refresh + hash-based skip\n"
        "  policy   ->  event-driven refresh, under 10 minutes of lag\n"
        "  history  ->  streaming ingest + nightly consolidation sync\n"
        "A freshness SLA per corpus turns 'probably current' into a\n"
        "measured, alarmed property.",
    )
    _ensure_seeds()
    pause()

    from module9.ingestion.freshness import check_all_corpora, explain_staleness

    verdicts = check_all_corpora()
    show("Cross-corpus freshness dashboard", [
        {
            "corpus": v["corpus"],
            "status": v["status"].upper(),
            "age_hours": v["newest_chunk_age_hours"],
            "sla_hours": v["sla_hours"],
            "chunks": v["chunk_count"],
        }
        for v in verdicts
    ])

    verdict = explain_staleness("history")
    info(verdict["explanation"])

    concept(
        "Freshness is a property you monitor, not a property you assume. "
        "The verdict compares the newest chunk's age against the corpus "
        "SLA; in production the same check feeds a CloudWatch alarm so a "
        "silently failed Sunday job pages someone before the agent starts "
        "citing last month's state."
    )
    pause()


# ---------------------------------------------------------------------------
# Section 7: Lineage, Why Did the Agent Say This? (beat B5)
# ---------------------------------------------------------------------------

def demo_lineage() -> None:
    box(
        "Lineage from Source to Response",
        "Two lineage layers answer 'why did the agent say this?':\n"
        "  1. Unity Catalog: table-level lineage in the lakehouse\n"
        "  2. The Neo4j graph: Source -> Dataset -> Corpus -> Agent,\n"
        "     living in the same graph store as Module 7's relationship\n"
        "     memory, joined to chunk metadata at query time.",
    )
    _ensure_seeds()
    pause()

    from module9.ingestion.lineage import get_lineage, get_provenance

    # Make sure at least one streamed chunk exists to trace.
    if "loaded_doc_id" not in _STATE:
        demo_metadata_prereq()

    lineage = get_lineage("history")
    if not lineage["graph_edges"]:
        # Standalone run of this section: stream one chunk through so there is
        # a graph to show.
        demo_metadata_prereq()
        lineage = get_lineage("history")
    show("Lineage graph edges written to the graph store", [
        {"edge": f"{e['source']} -[{e['relationship']}]-> {e['target']}"}
        for e in lineage["graph_edges"]
    ] or ["(no edges recorded)"])
    show("History corpus", {
        "chunk_count": lineage["chunk_count"],
        "doc_ids": ", ".join(d[:24] + "..." for d in lineage["doc_ids"][:3]),
    })

    doc_id = _STATE.get("loaded_doc_id") or (lineage["doc_ids"][-1] if lineage["doc_ids"] else None)
    if doc_id:
        pause("  Trace one document all the way back...")
        prov = get_provenance(doc_id)
        show("Provenance graph path", " ".join(str(p) for p in prov["graph_path"]))
        show_json("Full provenance chain", {
            "source": prov["source"],
            "confluent": prov["confluent"],
            "databricks": prov["databricks"],
            "pipeline": prov["pipeline"],
        })

    concept(
        "This is the compliance query from the module's data lineage "
        "section: given an answer, find the exact source that produced it. "
        "The chain runs "
        "answer -> chunk -> corpus -> Delta table version -> Kafka offset. "
        "On AWS-native stacks the same query runs as SQL over Glue Data "
        "Catalog and Athena; Databricks Unity Catalog gives it to you as a "
        "governance-platform feature spanning the whole data estate."
    )
    pause()


def demo_metadata_prereq() -> None:
    """Quietly stream one chunk through for standalone section runs."""
    from module9.config.corpora import get_corpus
    from module9.ingestion.chunk import chunk_record
    from module9.ingestion.load import load_chunk
    from module9.ingestion.pipeline_run import new_run_id

    consumed, delta = _ensure_landed()
    chunks = chunk_record("", "history", event=consumed.event)
    result = load_chunk(
        chunks[0],
        get_corpus("history"),
        pipeline_run_id=new_run_id(),
        source_uri=consumed.source_uri,
        source_type="structured-record",
        source_modified=consumed.event_time,
        consumed=consumed,
        delta=delta,
    )
    if result.doc_id:
        _STATE["loaded_doc_id"] = result.doc_id


# ---------------------------------------------------------------------------
# Section 8: Access Control (beat B8, the Module 8 seam)
# ---------------------------------------------------------------------------

def demo_access_control() -> None:
    box(
        "Access Control at Ingestion and Retrieval",
        "Write path: every chunk passes the Module 7 PII guardrail and is\n"
        "stamped with access_level, allowed_agent_roles, and agent_scope.\n"
        "Read path: Module 8 authorizes the agent role at the boundary,\n"
        "then the role-compiled filter is applied server side by the\n"
        "knowledge base, before results come back. Two identities, two\n"
        "layers, no honor system.",
    )
    _ensure_seeds()
    pause()

    from module9.identity import (
        Auth0Error,
        PIPELINE_WRITE_POLICY,
        authorize_pipeline_write,
        authorize_retrieval,
        compile_retrieval_filter,
    )
    from module9.ingestion.chunk import render_history_record
    from module9.mock.sample_events import pii_deployment_event
    from module9.tools.pipeline_tools import governed_recall

    try:
        from module7.memory.guardrails import anonymize_pii
    except ImportError:
        from module9.mock.module7_contract import anonymize_pii

    info("Write path: the pipeline identity, not the agent identity")
    decision = authorize_pipeline_write("history")
    show("Pipeline write authorization (Module 8)", {
        "identity": decision.a2a_principal,
        "iam_role": decision.iam_role_arn,
        "scope": ", ".join(sorted(decision.effective_scopes)),
        "downstream": PIPELINE_WRITE_POLICY.downstream_access,
    })

    pause("  A record with PII arrives on the stream...")

    event = pii_deployment_event()
    rendered = render_history_record(event)
    show("Before the write-path guardrail", rendered)
    show("After anonymize_pii", anonymize_pii(rendered))

    pause("  Now the read path: two roles, same query...")

    ok = authorize_retrieval("DeployObserve", "history")
    show("DeployObserve requests the history corpus", {
        "decision": "ALLOW",
        "effective_scopes": ", ".join(sorted(ok.effective_scopes)),
        "compiled filter_dict": compile_retrieval_filter(ok, "history"),
    })
    granted = governed_recall("checkout-api deployment", corpus="history",
                              role="DeployObserve")
    info(f"Retrieval returned {len(granted['results'])} chunk(s), each stamped "
         f"access_level=internal, agent_scope=operations")

    try:
        authorize_retrieval("RepositoryAnalysis", "history")
        info("(unexpected: authorization should have been denied)")
    except Auth0Error as exc:
        show("RepositoryAnalysis requests the history corpus", {
            "decision": "DENY (Auth0Error raised at the agent boundary)",
            "reason": str(exc),
        })
    denied = governed_recall("checkout-api deployment", corpus="history",
                             role="RepositoryAnalysis")
    info(f"governed_recall as RepositoryAnalysis: access={denied['access']}, "
         f"results={len(denied['results'])}")

    concept(
        "The metadata filter is row-level security: it is evaluated by the "
        "knowledge base itself, before results are returned, so unauthorized "
        "chunks never reach the agent's context window, even if the agent's "
        "reasoning has been manipulated. Module 8 supplies the identity "
        "layer: the pipeline writes under a write-scoped principal, each "
        "agent role reads under a scoped policy, and every decision leaves "
        "an audit fingerprint. AgentCore Identity is the AWS-native home "
        "for this pattern as it productionizes."
    )
    pause()


# ---------------------------------------------------------------------------
# Section 9: Full Loop (beat B9)
# ---------------------------------------------------------------------------

def demo_full_loop() -> None:
    box(
        "The Full Loop: Kafka Offset to Governed Answer",
        "A new release ships while we are talking. The whole pipeline runs:\n"
        "produce -> consume -> Delta -> chunk -> gates -> embed -> load.\n"
        "Then we ask the same question from Section 1 and the DevOps\n"
        "Companion answers from the freshly ingested fact, tracing it back\n"
        "to the exact Kafka offset and Delta table version.",
    )
    _ensure_seeds()
    pause()

    from module9.ingestion.lineage import get_provenance
    from module9.ingestion.pipeline_run import run_pipeline
    from module9.mock.sample_events import followup_deployment_event
    from module9.producers.devops_event_producer import produce_event

    # A distinct, later release, so this is genuinely new knowledge rather
    # than a content-hash duplicate of the event used in sections 2 to 4.
    event = followup_deployment_event()
    report = produce_event(event)
    info(f"A new release just shipped: {event['service']} {event['version']}")
    info(f"Produced to {report['topic']} offset {report['offset']}")

    result = run_pipeline(corpus="history", max_events=10)
    show("Pipeline run", result.summary())
    if result.doc_ids:
        _STATE["loaded_doc_id"] = result.doc_ids[-1]

    pause("  Re-ask the question from Section 1...")

    question = "What was the most recent checkout-api deployment to production?"
    doc_id = None

    if _full_mock():
        doc_id = _scripted_answer(question, prefer_fresh=True)
    else:
        try:
            from module9.agent import create_pipeline_agent

            agent, sid = create_pipeline_agent(verbose=True)
            user_says(question)
            invoke_result = agent.invoke(
                {"messages": [("user", question)]},
                config={"configurable": {"thread_id": sid}},
            )
            msgs = invoke_result.get("messages", [])
            agent_says(msgs[-1].content if msgs else "(no response)")
            doc_id = _STATE.get("loaded_doc_id")
        except Exception as exc:
            info(f"(Live agent unavailable: {exc})")
            doc_id = _scripted_answer(question, prefer_fresh=True)

    doc_id = doc_id or _STATE.get("loaded_doc_id")
    if doc_id:
        pause("  And prove where that answer came from...")
        act("get_provenance", f"doc_id={doc_id[:28]}...")
        prov = get_provenance(doc_id)
        show("Provenance", {
            "graph": " ".join(str(p) for p in prov["graph_path"]),
            "kafka": f"{prov['confluent']['kafka_topic']} offset "
                     f"{prov['confluent']['kafka_offset']}",
            "delta": f"{prov['databricks']['delta_table']} version "
                     f"{prov['databricks']['delta_version']}",
            "unity_catalog": prov["databricks"]["unity_catalog_lineage_id"],
            "pipeline_run": prov["pipeline"]["pipeline_run_id"],
            "content_hash": str(prov["pipeline"]["content_hash"])[:30] + "...",
        })

    concept(
        "An agent is only as trustworthy as the pipeline behind it. Stream "
        "the event with Confluent, govern and embed it with Databricks, "
        "load it with lineage into the Module 7 knowledge base, and every "
        "answer the agent gives can be traced back to the exact source it "
        "came from. That trace is what turns 'the model said so' into an "
        "auditable system."
    )
    pause()


# ---------------------------------------------------------------------------
# Section registry and entry point
# ---------------------------------------------------------------------------

SECTIONS: dict[int, tuple[str, Callable[[], None]]] = {
    1: ("The Stale Agent Problem",                            demo_stale_agent),
    2: ("Act 1: Streaming the Event with Confluent",          demo_confluent_stream),
    3: ("Act 2: Landing in Delta Lake (Unity Catalog)",       demo_delta_landing),
    4: ("The Lineage Metadata Schema (Appendix B)",           demo_metadata_schema),
    5: ("Data Quality Gates",                                 demo_quality_gates),
    6: ("Freshness Strategies and SLAs",                      demo_freshness),
    7: ("Lineage: Why Did the Agent Say This?",               demo_lineage),
    8: ("Access Control at Ingestion and Retrieval",          demo_access_control),
    9: ("Full Loop: Kafka Offset to Governed Answer",         demo_full_loop),
}


def main() -> None:
    global _NO_PAUSE, _FRESH_TOPIC, _REDACT_DATES

    parser = argparse.ArgumentParser(
        description="Module 9: Data Pipelines and Lineage demo (9 sections)"
    )
    parser.add_argument("--section", type=int, metavar="N",
                        help="Run a specific section (1-9). Omit to run all.")
    parser.add_argument("--no-pause", action="store_true",
                        help="Skip all pause() prompts (useful for review/CI).")
    parser.add_argument("--mock", action="store_true",
                        help="Force mock mode: AGENT_MOCK_PIPELINE=true and "
                             "AGENT_MOCK_MEMORY=true. No credentials required.")
    parser.add_argument("--live", action="store_true",
                        help="Force live mode. Requires Confluent, Databricks, "
                             "Atlas/Neo4j, and Amazon Bedrock credentials in .env.")
    parser.add_argument("--no-prep", action="store_true",
                        help="Skip the automatic environment preparation step.")
    parser.add_argument("--no-reset", action="store_true",
                        help="Prepare the environment but leave partner state "
                             "as is: do not skip the topic backlog and do not "
                             "truncate the demo Delta tables.")
    parser.add_argument("--fresh-topic", action="store_true",
                        help="Delete and recreate the Kafka topic so offsets "
                             "restart at 0. Destructive and slower; use before "
                             "a final recording.")
    parser.add_argument("--redact-dates", action="store_true",
                        help="Show calendar dates in displayed output as the "
                             "placeholder YYYY-MM-DD, so a recording does not "
                             "pin itself to a day. Times of day are kept, and "
                             "the stored records are unchanged.")
    args = parser.parse_args()

    if args.no_pause:
        _NO_PAUSE = True
    if args.fresh_topic:
        _FRESH_TOPIC = True
    if args.redact_dates:
        _REDACT_DATES = True

    if args.mock:
        os.environ["AGENT_MOCK_PIPELINE"] = "true"
        os.environ["AGENT_MOCK_MEMORY"] = "true"
        # --mock means no network at all, so ignore a configured knowledge
        # base even when .env points at one.
        os.environ.pop("BEDROCK_KB_ID", None)
        os.environ.pop("BEDROCK_KB_DATA_SOURCE_ID", None)
    elif args.live:
        os.environ.pop("AGENT_MOCK_PIPELINE", None)
        os.environ.pop("AGENT_MOCK_MEMORY", None)

    # Prepare the environment so every run opens identically. A full run
    # resets partner state by default; a single-section run only health checks
    # and warms, so it does not disturb state you may be inspecting.
    if not args.no_prep:
        _run_prep(reset=(args.section is None and not args.no_reset))

    if args.section is not None:
        if args.section not in SECTIONS:
            print(f"Error: --section must be 1-9, got {args.section}", file=sys.stderr)
            sys.exit(1)
        title, fn = SECTIONS[args.section]
        header(args.section, title)
        fn()
    else:
        if _c is not None:
            _c.print(Panel(
                "[bold white]Module 9: Data Pipelines and Lineage[/bold white]\n\n"
                "[cyan]9 sections  |  ~22 minutes  |  press Enter to advance each beat[/cyan]\n\n"
                "  [bold]Confluent Cloud[/bold]   [dim]->[/dim] Act 1: real-time event streaming [dim](managed Kafka)[/dim]\n"
                "  [bold]Databricks[/bold]        [dim]->[/dim] Act 2: Delta Lake + Unity Catalog lineage\n"
                f"  [bold]Knowledge base[/bold]   [dim]->[/dim] {_sink_label()}\n"
                "  [bold]Lineage graph[/bold]    [dim]->[/dim] Source to Dataset to Corpus to Agent "
                "[dim](Module 7 graph store)[/dim]\n"
                "  [bold]Amazon Bedrock[/bold]    [dim]->[/dim] Claude Sonnet 4.6 [dim](the agent's reasoning)[/dim]\n\n"
                "[dim]Run a single section: python demos/module9_demo.py --section N[/dim]\n"
                "[dim]Fully offline:        python demos/module9_demo.py --mock[/dim]",
                border_style="cyan",
                padding=(1, 2),
            ))
        else:
            print("\n" + "=" * 62)
            print("  Module 9: Data Pipelines and Lineage")
            print("  9 sections | ~22 minutes | press Enter to advance")
            print("=" * 62)

        pause()

        for num, (title, fn) in SECTIONS.items():
            header(num, title)
            fn()
            print()

        if _c is not None:
            _c.rule("[bold green]Demo Complete[/bold green]", style="green")
        else:
            print("\n" + "=" * 62 + "\n  Demo Complete\n" + "=" * 62)


if __name__ == "__main__":
    main()
