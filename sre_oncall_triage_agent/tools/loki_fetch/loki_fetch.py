#!/usr/bin/env python3
"""
Loki log fetcher - directly queries Loki HTTP API.

Usage:
  Mode 1: Parse Grafana Explore URL and fetch logs
    python3 loki_fetch.py <grafana_explore_url> [options]

  Mode 2: Direct LogQL query
    python3 loki_fetch.py --expr '{app="myapp"}' [options]
    python3 loki_fetch.py --expr '{app="myapp"}' --from now-2h --to now-30m

Output:
  Formatted log lines to stdout:
    2026-03-31 10:00:01 | ERROR something failed

Environment:
  LOKI_URL      Loki base URL (required — no hardcoded default)
  LOKI_ORG_ID   X-Scope-OrgID header (default: fake)
"""

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone


LOKI_URL_DEFAULT = os.environ.get("LOKI_URL", "")
LOKI_ORG_ID_DEFAULT = os.environ.get("LOKI_ORG_ID", "fake")


# ---------------------------------------------------------------------------
# URL parsing (Grafana Explore URL → LogQL params)
# ---------------------------------------------------------------------------

def parse_grafana_url(url: str) -> dict:
    """Extract LogQL query, time range, and direction from a Grafana Explore URL."""
    parsed = urllib.parse.urlparse(url)
    params = urllib.parse.parse_qs(parsed.query)
    panes_raw = params.get("panes", [None])[0]
    if not panes_raw:
        raise ValueError("No 'panes' parameter found in URL")
    panes = json.loads(panes_raw)
    pane = next(iter(panes.values()))
    query_obj = pane["queries"][0]
    time_range = pane.get("range", {"from": "now-1h", "to": "now"})
    return {
        "expr": query_obj["expr"],
        "direction": query_obj.get("direction", "backward"),
        "time_from": time_range.get("from", "now-1h"),
        "time_to": time_range.get("to", "now"),
        "datasource_uid": query_obj.get("datasource", {}).get("uid", ""),
    }


# ---------------------------------------------------------------------------
# Time helpers
# ---------------------------------------------------------------------------

def resolve_time_ns(t: str) -> int:
    """Convert Grafana relative/absolute time string to Unix nanoseconds."""
    now = int(time.time())

    if t == "now":
        return now * 10**9

    # Relative: now-1h, now-30m, now-5s, now-7d
    m = re.match(r"now-(\d+)([smhd])", t)
    if m:
        val, unit = int(m.group(1)), m.group(2)
        mult = {"s": 1, "m": 60, "h": 3600, "d": 86400}[unit]
        return (now - val * mult) * 10**9

    # ISO 8601: 2026-03-31T10:00:00Z or 2026-03-31T10:00:00+00:00
    if re.match(r"^\d{4}-\d{2}-\d{2}T", t):
        dt = datetime.fromisoformat(t.replace("Z", "+00:00"))
        return int(dt.timestamp()) * 10**9

    # Grafana absolute timestamp (milliseconds)
    if t.isdigit():
        return int(t) * 10**6

    raise ValueError(f"Cannot parse time: {t!r}")


def ns_to_str(ns: int) -> str:
    return datetime.fromtimestamp(ns / 10**9, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


# ---------------------------------------------------------------------------
# Loki HTTP query
# ---------------------------------------------------------------------------

def query_loki(
    loki_url: str,
    org_id: str,
    expr: str,
    start_ns: int,
    end_ns: int,
    limit: int = 200,
    direction: str = "backward",
) -> dict:
    """Call /loki/api/v1/query_range and return the parsed JSON response."""
    params = urllib.parse.urlencode({
        "query": expr,
        "start": str(start_ns),
        "end": str(end_ns),
        "limit": str(limit),
        "direction": direction,
    })
    url = f"{loki_url.rstrip('/')}/loki/api/v1/query_range?{params}"
    req = urllib.request.Request(url, headers={"X-Scope-OrgID": org_id})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        raise RuntimeError(f"Loki HTTP {e.code}: {body}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"Cannot reach Loki at {loki_url}: {e.reason}") from e


# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------

def format_streams(data: dict, json_output: bool = False) -> list[str]:
    """Return sorted list of formatted log lines from Loki response."""
    results = data.get("data", {}).get("result", [])
    entries: list[tuple[int, str]] = []

    for stream in results:
        stream_labels = stream.get("stream", {})
        for ts_ns_str, log_line in stream.get("values", []):
            ts_ns = int(ts_ns_str)
            if json_output:
                entry = json.dumps({
                    "timestamp": ns_to_str(ts_ns),
                    "labels": stream_labels,
                    "line": log_line,
                }, ensure_ascii=False)
            else:
                entry = f"{ns_to_str(ts_ns)} | {log_line}"
            entries.append((ts_ns, entry))

    entries.sort(key=lambda x: x[0])
    return [e for _, e in entries]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Fetch logs from Loki directly (no Grafana MCP dependency).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument(
        "url_or_expr",
        nargs="?",
        help="Grafana Explore URL (containing 'panes=') or LogQL expression",
    )
    p.add_argument("--expr", help="LogQL expression (alternative to positional arg)")
    p.add_argument("--from", dest="from_time", default="now-1h",
                   help="Start time: now-1h | now-30m | ISO8601 (default: now-1h)")
    p.add_argument("--to", dest="to_time", default="now",
                   help="End time: now | ISO8601 (default: now)")
    p.add_argument("--loki-url", default=LOKI_URL_DEFAULT,
                   help="Loki base URL (default: $LOKI_URL env var)")
    p.add_argument("--org-id", default=LOKI_ORG_ID_DEFAULT,
                   help=f"X-Scope-OrgID header (default: {LOKI_ORG_ID_DEFAULT})")
    p.add_argument("--limit", type=int, default=200,
                   help="Max log lines to fetch (default: 200)")
    p.add_argument("--direction", default="backward",
                   choices=["backward", "forward"],
                   help="Log order (default: backward = newest first)")
    p.add_argument("--json", action="store_true",
                   help="Output NDJSON instead of plain text")
    p.add_argument("--dry-run", action="store_true",
                   help="Print resolved query params without fetching")
    return p


def main():
    parser = build_parser()
    args = parser.parse_args()

    # --- Resolve expression and time range ---
    raw = args.url_or_expr or ""
    if raw and "panes=" in raw:
        # Mode 1: Grafana Explore URL
        parsed = parse_grafana_url(raw)
        expr = parsed["expr"]
        start_ns = resolve_time_ns(parsed["time_from"])
        end_ns = resolve_time_ns(parsed["time_to"])
        direction = parsed["direction"]
    else:
        expr = args.expr or raw
        if not expr:
            parser.print_help()
            sys.exit(1)
        start_ns = resolve_time_ns(args.from_time)
        end_ns = resolve_time_ns(args.to_time)
        direction = args.direction

    if not args.loki_url:
        print("ERROR: --loki-url or LOKI_URL env var is required", file=sys.stderr)
        sys.exit(1)

    if args.dry_run:
        print(json.dumps({
            "loki_url": args.loki_url,
            "org_id": args.org_id,
            "expr": expr,
            "start": ns_to_str(start_ns),
            "end": ns_to_str(end_ns),
            "limit": args.limit,
            "direction": direction,
        }, indent=2))
        return

    # --- Fetch ---
    try:
        data = query_loki(
            args.loki_url, args.org_id,
            expr, start_ns, end_ns,
            args.limit, direction,
        )
    except RuntimeError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    lines = format_streams(data, json_output=args.json)

    if not lines:
        stats = data.get("data", {}).get("stats", {})
        print(
            f"[no logs found]  expr={expr!r}  "
            f"start={ns_to_str(start_ns)}  end={ns_to_str(end_ns)}",
            file=sys.stderr,
        )
        sys.exit(1)

    for line in lines:
        print(line)


if __name__ == "__main__":
    main()
