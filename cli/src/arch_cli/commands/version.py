"""arch version — 版本管理"""
from __future__ import annotations

import sys

import click

from ..client import ArchClient
from ..config import Config
from ..output import make_console, print_json, print_versions


@click.group(name="version", help="Component 版本管理")
def cli():
    pass


@cli.command(name="list", help="列出组件的所有版本")
@click.argument("component_name")
@click.option("--format", "fmt", type=click.Choice(["table", "json"]), default=None)
def list_cmd(component_name, fmt):
    cfg = Config.load()
    if fmt:
        cfg.output_format = fmt
    console = make_console(cfg.output_color)
    client = ArchClient(cfg)

    data = client.list_versions(component_name)
    versions = data.get("items", [])
    if cfg.output_format == "json":
        print_json(versions, console)
    else:
        print_versions(versions, console)


@cli.command(name="get", help="按 version_id 取版本详情")
@click.argument("version_id")
def get_cmd(version_id):
    cfg = Config.load()
    console = make_console(cfg.output_color)
    client = ArchClient(cfg)
    data = client.get_version(version_id)
    print_json(data, console)


@cli.command(name="create", help="创建新版本")
@click.argument("component_name")
@click.option("--version", "version_str", required=True, help="SemVer,如 1.2.0")
@click.option("--intent", "semver_intent", required=True, type=click.Choice(["major", "minor", "patch"]))
@click.option("--changelog", required=True, help="变更说明")
@click.option("--breaking-changes", help="破坏性变更(major 必填)")
@click.option("--compatibility-window", help="兼容期,如 'LTS until 2027-06'")
@click.option("--replaces", help="替代的旧版本号")
def create_cmd(component_name, version_str, semver_intent, changelog, breaking_changes,
               compatibility_window, replaces):
    cfg = Config.load()
    console = make_console(cfg.output_color)
    client = ArchClient(cfg)

    data = {
        "version": version_str,
        "semver_intent": semver_intent,
        "changelog": changelog,
    }
    if breaking_changes:
        data["breaking_changes"] = breaking_changes
    if compatibility_window:
        data["compatibility_window"] = compatibility_window
    if replaces:
        data["replaces_version"] = replaces

    try:
        result = client.create_version(component_name, data)
    except Exception as e:
        console.print(f"[red]✗ 创建失败:[/red] {e}")
        sys.exit(1)

    console.print(f"[green]✓ 版本已创建:[/green] {component_name} {result['version']} (id={result['id'][:8]}...)")
    if result.get("breaking_changes"):
        console.print(f"  [yellow]breaking_changes:[/yellow] {result['breaking_changes'][:80]}")