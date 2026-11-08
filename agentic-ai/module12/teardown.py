"""Print a safe, reviewable teardown plan for Module 12.

This command intentionally plans but does not delete resources. The stack
contains versioned evidence and secrets, so deletion remains an explicit
operator action after the printed inventory has been reviewed.

Usage:
    python -m module12.teardown --stack module12-demo --dry-run
"""
from __future__ import annotations

import argparse


def plan(stack: str, *, state_backend: str | None = None) -> list[str]:
    backend_note = state_backend or "the configured Pulumi backend"
    return [
        f"Review Pulumi resources in stack {stack!r} with `pulumi stack --show-urns`.",
        "Confirm no AgentCore, tool, or telemetry resources are using this foundation.",
        "Export or retain any required evidence objects before removing the stack.",
        "Remove the Pulumi stack resources with `pulumi destroy --stack "
        f"{stack} --yes` after review; the S3 bucket is protected by force_destroy=false.",
        "If the evidence bucket must be removed, empty all object versions and delete it "
        "manually after a second review.",
        f"Delete the optional Pulumi state bucket only after all stacks using {backend_note} are gone.",
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--stack", default="module12-demo")
    parser.add_argument("--state-backend")
    parser.add_argument("--dry-run", action="store_true", help="print the plan and delete nothing")
    args = parser.parse_args(argv)
    if not args.dry_run:
        parser.error("Teardown is plan-only; pass --dry-run")
    print(f"Module 12 teardown plan for stack {args.stack} (nothing will be deleted)")
    for index, item in enumerate(plan(args.stack, state_backend=args.state_backend), 1):
        print(f"{index}. {item}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
