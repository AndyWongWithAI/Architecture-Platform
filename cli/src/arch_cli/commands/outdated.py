"""arch outdated / upgrade / lock — 版本管理

Phase 2.5:版本升级分析 + 锁定
"""
from __future__ import annotations

from typing import Optional

import click

from ..client import ArchClient
from ..config import Config
from ..output import make_console


@click.command(name="outdated", help="检查组件是否有可升级版本(基于 SemVer 约束)")
@click.option("--component", help="只检查指定组件(默认检查所有)")
def outdated_cmd(component):
    cfg = Config.load()
    console = make_console(cfg.output_color)
    client = ArchClient(cfg)

    # 简化实现:列出所有组件,看每个组件的版本情况
    if component:
        try:
            comp = client.get_component(component)
            components = [comp]
        except Exception as e:
            console.print(f"[red]✗ 组件不存在:[/red] {e}")
            return
    else:
        data = client.list_components()
        components = data.get("items", [])

    console.print(f"[bold]检查 {len(components)} 个组件的版本状态[/bold]\n")

    for c in components:
        name = c["name"]
        try:
            versions = client.list_versions(name).get("items", [])
        except Exception:
            continue

        if not versions:
            console.print(f"  [dim]{name}:[/dim] [yellow](无版本记录)[/yellow]")
            continue

        latest = max(versions, key=lambda v: v.get("created_at", ""))
        current_id = c.get("current_version_id")
        current = next((v for v in versions if v["id"] == current_id), None)

        if current and current["id"] == latest["id"]:
            console.print(f"  [green]{name}:[/green] 当前 {current['version']} [dim](up-to-date)[/dim]")
        else:
            current_v = current["version"] if current else "?"
            latest_v = latest["version"]
            semver = latest.get("semver_intent", "?")
            color = {"major": "red", "minor": "yellow", "patch": "green"}.get(semver, "white")
            console.print(
                f"  [cyan]{name}:[/cyan] {current_v} → {latest_v} "
                f"[{color}]({semver})[/{color}]"
            )


@click.command(name="lock", help="生成依赖 lockfile(.aip-lock.toml,Phase 2 占位)")
@click.option("--output", "-o", default=".aip-lock.toml", help="输出文件路径")
def lock_cmd(output):
    cfg = Config.load()
    console = make_console(cfg.output_color)
    client = ArchClient(cfg)

    data = client.list_components()
    components = data.get("items", [])

    lines = [
        "# arch-platform lockfile",
        f"# 生成时间:{__import__('datetime').datetime.now().isoformat()}",
        "",
        "[components]",
    ]
    for c in components:
        if c.get("current_version_id"):
            lines.append(f'{c["name"]} = {{ version = "TBD", resolved_at = "TBD" }}')

    with open(output, "w") as f:
        f.write("\n".join(lines) + "\n")

    console.print(f"[green]✓ Lockfile 已生成:[/green] {output} ({len(components)} 个组件)")