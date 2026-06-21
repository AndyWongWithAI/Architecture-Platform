"""Rich 输出格式化:表格 / JSON / 颜色

支持两种模式:
- table(默认):rich.Table 漂亮输出
- json:原始 JSON,方便脚本处理
"""
from __future__ import annotations

import json
from typing import Any, Optional

from rich.console import Console
from rich.table import Table


def make_console(color: bool = True) -> Console:
    return Console(no_color=not color)


def print_json(data: Any, console: Console) -> None:
    """打印 JSON(pretty)"""
    console.print_json(json.dumps(data, ensure_ascii=False, indent=2))


def print_components(components: list[dict], console: Console) -> None:
    """打印组件列表(表格)"""
    if not components:
        console.print("[yellow](无组件)[/yellow]")
        return

    t = Table(title="组件", show_header=True, header_style="bold magenta")
    t.add_column("name", style="cyan", no_wrap=True)
    t.add_column("layer")
    t.add_column("category")
    t.add_column("asset", justify="center")
    t.add_column("form")
    t.add_column("title")

    for c in components:
        asset = "✓" if c.get("is_asset") else "✗"
        asset_style = "green" if c.get("is_asset") else "dim"
        t.add_row(
            c.get("name", ""),
            c.get("layer", ""),
            c.get("category", ""),
            f"[{asset_style}]{asset}[/{asset_style}]",
            c.get("distribution_form") or "-",
            (c.get("title") or "")[:40],
        )
    console.print(t)


def print_versions(versions: list[dict], console: Console) -> None:
    if not versions:
        console.print("[yellow](无版本)[/yellow]")
        return
    t = Table(title="版本", show_header=True, header_style="bold magenta")
    t.add_column("version", style="cyan")
    t.add_column("semver_intent")
    t.add_column("breaking_changes?", justify="center")
    t.add_column("created_at")
    for v in versions:
        has_breaking = "✓" if v.get("breaking_changes") else "-"
        t.add_row(
            v.get("version", ""),
            v.get("semver_intent", ""),
            has_breaking,
            v.get("created_at", "")[:19],
        )
    console.print(t)


def print_feedbacks(feedbacks: list[dict], console: Console) -> None:
    if not feedbacks:
        console.print("[yellow](无反馈)[/yellow]")
        return
    t = Table(title="反馈", show_header=True, header_style="bold magenta")
    t.add_column("id", style="dim", no_wrap=True)
    t.add_column("severity")
    t.add_column("status")
    t.add_column("decision")
    t.add_column("summary")

    sev_color = {"critical": "red", "high": "orange3", "medium": "yellow", "low": "green"}
    for f in feedbacks:
        sev = f.get("severity", "")
        sev_styled = f"[{sev_color.get(sev, 'white')}]{sev}[/{sev_color.get(sev, 'white')}]"
        t.add_row(
            (f.get("id") or "")[:8],
            sev_styled,
            f.get("status", ""),
            f.get("decision") or "-",
            (f.get("bug_summary") or "")[:50],
        )
    console.print(t)


def print_requirements(requirements: list[dict], console: Console) -> None:
    """打印需求列表(对齐 print_feedbacks 风格)"""
    if not requirements:
        console.print("[yellow](无需求)[/yellow]")
        return
    t = Table(title="需求", show_header=True, header_style="bold magenta")
    t.add_column("id", style="dim", no_wrap=True)
    t.add_column("priority")
    t.add_column("type")
    t.add_column("status")
    t.add_column("assignee")
    t.add_column("title")

    pri_color = {"P0": "red", "P1": "orange3", "P2": "yellow", "P3": "dim"}
    for r in requirements:
        pri = r.get("priority", "")
        pri_styled = f"[{pri_color.get(pri, 'white')}]{pri}[/{pri_color.get(pri, 'white')}]"
        t.add_row(
            (r.get("id") or "")[:8],
            pri_styled,
            r.get("type", ""),
            r.get("status", ""),
            r.get("assignee") or "-",
            (r.get("title") or "")[:50],
        )
    console.print(t)


def print_tree(node: dict, console: Console, indent: int = 0) -> None:
    """递归打印依赖树"""
    comp = node.get("component", {})
    name = comp.get("name", "")
    layer = comp.get("layer", "")
    atomic = "🟢" if comp.get("atomic") else "🔵"
    prefix = "  " * indent
    console.print(f"{prefix}{atomic} [cyan]{name}[/cyan] [dim]({layer})[/dim]")
    for child in node.get("children", []):
        print_tree(child, console, indent + 1)


def print_usage(usage: dict, console: Console) -> None:
    """打印 install + example 信息"""
    console.print(f"[bold]Install:[/bold]  {usage.get('install_command') or '(无)'}")
    console.print(f"[bold]Import:[/bold]   {usage.get('package_name') or '-'}")
    console.print(f"[bold]Example:[/bold]")
    console.print(f"  {usage.get('usage_example') or '(无)'}")
    console.print(f"[bold]Latest:[/bold]   {usage.get('current_version') or '-'}")