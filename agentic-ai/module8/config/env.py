from __future__ import annotations

from pathlib import Path


def load_agentic_env() -> None:
    """Load agentic-ai/.env when python-dotenv is installed."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        return

    root = Path(__file__).resolve().parents[2]
    load_dotenv(root / ".env")
