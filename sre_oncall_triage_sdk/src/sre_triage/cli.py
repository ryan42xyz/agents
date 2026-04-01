"""CLI entry point for the SRE oncall triage agent.

Usage:
    sre-triage --alert "alert text here"
    sre-triage --alert-file /path/to/alert.txt
    echo "alert text" | sre-triage --alert -
"""

from __future__ import annotations

import sys
from pathlib import Path

import click

from .agent import TriageAgent
from .config import Config


@click.command()
@click.option(
    "--alert",
    type=str,
    default=None,
    help="Alert text (use '-' to read from stdin)",
)
@click.option(
    "--alert-file",
    type=click.Path(exists=True, path_type=Path),
    default=None,
    help="Path to file containing alert text",
)
@click.option(
    "--model",
    type=str,
    default=None,
    help="Override model (default: from config)",
)
@click.option(
    "--backend",
    type=click.Choice(["http", "mcp"]),
    default=None,
    help="Tool backend (default: from config)",
)
@click.option(
    "--llm",
    type=click.Choice(["api", "opencode"]),
    default=None,
    help="LLM backend: 'api' (Anthropic SDK) or 'opencode' (local OpenCode server, no API key needed)",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Print system prompt and exit without calling API",
)
def main(
    alert: str | None,
    alert_file: Path | None,
    model: str | None,
    backend: str | None,
    llm: str | None,
    dry_run: bool,
) -> None:
    """SRE Oncall Triage Agent — Standalone SDK implementation."""
    # Resolve alert text
    alert_text = _resolve_alert(alert, alert_file)
    if not alert_text:
        click.echo("Error: provide alert via --alert, --alert-file, or stdin", err=True)
        sys.exit(1)

    # If using claude-code, set LLM_BACKEND before config loads
    import os
    if llm:
        os.environ["LLM_BACKEND"] = llm

    # Load config
    project_root = Path(__file__).parent.parent.parent
    config = Config.from_env(project_root)

    # Apply CLI overrides via dataclass replace
    overrides = {}
    if model:
        overrides["model"] = model
    if backend:
        overrides["tool_backend"] = backend
    if llm:
        overrides["llm_backend"] = llm
    if overrides:
        from dataclasses import replace
        config = replace(config, **overrides)

    # Dry run: print system prompt and exit
    if dry_run:
        from .context.knowledge import KnowledgeLoader
        knowledge = KnowledgeLoader(config.knowledge_base_path, config.facets_path)
        click.echo("=== System Prompt ===")
        click.echo(f"Model: {config.model}")
        click.echo(f"Backend: {config.tool_backend}")
        click.echo(f"Knowledge: {config.knowledge_base_path}")
        click.echo()
        routing = knowledge.load_routing_table()
        click.echo(f"Routing table loaded: {len(routing)} chars")
        click.echo()
        click.echo("=== Alert Text ===")
        click.echo(alert_text)
        return

    # Run investigation
    agent = TriageAgent(config)
    click.echo(f"Starting investigation (model={config.model}, backend={config.tool_backend})")
    click.echo(f"Alert: {alert_text[:100]}...")
    click.echo()

    result = agent.investigate(alert_text)

    # Print summary
    click.echo(f"\n{'='*60}")
    click.echo(f"Investigation complete")
    click.echo(f"  Turns: {result.turns}")
    click.echo(f"  Tokens: {result.total_input_tokens} in / {result.total_output_tokens} out")
    if result.output_path:
        click.echo(f"  Output: {result.output_path}")
    if result.trace_path:
        click.echo(f"  Trace: {result.trace_path}")
    click.echo(f"{'='*60}")


def _resolve_alert(alert: str | None, alert_file: Path | None) -> str:
    """Resolve alert text from various input sources."""
    if alert_file:
        return alert_file.read_text().strip()
    if alert == "-":
        return sys.stdin.read().strip()
    if alert:
        return alert.strip()

    # Try stdin if connected to a pipe
    if not sys.stdin.isatty():
        return sys.stdin.read().strip()

    return ""


if __name__ == "__main__":
    main()
