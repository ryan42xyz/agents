"""Evaluation scorer — grades investigation output against expected results."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from .cases import EvalCase
from ..output.verifier import verify_report


@dataclass
class ScoreResult:
    case_id: str
    total_score: float          # 0.0 - 1.0
    routing_correct: bool       # routed to correct cluster
    debug_tree_correct: bool    # correct debug tree selected
    verdict_correct: bool       # verdict in expected set
    sections_complete: bool     # all required sections present
    language_safe: bool         # no overconfident Slack language
    evidence_present: bool      # evidence chain non-empty
    details: dict[str, Any]

    def summary_line(self) -> str:
        score_pct = int(self.total_score * 100)
        checks = "".join([
            "R" if self.routing_correct else "r",
            "T" if self.debug_tree_correct else "t",
            "V" if self.verdict_correct else "v",
            "S" if self.sections_complete else "s",
            "L" if self.language_safe else "l",
            "E" if self.evidence_present else "e",
        ])
        return f"{self.case_id}: {score_pct:3d}%  [{checks}]"


def score_investigation(case: EvalCase, report_text: str) -> ScoreResult:
    """Score an investigation report against expected outcomes.

    Scoring weights:
      - Routing correct (cluster):     20%
      - Debug tree correct:            20%
      - Verdict in expected set:       20%
      - Sections complete (verifier):  15%
      - Language safe (verifier):      15%
      - Evidence chain present:        10%
    """
    exp = case.expected
    details: dict[str, Any] = {}

    # 1. Routing (20%) — check if routing cluster mentioned
    routing_correct = False
    expected_cluster = exp.get("routing_cluster", "")
    if expected_cluster:
        cluster_num = re.search(r"Cluster\s+(\d+)", expected_cluster)
        if cluster_num:
            n = cluster_num.group(1)
            routing_correct = bool(
                re.search(rf"[Cc]luster\s+{n}", report_text) or
                re.search(rf"Cluster {n}", report_text)
            )
    details["routing_cluster"] = {"expected": expected_cluster, "correct": routing_correct}

    # 2. Debug tree (20%)
    debug_tree_correct = False
    expected_tree = exp.get("debug_tree", "")
    if expected_tree:
        tree_stem = expected_tree.replace(".md", "").replace("debug-tree-", "")
        debug_tree_correct = tree_stem.lower() in report_text.lower() or expected_tree in report_text
    details["debug_tree"] = {"expected": expected_tree, "correct": debug_tree_correct}

    # 3. Verdict (20%)
    verdict_correct = False
    expected_verdicts = set(exp.get("verdict_in", []))
    if expected_verdicts:
        for v in expected_verdicts:
            if v in report_text:
                verdict_correct = True
                details["verdict_found"] = v
                break
    details["verdict"] = {"expected": list(expected_verdicts), "correct": verdict_correct}

    # 4 + 5. Run verifier for sections + language (15% + 15%)
    verify_result = verify_report(report_text)
    sections_complete = not any(
        c.level == "FAIL" and c.check == "schema_completeness"
        for c in verify_result.checks
    )
    language_safe = not any(
        c.level == "WARN" and c.check == "slack_language"
        for c in verify_result.checks
    )
    details["verifier"] = verify_result.verdict
    details["verifier_checks"] = {c.check: c.level for c in verify_result.checks}

    # 6. Evidence chain (10%)
    evidence_required = exp.get("evidence_chain_nonempty", True)
    evidence_present = not evidence_required or bool(
        re.search(r"evidence[_\s]chain\s*:\s*\[.+\]", report_text, re.IGNORECASE)
    )
    details["evidence"] = {"required": evidence_required, "present": evidence_present}

    # Composite score
    weights = [
        (routing_correct, 0.20),
        (debug_tree_correct, 0.20),
        (verdict_correct, 0.20),
        (sections_complete, 0.15),
        (language_safe, 0.15),
        (evidence_present, 0.10),
    ]
    total = sum(w for ok, w in weights if ok)

    return ScoreResult(
        case_id=case.id,
        total_score=total,
        routing_correct=routing_correct,
        debug_tree_correct=debug_tree_correct,
        verdict_correct=verdict_correct,
        sections_complete=sections_complete,
        language_safe=language_safe,
        evidence_present=evidence_present,
        details=details,
    )
