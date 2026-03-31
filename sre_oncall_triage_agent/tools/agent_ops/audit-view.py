#!/usr/bin/env python3
"""
audit-view.py — Agent Audit Log Inspector

Usage:
  python3 audit-view.py                  # today's log
  python3 audit-view.py 2026-03-28       # specific date
  python3 audit-view.py --all            # all logs merged
  python3 audit-view.py --tail 20        # last N entries
  python3 audit-view.py --grep kubectl   # filter by keyword
  python3 audit-view.py --session <id>   # filter by session_id prefix
  python3 audit-view.py --json           # raw JSON output (pipe-friendly)
"""

import sys
import json
import os
import glob
import argparse
from datetime import date
from textwrap import shorten

# Resolve logs dir relative to this script's real location (follows symlinks)
_SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))
AUDIT_DIR = os.path.join(_SCRIPT_DIR, "logs")

# ANSI colors
RESET  = "\033[0m"
BOLD   = "\033[1m"
DIM    = "\033[2m"
CYAN   = "\033[36m"
YELLOW = "\033[33m"
GREEN  = "\033[32m"
RED    = "\033[31m"
BLUE   = "\033[34m"
GRAY   = "\033[90m"


def load_jsonl(path):
    records = []
    with open(path) as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as e:
                print(f"{RED}[parse error line {i}]{RESET} {e}", file=sys.stderr)
    return records


def load_all():
    files = sorted(glob.glob(os.path.join(AUDIT_DIR, "*.jsonl")))
    records = []
    for f in files:
        records.extend(load_jsonl(f))
    return records


def format_record(r, idx, total, pre_index=None):
    ts        = r.get("timestamp", "?")
    sid       = r.get("session_id", "?")[:8]
    cwd       = r.get("cwd", "?")
    cmd       = r.get("command", "")
    phase     = r.get("phase")  # "pre", "post", or None (legacy)

    # Phase badge
    if phase == "pre":
        phase_badge = f" {YELLOW}[PRE]{RESET}"
    elif phase == "post":
        phase_badge = f" {GREEN}[POST]{RESET}"
    else:
        phase_badge = ""  # legacy entry (no phase field)

    # Pre-entries have no output — skip output parsing entirely
    out_text = ""
    if phase != "pre":
        if r.get("stdout") or r.get("stderr"):
            out_text = r.get("stdout", "").strip()
            if not out_text and r.get("stderr"):
                out_text = f"[stderr] {r['stderr'].strip()}"
        else:
            preview = r.get("output_preview", "")
            try:
                out = json.loads(preview)
                out_text = out.get("stdout", "").strip() or f"[stderr] {out.get('stderr','').strip()}"
            except Exception:
                import re
                m = re.search(r'"stdout"\s*:\s*"((?:[^"\\]|\\.)*)', preview)
                if m:
                    out_text = m.group(1).replace("\\n", "\n").replace('\\"', '"').replace("\\t", "\t")
                else:
                    out_text = preview.strip()

    # Strip comment lines and continuation backslashes; show only executable tokens
    cmd_lines = [l.strip().rstrip("\\").strip() for l in cmd.splitlines()
                 if l.strip() and not l.strip().startswith("#")]
    cmd_clean = " ".join(cmd_lines) if cmd_lines else cmd
    cmd_short = shorten(cmd_clean, width=120, placeholder="…")

    # render stdout as real multi-line, max OUT_LINES lines
    OUT_LINES = 5
    out_lines_raw = [l for l in out_text.splitlines() if l.strip()]
    out_display = []
    for l in out_lines_raw[:OUT_LINES]:
        out_display.append(shorten(l, width=100, placeholder="…"))
    truncated = len(out_lines_raw) > OUT_LINES

    reasoning = r.get("reasoning")

    lines = [
        f"{BOLD}{CYAN}[{idx}/{total}]{RESET}{phase_badge} {GRAY}{ts}{RESET}  {BLUE}session:{sid}…{RESET}",
        f"  {DIM}cwd{RESET}  {cwd}",
    ]
    if phase == "pre":
        if reasoning:
            lines.append(f"  {BOLD}{YELLOW}why{RESET}  {reasoning}")
        else:
            lines.append(f"  {DIM}why{RESET}  {GRAY}(no # INTENT: provided){RESET}")
    # POST: inherit reasoning from matching PRE entry
    if phase == "post" and pre_index:
        inherited = pre_index.get(cmd)
        if inherited:
            lines.append(f"  {DIM}why{RESET}  {GRAY}↳ {shorten(inherited, width=100, placeholder='…')}  [PRE]{RESET}")

    lines += [
        f"  {YELLOW}cmd{RESET}  {cmd_short}",
    ]
    if out_display:
        lines.append(f"  {GREEN}out{RESET}  {out_display[0]}")
        for l in out_display[1:]:
            lines.append(f"       {l}")
        if truncated:
            lines.append(f"       {GRAY}… ({len(out_lines_raw)} lines total){RESET}")
    lines.append("")
    return "\n".join(lines)


def format_json(records):
    print(json.dumps(records, indent=2, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(description="Agent audit log inspector")
    parser.add_argument("date", nargs="?", default=str(date.today()),
                        help="Date to inspect (YYYY-MM-DD), default: today")
    parser.add_argument("--all", action="store_true", help="Load all log files")
    parser.add_argument("--tail", type=int, metavar="N", help="Show last N entries")
    parser.add_argument("--grep", metavar="KEYWORD", help="Filter entries containing keyword")
    parser.add_argument("--session", metavar="PREFIX", help="Filter by session_id prefix")
    parser.add_argument("--json", action="store_true", help="Output raw JSON")
    args = parser.parse_args()

    # Load
    if args.all:
        records = load_all()
        source = "all logs"
    else:
        path = os.path.join(AUDIT_DIR, f"{args.date}.jsonl")
        if not os.path.exists(path):
            print(f"{RED}No log file found:{RESET} {path}")
            sys.exit(1)
        records = load_jsonl(path)
        source = args.date

    # Filter
    if args.grep:
        kw = args.grep.lower()
        records = [r for r in records
                   if kw in r.get("command", "").lower()
                   or kw in r.get("output_preview", "").lower()
                   or kw in r.get("cwd", "").lower()]

    if args.session:
        records = [r for r in records
                   if r.get("session_id", "").startswith(args.session)]

    if args.tail:
        records = records[-args.tail:]

    if not records:
        print(f"{YELLOW}No matching records.{RESET}")
        sys.exit(0)

    # Output
    if args.json:
        format_json(records)
        return

    # Build PRE → reasoning index for POST inheritance
    pre_index = {
        r["command"]: r["reasoning"]
        for r in records
        if r.get("phase") == "pre" and r.get("reasoning")
    }

    print(f"\n{BOLD}Agent Audit — {source}{RESET}  ({len(records)} records)\n")
    for i, r in enumerate(records, 1):
        print(format_record(r, i, len(records), pre_index=pre_index))

    # Summary
    sessions = {r.get("session_id") for r in records}
    cwds     = {r.get("cwd") for r in records}
    print(f"{DIM}─── {len(records)} entries · {len(sessions)} session(s) · {len(cwds)} cwd(s) ───{RESET}\n")


if __name__ == "__main__":
    main()
