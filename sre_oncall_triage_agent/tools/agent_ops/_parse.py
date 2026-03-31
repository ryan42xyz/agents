"""Shared markdown parsing utilities for oncall agent output files.

Used by verify.py and slo.py to extract structured data from
semi-structured markdown investigation output files.
"""

import re
from typing import Optional


def parse_sections(md_text: str) -> dict[str, str]:
    """Split markdown into sections by ## headers.

    Returns dict mapping header text (lowercase, stripped) to section body.
    Handles ## and ### level headers. For nested sections (###),
    they are included in both their own key and the parent ## section.
    """
    sections: dict[str, str] = {}
    current_header = None
    current_lines: list[str] = []

    for line in md_text.split("\n"):
        match = re.match(r"^(#{1,3})\s+(.+)$", line)
        if match:
            # Save previous section
            if current_header is not None:
                sections[current_header] = "\n".join(current_lines).strip()
            current_header = match.group(2).strip().lower()
            current_lines = []
        else:
            current_lines.append(line)

    # Save last section
    if current_header is not None:
        sections[current_header] = "\n".join(current_lines).strip()

    return sections


def parse_investigation_log(section_text: str) -> list[dict]:
    """Parse pipe-delimited investigation log table.

    Expected format:
    | Step | Tool | Query | Result | Interpretation | Branch |
    |------|------|-------|--------|----------------|--------|
    | 1    | ...  | ...   | ...    | ...            | ...    |

    Returns list of dicts with keys from header row.
    """
    lines = [l.strip() for l in section_text.split("\n") if l.strip().startswith("|")]
    if len(lines) < 2:
        return []

    # First line is header, second is separator
    headers = [h.strip().lower() for h in lines[0].split("|") if h.strip()]
    rows = []
    for line in lines[2:]:  # skip header and separator
        cells = [c.strip() for c in line.split("|") if c.strip() or c == ""]
        # Filter out empty strings from leading/trailing pipes
        cells = [c.strip() for c in line.split("|")]
        cells = cells[1:-1] if len(cells) > 2 else cells  # strip leading/trailing empty
        if len(cells) >= len(headers):
            row = {headers[i]: cells[i].strip() for i in range(len(headers))}
            rows.append(row)

    return rows


def parse_yaml_block(section_text: str) -> dict[str, str]:
    """Parse a simple YAML-like block from section text.

    Handles single-level key: value and key: [list, items].
    Not a full YAML parser — just enough for scope declarations.
    """
    result: dict[str, str] = {}
    for line in section_text.split("\n"):
        match = re.match(r"^(\w[\w_]*)\s*:\s*(.+)$", line.strip())
        if match:
            key = match.group(1).strip()
            value = match.group(2).strip()
            result[key] = value
    return result


def extract_field(text: str, field_name: str) -> Optional[str]:
    """Extract a field value from text like 'field_name: value' or '- field_name: value'."""
    pattern = rf"[-\s]*{re.escape(field_name)}\s*:\s*(.+)"
    match = re.search(pattern, text, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return None


def find_debug_tree_ref(sections: dict[str, str]) -> Optional[str]:
    """Find debug tree filename referenced in output.

    Looks for pattern: **Debug tree**: `filename.md`
    """
    for section_text in sections.values():
        match = re.search(r"\*\*Debug tree\*\*\s*:\s*`?([^`\n]+)`?", section_text)
        if match:
            return match.group(1).strip()
    return None


def count_debug_tree_steps(tree_text: str) -> list[str]:
    """Count and list step headers in a debug tree file.

    Returns list of step identifiers like ["1", "2", "3", "2B", "3A"].
    """
    steps = []
    for match in re.finditer(r"^###\s+Step\s+(\w+)", tree_text, re.MULTILINE):
        steps.append(match.group(1))
    return steps


def has_unknown_results(log_rows: list[dict]) -> list[dict]:
    """Find investigation log rows where result is UNKNOWN."""
    return [row for row in log_rows if "unknown" in row.get("result", "").lower()]
