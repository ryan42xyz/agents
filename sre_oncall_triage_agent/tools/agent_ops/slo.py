#!/usr/bin/env python3
"""SRE oncall triage agent SLO metrics aggregation.

Scans investigation output files and produces quality metrics.
Derives all data from existing output files — no new infrastructure needed.

Usage:
    python3 slo.py                          # scan all output files
    python3 slo.py --since 2026-03-01       # filter by date
    python3 slo.py --json                   # machine-readable output

Exit codes:
    0 = success
    1 = no output files found
"""

import argparse
import glob
import json
import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

# Add parent to path for _parse import
sys.path.insert(0, str(Path(__file__).parent))
from _parse import (
    parse_sections,
    parse_investigation_log,
    extract_field,
    find_debug_tree_ref,
    has_unknown_results,
)

# Default output directory (relative to agent root)
DEFAULT_OUTPUT_DIR = Path(__file__).parent.parent.parent / "tmp"


def extract_date_from_filename(filename: str) -> str | None:
    """Extract date from sre-triage-YYYY-MM-DD_HH-MM-SS.md filename."""
    match = re.search(r"sre-triage-(\d{4}-\d{2}-\d{2})", filename)
    return match.group(1) if match else None


def analyze_file(filepath: Path) -> dict | None:
    """Extract metrics from a single investigation output file."""
    try:
        md_text = filepath.read_text()
    except (OSError, UnicodeDecodeError):
        return None

    sections = parse_sections(md_text)
    if not sections:
        return None

    metrics: dict = {
        "file": filepath.name,
        "date": extract_date_from_filename(filepath.name),
    }

    # Debug tree usage
    tree_ref = find_debug_tree_ref(sections)
    metrics["debug_tree_used"] = tree_ref is not None
    metrics["debug_tree_name"] = tree_ref

    # Verdict and confidence
    all_text = "\n".join(sections.values())
    metrics["verdict"] = extract_field(all_text, "verdict")
    metrics["confidence"] = extract_field(all_text, "confidence")

    # Triage result
    triage_result = extract_field(all_text, "triage result") or extract_field(all_text, "Triage result")
    if triage_result is None:
        # Try to find IGNORE_DEV, KNOWN_ISSUE, etc. in text
        for label in ["IGNORE_DEV", "KNOWN_ISSUE", "NON_ACTIONABLE_NOISE", "NEEDS_ATTENTION"]:
            if label in all_text:
                triage_result = label
                break
    metrics["triage_result"] = triage_result

    # Investigation log metrics
    log_text = ""
    for key, val in sections.items():
        if "investigation log" in key or "inspection" in key:
            log_text += val + "\n"
    log_rows = parse_investigation_log(log_text)
    metrics["steps_count"] = len(log_rows)
    metrics["unknown_steps"] = len(has_unknown_results(log_rows))

    # Verification result
    verification = None
    for key in sections:
        if "verification" in key:
            if "pass" in key.lower() or "pass" in sections[key].lower():
                verification = "PASS"
            elif "warn" in key.lower() or "warn" in sections[key].lower():
                verification = "WARN"
            elif "fail" in key.lower() or "fail" in sections[key].lower():
                verification = "FAIL"
    metrics["verification"] = verification

    # Routing cluster
    cluster = None
    for key, val in sections.items():
        if "routing cluster" in key or "historical pattern" in key:
            cluster_match = re.search(r"Cluster\s+\d+\s*[—–-]\s*\S+", val)
            if cluster_match:
                cluster = cluster_match.group(0)
    # Also check investigation scope
    if cluster is None:
        for key, val in sections.items():
            if "scope" in key:
                cluster_match = re.search(r"Cluster\s+\d+\s*[—–-]\s*\S+", val)
                if cluster_match:
                    cluster = cluster_match.group(0)
    metrics["cluster"] = cluster

    # Scope expansion
    scope_expanded = False
    for key, val in sections.items():
        if "scope" in key:
            if re.search(r"expand|update|changed|added", val, re.IGNORECASE):
                scope_expanded = True
    metrics["scope_expanded"] = scope_expanded

    return metrics


def aggregate(file_metrics: list[dict]) -> dict:
    """Aggregate metrics across all files."""
    total = len(file_metrics)
    if total == 0:
        return {"total": 0}

    agg: dict = {"total": total}

    # Debug tree rate
    tree_count = sum(1 for m in file_metrics if m["debug_tree_used"])
    agg["debug_tree_count"] = tree_count
    agg["debug_tree_rate"] = round(tree_count / total * 100, 1)

    # Verdict distribution
    verdicts = Counter(m["verdict"] for m in file_metrics if m["verdict"])
    agg["verdict_distribution"] = dict(verdicts)

    # Confidence distribution
    confidences = Counter(m["confidence"] for m in file_metrics if m["confidence"])
    agg["confidence_distribution"] = dict(confidences)

    # Triage result distribution
    triage = Counter(m["triage_result"] for m in file_metrics if m["triage_result"])
    agg["triage_result_distribution"] = dict(triage)

    # Steps to conclusion
    steps = [m["steps_count"] for m in file_metrics if m["steps_count"] > 0]
    agg["avg_steps"] = round(sum(steps) / len(steps), 1) if steps else 0

    # Unknown steps
    unknown_count = sum(1 for m in file_metrics if m["unknown_steps"] > 0)
    agg["investigations_with_unknowns"] = unknown_count

    # Verification results
    verifications = Counter(m["verification"] for m in file_metrics if m["verification"])
    agg["verification_distribution"] = dict(verifications)
    verified = sum(1 for m in file_metrics if m["verification"])
    agg["verification_pass_rate"] = (
        round(verifications.get("PASS", 0) / verified * 100, 1) if verified > 0 else None
    )

    # Cluster distribution
    clusters = Counter(m["cluster"] for m in file_metrics if m["cluster"])
    agg["cluster_distribution"] = dict(clusters)

    # Scope expansion
    scope_exp = sum(1 for m in file_metrics if m["scope_expanded"])
    agg["scope_expansions"] = scope_exp

    return agg


def print_human(agg: dict, since: str | None = None):
    """Print human-readable SLO report."""
    if agg["total"] == 0:
        print("No investigation output files found.")
        return

    period = f" (since {since})" if since else ""
    print(f"Agent SLO Report{period}")
    print("─" * 44)
    print(f"Investigations:           {agg['total']}")
    print(f"Debug tree used:          {agg['debug_tree_count']} / {agg['total']} ({agg['debug_tree_rate']}%)")
    if agg["verification_pass_rate"] is not None:
        print(f"Verification pass rate:   {agg['verification_pass_rate']}%")
    print()

    if agg["verdict_distribution"]:
        print("Verdict distribution:")
        for verdict, count in sorted(agg["verdict_distribution"].items(), key=lambda x: -x[1]):
            print(f"  {verdict:20s} {count}")
        print()

    if agg["confidence_distribution"]:
        print("Confidence distribution:")
        for conf, count in sorted(agg["confidence_distribution"].items(), key=lambda x: -x[1]):
            print(f"  {conf:20s} {count}")
        print()

    if agg["triage_result_distribution"]:
        print("Triage result distribution:")
        for result, count in sorted(agg["triage_result_distribution"].items(), key=lambda x: -x[1]):
            print(f"  {result:24s} {count}")
        print()

    print(f"Avg steps to conclusion:  {agg['avg_steps']}")
    print(f"Investigations w/ UNKNOWN steps: {agg['investigations_with_unknowns']} / {agg['total']}")
    print(f"Scope expansions:         {agg['scope_expansions']}")

    if agg["cluster_distribution"]:
        print()
        print("Cluster distribution:")
        for cluster, count in sorted(agg["cluster_distribution"].items(), key=lambda x: -x[1]):
            print(f"  {cluster:36s} {count}")


def main():
    parser = argparse.ArgumentParser(description="SRE oncall triage agent SLO metrics")
    parser.add_argument("--since", help="Only include files from this date (YYYY-MM-DD)")
    parser.add_argument("--dir", help="Output directory to scan", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--json", action="store_true", help="Output JSON")
    args = parser.parse_args()

    output_dir = Path(args.dir)
    pattern = str(output_dir / "sre-triage-*.md")
    files = sorted(glob.glob(pattern))

    if not files:
        if args.json:
            print(json.dumps({"total": 0, "error": "no files found"}))
        else:
            print(f"No oncall-agent output files found in {output_dir}")
        sys.exit(1)

    file_metrics = []
    for f in files:
        filepath = Path(f)
        # Date filter
        if args.since:
            file_date = extract_date_from_filename(filepath.name)
            if file_date and file_date < args.since:
                continue

        metrics = analyze_file(filepath)
        if metrics:
            file_metrics.append(metrics)

    agg = aggregate(file_metrics)

    if args.json:
        output = {
            "aggregate": agg,
            "investigations": file_metrics,
        }
        print(json.dumps(output, indent=2, default=str))
    else:
        print_human(agg, args.since)


if __name__ == "__main__":
    main()
