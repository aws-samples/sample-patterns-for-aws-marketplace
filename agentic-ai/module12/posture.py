"""Deterministic Snyk-shaped posture and quarantine contracts."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


POSTURE_SUBJECT = "companion-tools"
EVENT_SOURCE = "module12.snyk"
FINDING_EVENT_TYPE = "SnykFinding"
RECOVERY_EVENT_TYPE = "SnykPostureRecovered"
QUARANTINE_SEVERITIES = frozenset({"high", "critical"})
SNYK_CLI_VERSION = "1.1308.3"
SNYK_MONITOR_PROJECT_NAME = "DevOps Companion Tool Supply Chain"
SNYK_MONITOR_TARGET_REFERENCE = "module12-demo"
SEVERITY_RANK = {
    "none": 0,
    "low": 1,
    "medium": 2,
    "high": 3,
    "critical": 4,
}
RECORDED_SNYK_REPORT = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "snyk_vulnerable_package_report.json"
)


@dataclass(frozen=True)
class PostureEvent:
    subject: str
    posture: str
    posture_field: str
    reason: str
    tool_digest: str
    reviewed_tool_digest: str
    scan_digest: str
    finding_id: str | None = None
    severity: str | None = None

    def to_detail(self) -> dict[str, Any]:
        detail = {
            "subject": self.subject,
            "posture": self.posture,
            "posture_field": self.posture_field,
            "reason": self.reason,
            "tool_digest": self.tool_digest,
            "reviewed_tool_digest": self.reviewed_tool_digest,
            "scan_digest": self.scan_digest,
        }
        if self.finding_id:
            detail["finding_id"] = self.finding_id
        if self.severity:
            detail["severity"] = self.severity
        return detail


def canonical_digest(value: Any) -> str:
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def scan_digest(
    *,
    subject: str,
    repository_digest: str,
    tool_digest: str,
    reviewed_tool_digest: str,
) -> str:
    return canonical_digest(
        {
            "subject": subject,
            "repository_digest": repository_digest,
            "tool_digest": tool_digest,
            "reviewed_tool_digest": reviewed_tool_digest,
        }
    )


def load_recorded_snyk_report(
    path: str | Path = RECORDED_SNYK_REPORT,
) -> dict[str, Any]:
    """Load the checked-in Snyk CLI-shaped report used by the offline demo."""

    report = json.loads(Path(path).read_text())
    if not isinstance(report, dict):
        raise ValueError("the recorded Snyk report must be a JSON object")
    return report


def _version_key(value: str) -> tuple[int, ...]:
    return tuple(int(part) for part in re.findall(r"\d+", value))


def _highest_fixed_version(finding: Mapping[str, Any]) -> str:
    fixed_versions = finding.get("fixedIn", [])
    if not isinstance(fixed_versions, list):
        return ""
    normalized = [str(version) for version in fixed_versions]
    return max(normalized, key=_version_key, default="")


def normalize_snyk_report(report: Any) -> dict[str, Any]:
    """Extract a deterministic posture summary from Snyk JSON."""

    reports = report if isinstance(report, list) else [report]
    vulnerabilities: list[Mapping[str, Any]] = []
    dependency_count = 0
    project_name = ""
    target_file = ""
    package_manager = ""
    for candidate in reports:
        if not isinstance(candidate, Mapping):
            continue
        if not project_name:
            project_name = str(candidate.get("projectName", ""))
        if not target_file:
            target_file = str(candidate.get("targetFile", ""))
        if not package_manager:
            package_manager = str(candidate.get("packageManager", ""))
        try:
            dependency_count += int(candidate.get("dependencyCount", 0))
        except (TypeError, ValueError):
            pass
        candidate_vulnerabilities = candidate.get("vulnerabilities", [])
        if isinstance(candidate_vulnerabilities, list):
            vulnerabilities.extend(
                item
                for item in candidate_vulnerabilities
                if isinstance(item, Mapping)
            )

    ranked = sorted(
        vulnerabilities,
        key=lambda item: (
            SEVERITY_RANK.get(str(item.get("severity", "")).casefold(), 0),
            _version_key(_highest_fixed_version(item)),
            str(item.get("id", "")),
        ),
        reverse=True,
    )
    primary = ranked[0] if ranked else {}
    severity = str(primary.get("severity", "none")).casefold()
    fixed_versions = primary.get("fixedIn", [])
    if not isinstance(fixed_versions, list):
        fixed_versions = []
    dependency_path = primary.get("from", [])
    if not isinstance(dependency_path, list):
        dependency_path = []
    package_name = str(
        primary.get("packageName")
        or primary.get("package")
        or "unknown-package"
    )
    package_version = str(primary.get("version", ""))
    severity_counts = Counter(
        str(item.get("severity", "unknown")).casefold()
        for item in vulnerabilities
    )
    recommended_upgrade = max(
        (
            version
            for item in vulnerabilities
            for version in [_highest_fixed_version(item)]
            if version
        ),
        key=_version_key,
        default="",
    )
    return {
        "project_name": project_name,
        "target_file": target_file,
        "package_manager": package_manager,
        "dependency_count": dependency_count,
        "issue_count": len(vulnerabilities),
        "finding_id": str(primary.get("id", "SNYK-SCAN-CLEAN")),
        "title": str(primary.get("title", "No actionable vulnerabilities")),
        "severity": severity,
        "package_name": package_name,
        "package_version": package_version,
        "dependency_path": " > ".join(str(item) for item in dependency_path),
        "fixed_in": str(fixed_versions[0]) if fixed_versions else "",
        "recommended_upgrade": recommended_upgrade,
        "severity_counts": dict(sorted(severity_counts.items())),
        "quarantine_required": severity in QUARANTINE_SEVERITIES,
        "source_scan_digest": canonical_digest(report),
    }


def build_finding_event(
    *,
    subject: str = POSTURE_SUBJECT,
    repository_digest: str = "sha256:repository",
    tool_digest: str = "sha256:tool-observed",
    reviewed_tool_digest: str = "sha256:tool-reviewed",
    finding_id: str = "SNYK-MODULE12-001",
    severity: str = "high",
    package_name: str = "module12-companion-tools",
    package_version: str = "",
    title: str = "",
    dependency_path: str = "",
    fixed_in: str = "",
    recommended_upgrade: str = "",
    severity_counts: Mapping[str, int] | None = None,
    issue_count: int = 1,
    source_scan_digest: str = "",
) -> dict[str, Any]:
    """Build normalized finding evidence and the trusted quarantine transition."""

    normalized_severity = severity.casefold()
    quarantined = normalized_severity in QUARANTINE_SEVERITIES
    digest = scan_digest(
        subject=subject,
        repository_digest=repository_digest,
        tool_digest=tool_digest,
        reviewed_tool_digest=reviewed_tool_digest,
    )
    posture_event = PostureEvent(
        subject=subject,
        posture="quarantine" if quarantined else "healthy",
        posture_field="snyk_posture",
        reason=(
            "high_or_critical_snyk_finding"
            if quarantined
            else "finding_below_quarantine_threshold"
        ),
        tool_digest=tool_digest,
        reviewed_tool_digest=reviewed_tool_digest,
        scan_digest=digest,
        finding_id=finding_id,
        severity=normalized_severity,
    )
    finding = {
        "finding_id": finding_id,
        "severity": normalized_severity,
        "subject": subject,
        "package": package_name,
        "package_version": package_version,
        "title": title,
        "dependency_path": dependency_path,
        "fixed_in": fixed_in,
        "recommended_upgrade": recommended_upgrade,
        "severity_counts": dict(severity_counts or {}),
        "issue_count": issue_count,
        "source_scan_digest": source_scan_digest,
        "tool_digest": tool_digest,
        "reviewed_tool_digest": reviewed_tool_digest,
        "scan_digest": digest,
        "posture": "quarantine" if quarantined else "healthy",
    }
    return {
        "event_source": EVENT_SOURCE,
        "detail_type": FINDING_EVENT_TYPE,
        "finding": finding,
        "posture": posture_event.to_detail(),
    }


def build_finding_event_from_snyk_report(
    report: Any,
    *,
    subject: str = POSTURE_SUBJECT,
    tool_digest: str = "sha256:tool-observed",
    reviewed_tool_digest: str = "sha256:tool-reviewed",
) -> dict[str, Any]:
    """Turn Snyk CLI JSON into the trusted quarantine contract."""

    finding = normalize_snyk_report(report)
    return build_finding_event(
        subject=subject,
        repository_digest=finding["source_scan_digest"],
        tool_digest=tool_digest,
        reviewed_tool_digest=reviewed_tool_digest,
        finding_id=finding["finding_id"],
        severity=finding["severity"],
        package_name=finding["package_name"],
        package_version=finding["package_version"],
        title=finding["title"],
        dependency_path=finding["dependency_path"],
        fixed_in=finding["fixed_in"],
        recommended_upgrade=finding["recommended_upgrade"],
        severity_counts=finding["severity_counts"],
        issue_count=finding["issue_count"],
        source_scan_digest=finding["source_scan_digest"],
    )


def build_recovery_event(
    *,
    subject: str = POSTURE_SUBJECT,
    repository_digest: str = "sha256:repository",
    tool_digest: str,
    reviewed_tool_digest: str,
) -> dict[str, Any]:
    """Build a recovery transition only when the reviewed digest matches."""

    digest = scan_digest(
        subject=subject,
        repository_digest=repository_digest,
        tool_digest=tool_digest,
        reviewed_tool_digest=reviewed_tool_digest,
    )
    matches = tool_digest == reviewed_tool_digest
    posture_event = PostureEvent(
        subject=subject,
        posture="healthy" if matches else "quarantine",
        posture_field="snyk_posture",
        reason="reviewed_tool_digest_match"
        if matches
        else "tool_digest_mismatch_during_recovery",
        tool_digest=tool_digest,
        reviewed_tool_digest=reviewed_tool_digest,
        scan_digest=digest,
        finding_id=None,
        severity=None,
    )
    return {
        "event_source": EVENT_SOURCE,
        "detail_type": RECOVERY_EVENT_TYPE,
        "posture": posture_event.to_detail(),
    }


def posture_from_detail(detail: Mapping[str, Any]) -> PostureEvent:
    """Normalize an event detail into a trusted posture transition."""

    posture = str(detail.get("posture", "quarantine"))
    if posture not in {"healthy", "quarantine"}:
        posture = "quarantine"
    return PostureEvent(
        subject=str(detail.get("subject", POSTURE_SUBJECT)),
        posture=posture,
        posture_field=str(detail.get("posture_field", "snyk_posture")),
        reason=str(detail.get("reason", "unspecified_posture_transition")),
        tool_digest=str(detail.get("tool_digest", "")),
        reviewed_tool_digest=str(detail.get("reviewed_tool_digest", "")),
        scan_digest=str(detail.get("scan_digest", "")),
        finding_id=detail.get("finding_id"),
        severity=detail.get("severity"),
    )


LIVE_SCAN_BUILDSPEC = f"""version: 0.2
phases:
  install:
    commands:
      - npm install --global snyk@{SNYK_CLI_VERSION}
      - python3 -m pip install --disable-pip-version-check --no-input boto3==1.43.108
  build:
    commands:
      - snyk --version
      - 'snyk test --file=module12/fixtures/vulnerable_companion_tool/package-lock.json --package-manager=npm --json-file-output=/tmp/snyk.json || [ "$?" -eq 1 ]'
      - 'snyk monitor --file=module12/fixtures/vulnerable_companion_tool/package-lock.json --package-manager=npm --project-name="{SNYK_MONITOR_PROJECT_NAME}" --target-reference={SNYK_MONITOR_TARGET_REFERENCE}'
      - python3 -m module12.posture_handler --action publish-live --input /tmp/snyk.json
"""


def live_scan_plan() -> dict[str, Any]:
    """Describe the deployed CodeBuild/Snyk CLI scan."""

    return {
        "enabled_by_default": True,
        "required_secret": "m12-module12-demo/snyk",
        "snyk_cli_version": SNYK_CLI_VERSION,
        "required_command": (
            "snyk test "
            "--file=module12/fixtures/vulnerable_companion_tool/package-lock.json "
            "--package-manager=npm --json-file-output=/tmp/snyk.json"
        ),
        "monitor_command": (
            "snyk monitor "
            "--file=module12/fixtures/vulnerable_companion_tool/package-lock.json "
            f'--package-manager=npm --project-name="{SNYK_MONITOR_PROJECT_NAME}" '
            f"--target-reference={SNYK_MONITOR_TARGET_REFERENCE}"
        ),
        "monitor_project_name": SNYK_MONITOR_PROJECT_NAME,
        "monitor_target_reference": SNYK_MONITOR_TARGET_REFERENCE,
        "target_file": (
            "module12/fixtures/vulnerable_companion_tool/package-lock.json"
        ),
        "buildspec": LIVE_SCAN_BUILDSPEC,
        "publish_mode": "live",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--action", choices=("finding", "recovery", "live-plan"))
    parser.add_argument("--tool-digest", default="sha256:tool-observed")
    parser.add_argument("--reviewed-tool-digest", default="sha256:tool-reviewed")
    args = parser.parse_args()
    if args.action == "finding":
        result = build_finding_event()
    elif args.action == "recovery":
        result = build_recovery_event(
            tool_digest=args.tool_digest,
            reviewed_tool_digest=args.reviewed_tool_digest,
        )
    elif args.action == "live-plan":
        result = live_scan_plan()
    else:
        parser.error("--action is required")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
