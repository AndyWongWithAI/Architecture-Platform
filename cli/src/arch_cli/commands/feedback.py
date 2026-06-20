"""arch feedback — Bug 反馈闭环"""
from __future__ import annotations

import sys

import click

from ..client import ArchClient
from ..config import Config
from ..output import make_console, print_feedbacks, print_json


@click.group(name="feedback", help="Feedback Bug 反馈闭环")
def cli():
    pass


@cli.command(name="list", help="列出反馈")
@click.option("--status", type=click.Choice(["open", "triaged", "fixing", "fixed", "wontfix"]))
@click.option("--severity", type=click.Choice(["low", "medium", "high", "critical"]))
@click.option("--component", help="按组件名过滤")
@click.option("--format", "fmt", type=click.Choice(["table", "json"]), default=None)
def list_cmd(status, severity, component, fmt):
    cfg = Config.load()
    if fmt:
        cfg.output_format = fmt
    console = make_console(cfg.output_color)
    client = ArchClient(cfg)

    params = {}
    if status:
        params["status"] = status
    if severity:
        params["severity"] = severity
    if component:
        params["component"] = component

    data = client.list_feedbacks(**params)
    items = data.get("items", [])
    if cfg.output_format == "json":
        print_json(items, console)
    else:
        print_feedbacks(items, console)
        console.print(f"[dim]共 {data.get('total', 0)} 条反馈[/dim]")


@cli.command(name="create", help="登记新反馈")
@click.argument("version_id")
@click.option("--summary", "bug_summary", required=True, help="Bug 摘要")
@click.option("--root-cause", help="根因分析")
@click.option("--fix-plan", help="修复方案")
@click.option("--severity", default="medium", type=click.Choice(["low", "medium", "high", "critical"]))
@click.option("--reporter", default="cli", help="报告人")
@click.option("--reused-in", help="影响面(项目名,逗号分隔)")
def create_cmd(version_id, bug_summary, root_cause, fix_plan, severity, reporter, reused_in):
    cfg = Config.load()
    console = make_console(cfg.output_color)
    client = ArchClient(cfg)

    data = {
        "reporter": reporter,
        "bug_summary": bug_summary,
        "severity": severity,
    }
    if root_cause:
        data["root_cause"] = root_cause
    if fix_plan:
        data["fix_plan"] = fix_plan
    if reused_in:
        data["reused_in_projects"] = [p.strip() for p in reused_in.split(",")]

    try:
        result = client.create_feedback(version_id, data)
    except Exception as e:
        console.print(f"[red]✗ 创建失败:[/red] {e}")
        sys.exit(1)

    console.print(f"[green]✓ 反馈已登记:[/green] {result['id'][:8]} ({severity})")
    console.print(f"  {result['bug_summary'][:60]}")


@cli.command(name="update", help="更新反馈(状态 / 决策 / 根因)")
@click.argument("feedback_id")
@click.option("--status", type=click.Choice(["open", "triaged", "fixing", "fixed", "wontfix"]))
@click.option("--decision", type=click.Choice(["optimize", "fork_new", "keep_as_is", "reassess_form"]))
@click.option("--root-cause", help="根因(转 fixed 时建议填)")
@click.option("--fix-plan", help="修复方案")
def update_cmd(feedback_id, status, decision, root_cause, fix_plan):
    cfg = Config.load()
    console = make_console(cfg.output_color)
    client = ArchClient(cfg)

    data = {}
    if status:
        data["status"] = status
    if decision:
        data["decision"] = decision
    if root_cause:
        data["root_cause"] = root_cause
    if fix_plan:
        data["fix_plan"] = fix_plan

    if not data:
        console.print("[yellow]未指定任何更新字段[/yellow]")
        sys.exit(1)

    try:
        result = client.patch_feedback(feedback_id, data)
    except Exception as e:
        console.print(f"[red]✗ 更新失败:[/red] {e}")
        sys.exit(1)

    console.print(f"[green]✓ 反馈已更新:[/green] {result['id'][:8]}")
    console.print(f"  status={result.get('status')} decision={result.get('decision') or '-'}")