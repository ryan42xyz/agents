#!/usr/bin/env python3
"""SRE oncall triage agent output verifier.

Runs deterministic checks on investigation output files to validate
schema completeness, evidence consistency, and language safety.

Usage:
    python3 verify.py tmp/sre-triage-2026-03-31_14-23-45.md
    python3 verify.py tmp/sre-triage-2026-03-31_14-23-45.md --json

Exit codes:
    0 = PASS (all checks passed)
    1 = WARN (warnings only, review before sending)
    2 = FAIL (failures found, fix required)
"""

import argparse
import json
import re
import sys
from pathlib import Path

# Add parent to path for _parse import
sys.path.insert(0, str(Path(__file__).parent))
from _parse import (
    parse_sections,
    parse_investigation_log,
    parse_yaml_block,
    extract_field,
    find_debug_tree_ref,
    count_debug_tree_steps,
    has_unknown_results,
)

# --- Constants ---

REQUIRED_SECTIONS = [
    "slack response",
    "internal notes",
    "extracted signals",
    "links",
    "investigation log",
]
# Historical Pattern Matches is optional (marked "optional" in SKILL.md)

INTERNAL_NOTES_SUBSECTIONS = [
    "triage result",
    "conclusion",
    "event type",
    "hypothesis tree",
    "evidence checklist",
    "next verification",
    "guardrail check",
    "uncertainty note",
]

# Regex patterns for non-conservative language in Slack responses
ASSERTION_PATTERNS = [
    (r"\broot cause is\b(?!.*\b(?:likely|possibly|probably)\b)", "Asserts root cause without hedging"),
    (r"\bdefinitely\b", "Uses 'definitely' — too assertive for Slack response"),
    (r"\bcertainly\b", "Uses 'certainly' — too assertive for Slack response"),
    (r"\bclearly\b", "Uses 'clearly' — too assertive for Slack response"),
    (r"\ball users\b", "Asserts scope 'all users' — use 'some users may be affected'"),
    (r"\ball customers\b", "Asserts scope 'all customers' — use 'some customers may be affected'"),
    (r"\beveryone\b", "Asserts scope 'everyone' — use 'users may be affected'"),
    (r"\bwill cause\b", "Speculates about future — use 'may cause'"),
    (r"\bwill result\b", "Speculates about future — use 'may result'"),
    (r"\bconfirmed that\b", "Strong assertion — use 'evidence suggests' or 'consistent with'"),
]

# Debug trees directory relative to the agent root
DEBUG_TREES_DIR = Path(__file__).parent.parent.parent / "knowledge" / "debug-trees"


# --- Check functions ---

def check_schema_completeness(sections: dict[str, str]) -> list[dict]:
    """Check 1: All required output sections present."""
    results = []
    for section in REQUIRED_SECTIONS:
        found = any(section in key for key in sections)
        if not found:
            results.append({
                "check": "schema_completeness",
                "level": "FAIL",
                "message": f"Missing required section: '{section}'",
            })

    # Check Internal Notes subsections
    internal_notes_text = ""
    for key, val in sections.items():
        if "internal notes" in key:
            internal_notes_text += val + "\n"
    # Also gather subsection keys that might be parsed as separate sections
    for subsection in INTERNAL_NOTES_SUBSECTIONS:
        found_in_sections = any(subsection in key for key in sections)
        found_in_text = subsection.replace(" ", "").lower() in internal_notes_text.replace(" ", "").lower()
        # More lenient: check if the subsection title appears anywhere
        found_anywhere = any(
            subsection in key or subsection.replace(" ", "") in key.replace(" ", "")
            for key in sections
        )
        if not (found_in_sections or found_in_text or found_anywhere):
            results.append({
                "check": "schema_completeness",
                "level": "WARN",
                "message": f"Missing Internal Notes subsection: '{subsection}'",
            })

    if not results:
        results.append({
            "check": "schema_completeness",
            "level": "PASS",
            "message": "All required sections present",
        })
    return results


def check_debug_tree_completion(sections: dict[str, str]) -> list[dict]:
    """Check 2: If debug tree was used, verify all steps have results."""
    results = []
    tree_ref = find_debug_tree_ref(sections)

    if tree_ref is None:
        results.append({
            "check": "debug_tree_completion",
            "level": "PASS",
            "message": "No debug tree used (FACETS-based investigation)",
        })
        return results

    # Find the debug tree file
    tree_filename = tree_ref.split("/")[-1]
    tree_path = DEBUG_TREES_DIR / tree_filename
    if not tree_path.exists():
        # Try with .md extension
        if not tree_filename.endswith(".md"):
            tree_path = DEBUG_TREES_DIR / f"{tree_filename}.md"
        if not tree_path.exists():
            results.append({
                "check": "debug_tree_completion",
                "level": "WARN",
                "message": f"Debug tree file not found: {tree_filename}",
            })
            return results

    tree_text = tree_path.read_text()
    expected_steps = count_debug_tree_steps(tree_text)

    # Parse investigation log
    log_text = ""
    for key, val in sections.items():
        if "investigation log" in key or "inspection checklist" in key:
            log_text += val + "\n"

    log_rows = parse_investigation_log(log_text)
    completed_steps = set()
    for row in log_rows:
        step_val = row.get("step", "")
        # Extract step number/id
        step_match = re.match(r"(\w+)", step_val)
        if step_match:
            completed_steps.add(step_match.group(1))

    # Check for missing steps (allowing for branch skips)
    missing = []
    for step in expected_steps:
        if step not in completed_steps:
            missing.append(step)

    if missing:
        # Check if missing steps were skipped via branch logic
        branch_skip_indicators = [
            "different triage", "skip", "not applicable", "branched",
            "scenario", "→ step", "escalate", "manual",
        ]
        all_branches = " ".join(
            row.get("branch", "") for row in log_rows
        ).lower()

        for step in missing:
            is_branch_skip = any(ind in all_branches for ind in branch_skip_indicators)
            if is_branch_skip:
                results.append({
                    "check": "debug_tree_completion",
                    "level": "PASS",
                    "message": f"Step {step} skipped via branch logic",
                })
            else:
                results.append({
                    "check": "debug_tree_completion",
                    "level": "WARN",
                    "message": f"Debug tree step {step} has no result in investigation log",
                })
    else:
        results.append({
            "check": "debug_tree_completion",
            "level": "PASS",
            "message": f"All {len(expected_steps)} debug tree steps completed",
        })

    return results


def check_conclusion_evidence(sections: dict[str, str]) -> list[dict]:
    """Check 3: Verdict and evidence chain consistency."""
    results = []

    # Find verdict and confidence
    all_text = "\n".join(sections.values())
    verdict = extract_field(all_text, "verdict")
    confidence = extract_field(all_text, "confidence")
    evidence_chain = extract_field(all_text, "evidence_chain")

    if verdict is None:
        results.append({
            "check": "conclusion_evidence",
            "level": "WARN",
            "message": "No verdict field found in output",
        })
        return results

    # Check: verdict exists but evidence_chain is empty/missing
    if evidence_chain is None or evidence_chain.strip() in ("", "[]", "none"):
        results.append({
            "check": "conclusion_evidence",
            "level": "FAIL",
            "message": f"Verdict is '{verdict}' but evidence_chain is missing or empty",
        })

    # Check: FALSE_ALERT verdict but alert is firing
    if "false_alert" in verdict.lower():
        # Look for positive assertions of firing state in investigation log
        log_text = "\n".join(
            val for key, val in sections.items()
            if "investigation log" in key or "inspection" in key
        )
        log_rows = parse_investigation_log(log_text)
        for row in log_rows:
            result_text = row.get("result", "").lower()
            # Match "state=firing" or "state: firing" but NOT "not firing" or "no firing"
            if re.search(r"state\s*[=:]\s*firing", result_text):
                results.append({
                    "check": "conclusion_evidence",
                    "level": "FAIL",
                    "message": "Verdict is FALSE_ALERT but investigation log shows alert state = firing",
                })
                break

    if not results:
        results.append({
            "check": "conclusion_evidence",
            "level": "PASS",
            "message": f"Verdict '{verdict}' consistent with evidence (confidence: {confidence or 'not specified'})",
        })

    return results


def check_slack_language(sections: dict[str, str]) -> list[dict]:
    """Check 4: Slack response uses conservative language."""
    results = []

    slack_text = ""
    for key, val in sections.items():
        if "slack response" in key:
            slack_text += val + "\n"

    if not slack_text.strip():
        results.append({
            "check": "slack_language",
            "level": "WARN",
            "message": "Slack response section is empty or not found",
        })
        return results

    for pattern, description in ASSERTION_PATTERNS:
        matches = re.findall(pattern, slack_text, re.IGNORECASE)
        if matches:
            results.append({
                "check": "slack_language",
                "level": "WARN",
                "message": description,
            })

    if not results:
        results.append({
            "check": "slack_language",
            "level": "PASS",
            "message": "Slack response language is conservative",
        })

    return results


def check_links(sections: dict[str, str]) -> list[dict]:
    """Check 5: Link validation — Ready links have no placeholders, Templates have missing list."""
    results = []

    links_text = ""
    for key, val in sections.items():
        if "links" in key and "deep" not in key:
            links_text += val + "\n"

    if not links_text.strip():
        results.append({
            "check": "links",
            "level": "WARN",
            "message": "Links section is empty or not found",
        })
        return results

    # Check Ready links for unfilled placeholders
    ready_section = False
    template_section = False
    for line in links_text.split("\n"):
        line_lower = line.strip().lower()
        if "ready" in line_lower and (":" in line_lower or "##" in line_lower):
            ready_section = True
            template_section = False
        elif "template" in line_lower and (":" in line_lower or "##" in line_lower):
            ready_section = False
            template_section = True

        # Check for placeholders in Ready URLs
        if ready_section and re.search(r"\{[a-z_]+\}", line):
            results.append({
                "check": "links",
                "level": "FAIL",
                "message": f"Ready link contains unfilled placeholder: {line.strip()[:80]}",
            })

    if not results:
        results.append({
            "check": "links",
            "level": "PASS",
            "message": "Links validated",
        })

    return results


def check_unknown_documented(sections: dict[str, str]) -> list[dict]:
    """Check 6: UNKNOWN results in investigation log are mentioned in Uncertainty Note."""
    results = []

    # Parse investigation log
    log_text = ""
    for key, val in sections.items():
        if "investigation log" in key or "inspection" in key:
            log_text += val + "\n"

    log_rows = parse_investigation_log(log_text)
    unknown_rows = has_unknown_results(log_rows)

    if not unknown_rows:
        return []  # No unknowns, nothing to check

    # Find uncertainty note
    uncertainty_text = ""
    for key, val in sections.items():
        if "uncertainty" in key:
            uncertainty_text += val + "\n"

    if not uncertainty_text.strip():
        results.append({
            "check": "unknown_documented",
            "level": "WARN",
            "message": f"{len(unknown_rows)} step(s) have UNKNOWN result but Uncertainty Note is missing",
        })
    else:
        # Check that unknowns are at least mentioned
        for row in unknown_rows:
            step = row.get("step", "?")
            tool = row.get("tool", "")
            # Lenient check: just see if the step number or tool name appears in uncertainty note
            if step not in uncertainty_text and tool not in uncertainty_text:
                results.append({
                    "check": "unknown_documented",
                    "level": "WARN",
                    "message": f"Step {step} result is UNKNOWN but not mentioned in Uncertainty Note",
                })

    return results


def check_scope_consistency(sections: dict[str, str]) -> list[dict]:
    """Check 7: Investigation scope declaration vs actual queries (WS3)."""
    results = []

    # Find scope declaration
    scope_text = ""
    for key, val in sections.items():
        if "investigation scope" in key or "scope" in key:
            scope_text += val + "\n"

    if not scope_text.strip():
        # Scope declaration not present — not a failure, just skip
        return []

    scope = parse_yaml_block(scope_text)
    out_of_scope_raw = scope.get("out_of_scope", "")

    if not out_of_scope_raw:
        return []

    # Parse out_of_scope list
    out_of_scope_items = [
        item.strip().lower()
        for item in re.findall(r"[^,\[\]]+", out_of_scope_raw)
        if item.strip()
    ]

    # Check investigation log queries against out_of_scope
    log_text = ""
    for key, val in sections.items():
        if "investigation log" in key or "inspection" in key:
            log_text += val + "\n"

    log_rows = parse_investigation_log(log_text)
    for row in log_rows:
        query = row.get("query", "").lower()
        for item in out_of_scope_items:
            if item in query:
                results.append({
                    "check": "scope_consistency",
                    "level": "WARN",
                    "message": f"Step {row.get('step', '?')} queries '{item}' which is declared out_of_scope",
                })

    return results


# --- Main ---

def run_all_checks(md_text: str) -> list[dict]:
    """Run all verification checks and return results."""
    sections = parse_sections(md_text)
    all_results = []
    all_results.extend(check_schema_completeness(sections))
    all_results.extend(check_debug_tree_completion(sections))
    all_results.extend(check_conclusion_evidence(sections))
    all_results.extend(check_slack_language(sections))
    all_results.extend(check_links(sections))
    all_results.extend(check_unknown_documented(sections))
    all_results.extend(check_scope_consistency(sections))
    return all_results


def summarize(results: list[dict]) -> tuple[str, int]:
    """Summarize check results into overall verdict and exit code."""
    has_fail = any(r["level"] == "FAIL" for r in results)
    has_warn = any(r["level"] == "WARN" for r in results)

    if has_fail:
        return "FAIL", 2
    elif has_warn:
        return "WARN", 1
    else:
        return "PASS", 0


def main():
    parser = argparse.ArgumentParser(
        description="Verify sre_oncall_triage_agent investigation output"
    )
    parser.add_argument("file", help="Path to sre-triage output .md file")
    parser.add_argument("--json", action="store_true", help="Output JSON instead of human-readable")
    args = parser.parse_args()

    filepath = Path(args.file)
    if not filepath.exists():
        print(f"Error: file not found: {filepath}", file=sys.stderr)
        sys.exit(2)

    md_text = filepath.read_text()
    results = run_all_checks(md_text)
    verdict, exit_code = summarize(results)

    if args.json:
        output = {
            "file": str(filepath),
            "verdict": verdict,
            "checks": results,
        }
        print(json.dumps(output, indent=2))
    else:
        # Human-readable output
        fail_count = sum(1 for r in results if r["level"] == "FAIL")
        warn_count = sum(1 for r in results if r["level"] == "WARN")
        pass_count = sum(1 for r in results if r["level"] == "PASS")

        print(f"Verification: {verdict}")
        print(f"  PASS: {pass_count}  WARN: {warn_count}  FAIL: {fail_count}")
        print()

        for r in results:
            if r["level"] == "FAIL":
                print(f"  ✗ [{r['check']}] {r['message']}")
            elif r["level"] == "WARN":
                print(f"  ⚠ [{r['check']}] {r['message']}")

        if verdict == "PASS":
            print("  All checks passed.")

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
