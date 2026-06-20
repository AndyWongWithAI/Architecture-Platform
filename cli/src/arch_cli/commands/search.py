"""arch search / use / tree — 高频查询命令"""
from __future__ import annotations

import sys

import click

from ..client import ArchClient
from ..config import Config
from ..output import make_console, print_components, print_json, print_tree, print_usage


@click.command(name="search", help="跨实体关键字搜索(components/versions/feedbacks)")
@click.argument("query")
@click.option("--format", "fmt", type=click.Choice(["table", "json"]), default=None)
def search_cmd(query, fmt):
    cfg = Config.load()
    if fmt:
        cfg.output_format = fmt
    console = make_console(cfg.output_color)
    client = ArchClient(cfg)

    data = client.search(query)
    if cfg.output_format == "json":
        print_json(data, console)
        return

    console.print(f"[bold]搜索:[/bold] {query}")
    console.print(f"[dim]共 {data.get('total', 0)} 个匹配[/dim]")

    if data.get("components"):
        console.print("\n[bold cyan]组件:[/bold cyan]")
        print_components(data["components"], console)

    if data.get("versions"):
        console.print(f"\n[bold cyan]版本:[/bold cyan] {len(data['versions'])} 条")
        for v in data["versions"][:10]:
            console.print(f"  - {v.get('component_name', '?')} {v.get('version', '?')}")

    if data.get("feedbacks"):
        console.print(f"\n[bold cyan]反馈:[/bold cyan] {len(data['feedbacks'])} 条")
        for f in data["feedbacks"][:10]:
            console.print(f"  - [{f.get('severity', '?')}] {f.get('bug_summary', '?')[:60]}")


@click.command(name="use", help="查看组件安装指引(Install/Import/Example)")
@click.argument("name")
def use_cmd(name):
    cfg = Config.load()
    console = make_console(cfg.output_color)
    client = ArchClient(cfg)

    try:
        usage = client.get_usage(name)
    except Exception as e:
        console.print(f"[red]✗ 查询失败:[/red] {e}")
        sys.exit(1)

    console.rule(f"[bold cyan]{name}[/bold cyan]")
    print_usage(usage, console)


@click.command(name="tree", help="展开组件依赖树")
@click.argument("name")
def tree_cmd(name):
    cfg = Config.load()
    console = make_console(cfg.output_color)
    client = ArchClient(cfg)

    try:
        tree = client.get_tree(name)
    except Exception as e:
        console.print(f"[red]✗ 查询失败:[/red] {e}")
        sys.exit(1)

    console.rule(f"[bold cyan]{name} 依赖树[/bold cyan]")
    print_tree(tree, console)