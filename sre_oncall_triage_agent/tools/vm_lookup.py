#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Iterable


DEFAULT_BASE_URL = os.environ.get("VM_BASE_URL", "https://victoriametrics.example.com")
DEFAULT_QUERY_PATH = "/prometheus/api/v1/query"


@dataclass(frozen=True)
class VmClient:
    base_url: str
    query_path: str
    timeout_s: float

    def query(self, promql: str) -> dict[str, Any]:
        query = urllib.parse.urlencode({"query": promql})
        url = f"{self.base_url}{self.query_path}?{query}"
        request = urllib.request.Request(
            url,
            headers={
                "Accept": "application/json",
                "User-Agent": "infra-tools/vm_lookup.py",
            },
        )
        with urllib.request.urlopen(request, timeout=self.timeout_s) as response:
            body = response.read().decode("utf-8")
        payload = json.loads(body)
        if payload.get("status") != "success":
            raise RuntimeError(payload.get("error") or "unknown error")
        return payload


def _now_unix() -> int:
    return int(time.time())


def _extract_vector_metrics(payload: dict[str, Any]) -> list[dict[str, Any]]:
    data = payload.get("data") or {}
    result_type = data.get("resultType")
    if result_type != "vector":
        raise RuntimeError(f"unsupported resultType: {result_type!r}")
    result = data.get("result") or []
    if not isinstance(result, list):
        raise RuntimeError("unexpected result shape")
    return result


def _unique(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out


def _pod_regex_for_service(service: str) -> str:
    normalized = service.strip().lower()
    if normalized in {"fp", "fp-async", "fp-cron"}:
        if normalized == "fp":
            return r"fp-.*"
        if normalized == "fp-async":
            return r"fp-async-.*"
        if normalized == "fp-cron":
            return r"fp-cron-.*"
    return rf"{re_escape(normalized)}-.*"


def re_escape(value: str) -> str:
    # minimal regex escaping for pod name prefixes
    special = r"\.^$|?*+()[]{}"
    escaped = []
    for ch in value:
        if ch in special:
            escaped.append("\\" + ch)
        else:
            escaped.append(ch)
    return "".join(escaped)


def _build_pod_info_query(
    *,
    pod_regex: str,
    cluster: str | None,
    cluster_label: str | None,
) -> str:
    selectors: list[str] = [f'pod=~"{pod_regex}"']
    if cluster and cluster_label:
        selectors.append(f'{cluster_label}="{cluster}"')
    selector = ",".join(selectors)
    # kube_pod_info is the cleanest signal when present; it includes namespace/pod labels.
    return f"topk(200, max by (namespace, pod) (kube_pod_info{{{selector}}}))"


def _query_pods_candidates(
    client: VmClient,
    *,
    pod_regex: str,
    cluster: str | None,
    prefer_namespace: str | None,
) -> dict[str, Any]:
    if cluster:
        # Prefer applying a cluster filter when the caller provided one.
        cluster_label_candidates = ["kubernetes_cluster", "cluster", None]
    else:
        cluster_label_candidates = [None, "kubernetes_cluster", "cluster"]

    attempts: list[dict[str, Any]] = []
    for cluster_label in cluster_label_candidates:
        promql = _build_pod_info_query(
            pod_regex=pod_regex,
            cluster=cluster,
            cluster_label=cluster_label,
        )
        try:
            payload = client.query(promql)
            vector = _extract_vector_metrics(payload)
            if vector:
                attempts.append(
                    {
                        "cluster_label_used": cluster_label,
                        "query": promql,
                        "result_count": len(vector),
                    }
                )
                rows = []
                for item in vector:
                    metric = item.get("metric") or {}
                    namespace = metric.get("namespace")
                    pod = metric.get("pod")
                    if not namespace or not pod:
                        continue
                    rows.append({"namespace": namespace, "pod": pod})

                if prefer_namespace:
                    rows.sort(
                        key=lambda r: (
                            0 if r["namespace"] == prefer_namespace else 1,
                            r["namespace"],
                            r["pod"],
                        )
                    )
                else:
                    rows.sort(key=lambda r: (r["namespace"], r["pod"]))

                return {
                    "ok": True,
                    "base_url": client.base_url,
                    "endpoint": client.query_path,
                    "cluster": cluster,
                    "pod_regex": pod_regex,
                    "prefer_namespace": prefer_namespace,
                    "attempts": attempts,
                    "pods": rows,
                    "ts": _now_unix(),
                }

            attempts.append(
                {
                    "cluster_label_used": cluster_label,
                    "query": promql,
                    "result_count": 0,
                }
            )
        except Exception as exc:  # noqa: BLE001 - tool should surface errors as data
            attempts.append(
                {
                    "cluster_label_used": cluster_label,
                    "query": promql,
                    "error": str(exc),
                }
            )

    return {
        "ok": False,
        "base_url": client.base_url,
        "endpoint": client.query_path,
        "cluster": cluster,
        "pod_regex": pod_regex,
        "prefer_namespace": prefer_namespace,
        "attempts": attempts,
        "pods": [],
        "ts": _now_unix(),
    }


def cmd_pods(args: argparse.Namespace) -> int:
    client = VmClient(
        base_url=args.base_url.rstrip("/"),
        query_path=args.query_path,
        timeout_s=args.timeout_s,
    )
    pod_regex = args.pod_regex or _pod_regex_for_service(args.service)
    payload = _query_pods_candidates(
        client,
        pod_regex=pod_regex,
        cluster=args.cluster,
        prefer_namespace=args.prefer_namespace,
    )
    json.dump(payload, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0 if payload.get("ok") else 2


def cmd_namespace_from_pod(args: argparse.Namespace) -> int:
    client = VmClient(
        base_url=args.base_url.rstrip("/"),
        query_path=args.query_path,
        timeout_s=args.timeout_s,
    )
    promql = f'max by (namespace) (kube_pod_info{{pod="{args.pod}"}})'
    payload = client.query(promql)
    vector = _extract_vector_metrics(payload)
    namespaces = _unique(
        (item.get("metric") or {}).get("namespace")
        for item in vector
        if (item.get("metric") or {}).get("namespace")
    )
    out = {
        "ok": True,
        "base_url": client.base_url,
        "endpoint": client.query_path,
        "query": promql,
        "pod": args.pod,
        "namespaces": namespaces,
        "ts": _now_unix(),
    }
    json.dump(out, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="vm_lookup.py",
        description="Read-only VictoriaMetrics lookup helper (Prometheus-compatible API).",
    )
    parser.add_argument(
        "--base-url",
        default=DEFAULT_BASE_URL,
        help=f"Base URL (default: {DEFAULT_BASE_URL})",
    )
    parser.add_argument(
        "--query-path",
        default=DEFAULT_QUERY_PATH,
        help=f"Query API path (default: {DEFAULT_QUERY_PATH})",
    )
    parser.add_argument("--timeout-s", type=float, default=10.0, help="HTTP timeout seconds")

    sub = parser.add_subparsers(dest="cmd", required=True)

    pods = sub.add_parser("pods", help="Find candidate pods/namespaces for a service")
    pods.add_argument("--cluster", default=None, help="Cluster name (e.g., aws-useast1-prod-b)")
    pods.add_argument("--service", required=True, help="Service name (e.g., fp, fp-async, fp-cron)")
    pods.add_argument(
        "--pod-regex",
        default=None,
        help='Override pod regex (default derived from --service, e.g., "fp-.*")',
    )
    pods.add_argument(
        "--prefer-namespace",
        default=None,
        help="Sort results with this namespace first (does not filter).",
    )
    pods.set_defaults(func=cmd_pods)

    ns = sub.add_parser("namespace-from-pod", help="Find namespace for a specific pod name")
    ns.add_argument("--pod", required=True, help="Pod name")
    ns.set_defaults(func=cmd_namespace_from_pod)

    return parser


def main(argv: list[str]) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
