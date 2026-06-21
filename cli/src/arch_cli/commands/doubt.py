"""arch doubt — Phase 0 验证(doubt-driven-development 5 步法)

对齐 arch requirement 命令的风格与模式(reuse)
"""
from __future__ import annotations

import sys
from pathlib import Path

import click

from ..client import ArchClient
from ..config import Config
from ..output import make_console, print_json


@click.group(name="doubt", help="Doubt-Driven Development 5 步法(Phase 0 验证)")
def cli():
    pass


@cli.command(name="cycle", help="开一个 doubt cycle(CLAIM + EXTRACT)")
@click.option("--claim", required=True, help="2-3 行声明(决策 + 为什么重要)")
@click.option("--artifact", "artifact_file", type=click.Path(exists=True, dir_okay=False),
              help="artifact 文件路径(代码/决策)")
@click.option("--artifact-text", help="artifact 直接文本(与 --artifact 二选一)")
@click.option("--contract", "contract_file", type=click.Path(exists=True, dir_okay=False),
              help="contract 文件路径(期望行为)")
@click.option("--contract-text", help="contract 直接文本(与 --contract 二选一)")
@click.option("--component", help="关联组件名(可选)")
@click.option("--created-by", default="cli", help="创建人(默认 cli)")
@click.option("--format", "fmt", type=click.Choice(["json"]), default=None)
def cycle_cmd(claim, artifact_file, artifact_text, contract_file, contract_text, component, created_by, fmt):
    cfg = Config.load()
    if fmt:
        cfg.output_format = fmt
    console = make_console(cfg.output_color)
    client = ArchClient(cfg)

    # 二选一解析 artifact / contract
    if (artifact_file and artifact_text) or (not artifact_file and not artifact_text):
        console.print("[red]✗ 必须指定 --artifact FILE 或 --artifact-text TEXT(二选一)[/red]")
        sys.exit(1)
    artifact = Path(artifact_file).read_text() if artifact_file else artifact_text

    if (contract_file and contract_text) or (not contract_file and not contract_text):
        console.print("[red]✗ 必须指定 --contract FILE 或 --contract-text TEXT(二选一)[/red]")
        sys.exit(1)
    contract = Path(contract_file).read_text() if contract_file else contract_text

    payload = {
        "claim": claim,
        "artifact": artifact,
        "contract": contract,
        "created_by": created_by,
    }
    if component:
        payload["component_id"] = component

    try:
        cycle = client.create_doubt_cycle(payload)
    except Exception as e:
        console.print(f"[red]✗ 创建失败:[/red] {e}")
        sys.exit(1)

    cycle_id = cycle.get("id", "?")
    console.print(f"[green]✓[/green] doubt cycle 已创建: [bold]{cycle_id}[/bold]")
    console.print(f"[dim]下一步:arch doubt finding {cycle_id} --category actionable --severity critical --desc '...'[/dim]")


@cli.command(name="get", help="查 cycle 详情")
@click.argument("cycle_id")
def get_cmd(cycle_id):
    cfg = Config.load()
    console = make_console(cfg.output_color)
    client = ArchClient(cfg)
    try:
        cycle = client.get_doubt_cycle(cycle_id)
    except Exception as e:
        console.print(f"[red]✗ 查询失败:[/red] {e}")
        sys.exit(1)
    print_json(cycle, console)


@cli.command(name="finding", help="加 finding(RECONCILE 步骤)")
@click.argument("cycle_id")
@click.option("--category", required=True,
              type=click.Choice(["contract_misread", "actionable", "trade_off", "noise"]))
@click.option("--severity", default="medium",
              type=click.Choice(["low", "medium", "high", "critical"]))
@click.option("--desc", "description", required=True, help="finding 描述(10-5000 字符)")
def finding_cmd(cycle_id, category, severity, description):
    cfg = Config.load()
    console = make_console(cfg.output_color)
    client = ArchClient(cfg)

    payload = {
        "category": category,
        "severity": severity,
        "description": description,
    }
    try:
        finding = client.add_doubt_finding(cycle_id, payload)
    except Exception as e:
        console.print(f"[red]✗ 添加失败:[/red] {e}")
        sys.exit(1)
    console.print(f"[green]✓[/green] finding 已添加: [bold]{finding.get('id','?')[:8]}[/bold] ({category}/{severity})")


@cli.command(name="stop", help="STOP 步骤:主动 ship(用户决定停止)")
@click.argument("cycle_id")
@click.option("--reason", required=True, help="停止原因")
def stop_cmd(cycle_id, reason):
    cfg = Config.load()
    console = make_console(cfg.output_color)
    client = ArchClient(cfg)

    try:
        cycle = client.stop_doubt_cycle(cycle_id, {"reason": reason})
    except Exception as e:
        console.print(f"[red]✗ STOP 失败:[/red] {e}")
        sys.exit(1)
    console.print(f"[green]✓[/green] cycle 已停止: [bold]{cycle.get('id','?')[:8]}[/bold]")
    console.print(f"[dim]stopped_reason: {cycle.get('stopped_reason','?')}[/dim]")
