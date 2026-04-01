"""Configuration loaded from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Config:
    # Anthropic
    api_key: str
    model: str = "claude-sonnet-4-20250514"
    max_tokens: int = 4096
    max_turns: int = 20

    # LLM backend
    llm_backend: str = "api"  # "api" (Anthropic SDK) or "claude-code" (local CLI)

    # Tool backend
    tool_backend: str = "http"  # "http" or "mcp"

    # VictoriaMetrics
    vm_base_url: str = ""
    # Loki
    loki_url: str = ""
    loki_org_id: str = "prod"

    # Paths
    knowledge_base_path: Path = field(default_factory=lambda: Path("../sre_oncall_triage_agent/knowledge"))
    facets_path: Path = field(default_factory=lambda: Path("../sre_oncall_triage_agent/FACETS"))
    output_dir: Path = field(default_factory=lambda: Path("output"))
    trace_dir: Path = field(default_factory=lambda: Path("output/traces"))

    @classmethod
    def from_env(cls, project_root: Path | None = None) -> Config:
        """Load configuration from environment variables and .env file."""
        root = project_root or Path(__file__).parent.parent.parent
        env_file = root / ".env"
        if env_file.exists():
            _load_dotenv(env_file)

        llm_backend = os.environ.get("LLM_BACKEND", "api")
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not api_key and llm_backend != "claude-code":
            raise ValueError(
                "ANTHROPIC_API_KEY is required when LLM_BACKEND=api. "
                "Set it in .env, or use LLM_BACKEND=claude-code to use local Claude Code CLI."
            )

        def _resolve_path(env_var: str, default: str) -> Path:
            raw = os.environ.get(env_var, default)
            p = Path(raw)
            if not p.is_absolute():
                p = root / p
            return p

        return cls(
            api_key=api_key,
            model=os.environ.get("TRIAGE_MODEL", "claude-sonnet-4-20250514"),
            max_tokens=int(os.environ.get("TRIAGE_MAX_TOKENS", "4096")),
            max_turns=int(os.environ.get("TRIAGE_MAX_TURNS", "20")),
            llm_backend=llm_backend,
            tool_backend=os.environ.get("TOOL_BACKEND", "http"),
            vm_base_url=os.environ.get("VM_BASE_URL", ""),
            loki_url=os.environ.get("LOKI_URL", ""),
            loki_org_id=os.environ.get("LOKI_ORG_ID", "prod"),
            knowledge_base_path=_resolve_path("KNOWLEDGE_BASE_PATH", "../sre_oncall_triage_agent/knowledge"),
            facets_path=_resolve_path("FACETS_PATH", "../sre_oncall_triage_agent/FACETS"),
            output_dir=_resolve_path("OUTPUT_DIR", "output"),
            trace_dir=_resolve_path("TRACE_DIR", "output/traces"),
        )


def _load_dotenv(path: Path) -> None:
    """Minimal .env loader — no dependencies."""
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip("'\"")
        if key not in os.environ:  # don't override existing env vars
            os.environ[key] = value
