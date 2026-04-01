"""Test case loader for evaluation pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class MockToolResponse:
    match_query: str = ""
    match_command: str = ""
    response: Any = None


@dataclass
class EvalCase:
    id: str
    description: str
    alert_text: str
    expected: dict[str, Any]
    mock_tool_responses: dict[str, list[MockToolResponse]] = field(default_factory=dict)
    source_path: Path | None = None


def load_cases(cases_dir: Path) -> list[EvalCase]:
    """Load all YAML test cases from a directory."""
    cases = []
    for yaml_file in sorted(cases_dir.glob("case_*.yaml")):
        case = load_case(yaml_file)
        if case:
            cases.append(case)
    return cases


def load_case(path: Path) -> EvalCase | None:
    """Load a single test case from a YAML file."""
    try:
        data = yaml.safe_load(path.read_text())
    except Exception as e:
        print(f"Warning: could not load {path}: {e}")
        return None

    mock_responses: dict[str, list[MockToolResponse]] = {}
    for tool_name, responses in (data.get("mock_tool_responses") or {}).items():
        mock_responses[tool_name] = [
            MockToolResponse(
                match_query=r.get("match_query", ""),
                match_command=r.get("match_command", ""),
                response=r.get("response"),
            )
            for r in (responses or [])
        ]

    return EvalCase(
        id=data.get("id", path.stem),
        description=data.get("description", ""),
        alert_text=data.get("input", {}).get("alert_text", ""),
        expected=data.get("expected", {}),
        mock_tool_responses=mock_responses,
        source_path=path,
    )
