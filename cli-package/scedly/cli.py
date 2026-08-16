"""CLI entry point — all commands live here."""

import json
import sys
from datetime import date, datetime, time, timedelta

import click
import httpx

from .banner import print_logo
from .config import get_api_key, get_base_url, save_config


def _headers() -> dict:
    key = get_api_key()
    if not key:
        click.echo("Not logged in. Run: scedly login")
        sys.exit(1)
    return {"Authorization": f"Bearer {key}"}


def _url(path: str) -> str:
    return f"{get_base_url().rstrip('/')}/{path.lstrip('/')}"


@click.group(invoke_without_command=True)
@click.pass_context
def main(ctx):
    """scedly — your scheduling agent, in the terminal."""
    if ctx.invoked_subcommand is None:
        print_logo()
        click.echo("Type 'scedly --help' for commands.\n")


@main.command()
@click.option("--key", prompt="API key (sk-...)", hide_input=True)
@click.option(
    "--url", prompt="Base URL", default="http://localhost:8000", show_default=True
)
def login(key: str, url: str):
    """Save your API key and server URL."""
    save_config(api_key=key, base_url=url)
    click.echo("✓ Logged in. Config saved.")


@main.command()
@click.argument("message", nargs=-1, required=True)
def chat(message: tuple):
    """Send a message to the scheduling agent."""
    msg = " ".join(message)
    with httpx.stream(
        "POST",
        _url("/chat"),
        json={"message": msg, "session_id": "cli-session"},
        headers=_headers(),
        timeout=60,
    ) as resp:
        if resp.status_code != 200:
            click.echo(f"[Error {resp.status_code}] {resp.read().decode()}")
            return
        for line in resp.iter_lines():
            if not line.startswith("data: "):
                continue
            data = line[6:]
            if data == "[DONE]":
                break
            try:
                chunk = json.loads(data)
                if chunk.get("type") == "token":
                    click.echo(chunk["content"], nl=False)
            except json.JSONDecodeError:
                click.echo(data, nl=False)
        click.echo()


@main.command()
def schedule():
    """Show today's schedule."""
    today_start = datetime.combine(date.today(), time.min)
    tomorrow_start = today_start + timedelta(days=1)
    resp = httpx.get(
        _url("/calendar"),
        headers=_headers(),
        params={
            "start_date": today_start.isoformat(),
            "end_date": tomorrow_start.isoformat(),
        },
        timeout=15,
    )
    if resp.status_code != 200:
        click.echo(f"[Error {resp.status_code}] {resp.text}")
        return
    tasks = resp.json().get("blocks", [])
    if not tasks:
        click.echo("Nothing scheduled today.")
        return
    for t in tasks:
        click.echo(f"  {t['start'][11:16]} – {t['end'][11:16]}  {t['title']}")


@main.command()
@click.option(
    "--status",
    type=click.Choice(["all", "scheduled", "completed", "unscheduled"]),
    default="all",
)
def tasks(status: str):
    """List your tasks."""
    params = {} if status == "all" else {"status_filter": status}
    resp = httpx.get(_url("/tasks"), headers=_headers(), params=params, timeout=15)
    if resp.status_code != 200:
        click.echo(f"[Error {resp.status_code}] {resp.text}")
        return
    payload = resp.json()
    if status == "all":
        task_list = [
            task
            for section in ("pending", "in_progress", "done_this_week")
            for task in payload.get(section, [])
        ]
    else:
        task_list = payload.get("tasks", [])
    if not task_list:
        click.echo("No tasks found.")
        return
    for t in task_list:
        icon = "✓" if t.get("status") == "completed" else "○"
        click.echo(
            f"  {icon} {t['title']} ({t.get('duration_minutes', '?')}min, {t.get('priority', '?')})"
        )


if __name__ == "__main__":
    main()
