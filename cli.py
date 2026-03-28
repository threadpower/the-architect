"""
The Architect — CLI
Command line interface for task submission, status, budget, and guardrails.

Usage:
    architect submit --file task.yaml
    architect run "Build a BTC price fetcher" --type code
    architect status <task_id>
    architect list --status active
    architect budget
    architect guardrails
    architect health
"""
import typer
import httpx
import json
import yaml
from pathlib import Path
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

app = typer.Typer(
    name="architect",
    help="The Architect — Sovereign Development & Autonomy Platform",
)
console = Console()
BASE_URL = "http://localhost:8000"


@app.command()
def health():
    """Check platform health."""
    try:
        r = httpx.get(f"{BASE_URL}/health", timeout=5.0)
        data = r.json()

        color = "green" if data["status"] == "healthy" else "yellow"
        console.print(Panel(
            f"[bold]{data['platform']}[/bold] v{data['version']}\n"
            f"Status: [{color}]{data['status']}[/{color}]\n"
            f"Guardrails: v{data['guardrail_version']}",
            title="Health Check",
            border_style=color,
        ))

        table = Table(show_header=True)
        table.add_column("Component")
        table.add_column("Status")
        for comp, status in data["components"].items():
            s_color = "green" if status in ("up", "verified", "configured") else "red"
            table.add_row(comp, f"[{s_color}]{status}[/{s_color}]")
        console.print(table)

    except httpx.ConnectError:
        console.print("[red]Cannot connect to The Architect. Is it running?[/red]")
        console.print("Start with: uvicorn architect.main:app --port 8000")
        raise typer.Exit(1)


@app.command()
def submit(
    file: Path = typer.Option(None, "--file", "-f", help="YAML task file"),
    name: str = typer.Option(None, "--name", "-n", help="Task name (for inline)"),
    description: str = typer.Argument(None, help="Task description (inline mode)"),
    task_type: str = typer.Option("code", "--type", "-t"),
    primary: str = typer.Option(None, "--primary", "-p"),
    reviewer: str = typer.Option(None, "--reviewer", "-r"),
):
    """Submit a new task."""
    if file:
        content = file.read_text()
        r = httpx.post(
            f"{BASE_URL}/tasks/yaml",
            params={"yaml_content": content},
            timeout=10.0,
        )
    elif description:
        task_data = {
            "name": name or description[:60],
            "description": description,
            "type": task_type,
            "models": {},
        }
        if primary:
            task_data["models"]["primary"] = primary
        if reviewer:
            task_data["models"]["reviewer"] = reviewer

        r = httpx.post(f"{BASE_URL}/tasks", json=task_data, timeout=10.0)
    else:
        console.print("[red]Provide either --file or a description[/red]")
        raise typer.Exit(1)

    data = r.json()
    console.print(Panel(
        f"Task ID: [bold]{data['task_id']}[/bold]\n"
        f"Status: {data['status']}\n"
        f"Routing: {json.dumps(data.get('routing', {}), indent=2)}",
        title="Task Submitted",
        border_style="green",
    ))


@app.command()
def run(task_id: str):
    """Execute a submitted task."""
    console.print(f"Running task [bold]{task_id}[/bold]...")

    try:
        r = httpx.post(f"{BASE_URL}/tasks/{task_id}/run", timeout=300.0)
        data = r.json()

        color = "green" if data["status"] == "complete" else "yellow"
        console.print(Panel(
            f"Status: [{color}]{data['status']}[/{color}]\n"
            f"Iterations: {data['iterations']}\n"
            f"Cost: ${data['total_cost_usd']:.4f}\n\n"
            f"Output preview:\n{data.get('output_preview', 'N/A')}",
            title=f"Task {task_id} Result",
            border_style=color,
        ))
    except httpx.ReadTimeout:
        console.print("[yellow]Task is still running (timeout exceeded). "
                      "Check status with: architect status {task_id}[/yellow]")


@app.command()
def status(task_id: str):
    """Check task status and details."""
    r = httpx.get(f"{BASE_URL}/tasks/{task_id}", timeout=5.0)
    if r.status_code == 404:
        console.print(f"[red]Task {task_id} not found[/red]")
        raise typer.Exit(1)

    data = r.json()
    console.print(Panel(
        f"Name: {data['name']}\n"
        f"Type: {data['type']}\n"
        f"Status: {data['status']}\n"
        f"Priority: {data['priority']}\n"
        f"Cost: ${data.get('actual_cost_usd', 0):.4f}\n"
        f"Iterations: {data.get('iteration_count', 0)}\n"
        f"Created: {data['created_at']}",
        title=f"Task {task_id}",
    ))


@app.command(name="list")
def list_tasks(
    task_status: str = typer.Option(None, "--status", "-s"),
    limit: int = typer.Option(20, "--limit", "-l"),
):
    """List tasks."""
    params = {"limit": limit}
    if task_status:
        params["status"] = task_status

    r = httpx.get(f"{BASE_URL}/tasks", params=params, timeout=5.0)
    data = r.json()

    table = Table(title=f"Tasks ({data['count']} found)", show_header=True)
    table.add_column("ID", style="bold")
    table.add_column("Name")
    table.add_column("Type")
    table.add_column("Status")
    table.add_column("Cost")

    for t in data["tasks"]:
        s_color = {
            "complete": "green", "failed": "red", "paused": "yellow",
            "pending": "dim", "dispatched": "cyan",
        }.get(t["status"], "white")

        table.add_row(
            t["id"][-12:],
            t["name"][:40],
            t["type"],
            f"[{s_color}]{t['status']}[/{s_color}]",
            f"${t['cost']:.4f}",
        )

    console.print(table)


@app.command()
def budget():
    """Show today's budget report."""
    r = httpx.get(f"{BASE_URL}/budget", timeout=5.0)
    data = r.json()
    report = data["report"]

    console.print(Panel(
        "[bold]THE ARCHITECT — Cost Center[/bold]",
        border_style="bright_yellow",
    ))

    table = Table(show_header=True, title="Today's Spend")
    table.add_column("Provider")
    table.add_column("Spent", justify="right")
    table.add_column("Limit", justify="right")
    table.add_column("Usage", justify="right")

    for provider, info in report.get("providers", {}).items():
        pct = info["percentage"]
        color = "green" if pct < 70 else "yellow" if pct < 90 else "red"
        bar = "█" * int(pct / 10) + "░" * (10 - int(pct / 10))
        table.add_row(
            provider,
            f"${info['spent']:.2f}",
            f"${info['limit']:.2f}",
            f"[{color}]{bar} {pct:.0f}%[/{color}]",
        )

    console.print(table)

    # Savings
    savings = report.get("local_savings", 0)
    local_tasks = report.get("local_tasks", 0)
    if savings > 0 or local_tasks > 0:
        console.print(f"\n  Local tasks today: [bold]{local_tasks}[/bold]")
        console.print(
            f"  Estimated cloud cost avoided: "
            f"[bold green]${savings:.2f}[/bold green]"
        )

    if data.get("warning"):
        console.print(f"\n  [yellow]⚠ {data['warning']}[/yellow]")

    if data.get("local_only_mode"):
        console.print(
            "\n  [red]LOCAL ONLY MODE — budget threshold reached[/red]"
        )


@app.command()
def guardrails():
    """View active guardrails and integrity status."""
    r = httpx.get(f"{BASE_URL}/guardrails", timeout=5.0)
    data = r.json()

    integrity_color = "green" if data["integrity"] == "verified" else "red"
    console.print(Panel(
        f"Version: {data['version']}\n"
        f"Hash: {data['hash'][:32]}...\n"
        f"Integrity: [{integrity_color}]{data['integrity']}[/{integrity_color}]",
        title="Guardrail Kernel",
        border_style=integrity_color,
    ))

    g = data["guardrails"]

    console.print("\n[bold]Self-Improvement Allowed:[/bold]")
    for item in g.get("self_improve_allowed", []):
        console.print(f"  [green]✓[/green] {item}")

    console.print("\n[bold]Requires Human Approval:[/bold]")
    for item in g.get("requires_human_approval", []):
        console.print(f"  [yellow]⚡[/yellow] {item}")

    console.print("\n[bold]Explicitly Forbidden:[/bold]")
    for item in g.get("explicitly_forbidden", []):
        console.print(f"  [red]✗[/red] {item}")


@app.command()
def history(task_id: str):
    """View iteration history for a task."""
    r = httpx.get(f"{BASE_URL}/tasks/{task_id}/log", timeout=5.0)
    data = r.json()

    console.print(f"\n[bold]Event Log — {task_id}[/bold]\n")
    for event in data.get("events", []):
        ts = event.get("timestamp", "")[:19]
        ev = event.get("event", "")
        color = {
            "routed": "cyan", "iteration_start": "blue",
            "converged": "green", "complete": "green",
            "error": "red", "blocked": "red",
            "budget_warning": "yellow", "budget_exceeded": "red",
        }.get(ev, "white")

        console.print(f"  {ts}  [{color}]{ev:20}[/{color}]  {json.dumps(event.get('data', {}))}")


if __name__ == "__main__":
    app()
