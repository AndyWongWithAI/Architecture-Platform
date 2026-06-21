"""arch requirement — Phase 1 需求登记与状态推进

对齐 arch feedback 命令的风格与模式(reuse)
"""
from __future__ import annotations

import sys

import click

from ..client import ArchClient
from ..config import Config
from ..output import make_console, print_requirements, print_json


@click.group(name="requirement", help="Requirement 需求登记(Phase 1)")
def cli():
    pass


@cli.command(name="list", help="列出需求")
@click.option("--status", type=click.Choice([
    "draft", "triaged", "scheduled", "in_progress",
    "implemented", "verified", "rejected", "cancelled",
]))
@click.option("--priority", type=click.Choice(["P0", "P1", "P2", "P3"]))
@click.option("--type", "req_type", type=click.Choice([
    "new_feature", "bug_fix", "refactor", "optimization", "compliance", "tech_debt",
]))
@click.option("--assignee", help="按负责人过滤")
@click.option("--component", help="按 component 名过滤")
@click.option("--include-archived", is_flag=True, help="包含已归档")
@click.option("--format", "fmt", type=click.Choice(["table", "json"]), default=None)
def list_cmd(status, priority, req_type, assignee, component, include_archived, fmt):
    cfg = Config.load()
    if fmt:
        cfg.output_format = fmt
    console = make_console(cfg.output_color)
    client = ArchClient(cfg)

    params = {}
    if status:
        params["status"] = status
    if priority:
        params["priority"] = priority
    if req_type:
        params["type"] = req_type
    if assignee:
        params["assignee"] = assignee
    if component:
        params["component_id"] = component
    if include_archived:
        params["include_archived"] = True

    data = client.list_requirements(**params)
    items = data.get("items", [])
    if cfg.output_format == "json":
        print_json(items, console)
    else:
        print_requirements(items, console)
        console.print(f"[dim]共 {data.get('total', 0)} 个需求[/dim]")


@cli.command(name="get", help="需求详情")
@click.argument("req_id")
def get_cmd(req_id):
    cfg = Config.load()
    console = make_console(cfg.output_color)
    client = ArchClient(cfg)
    try:
        req = client.get_requirement(req_id)
    except Exception as e:
        console.print(f"[red]✗ 查询失败:[/red] {e}")
        sys.exit(1)
    print_json(req, console)


@cli.command(name="create", help="创建需求")
@click.argument("component_id", required=False, default=None)
@click.option("--title", required=True, help="需求标题(20-200 字符)")
@click.option("--description", help="详细描述")
@click.option("--user-story", help="用户故事")
@click.option("--ac", "acceptance_criteria", help='验收标准 JSON 字符串,如 \'[{"given":"...","when":"...","then":"..."}]\'')
@click.option("--nfr", "nfr", help='NFR JSON 字符串,如 \'{"performance":"p99<200ms"}\'')
@click.option("--type", "req_type", required=True, type=click.Choice([
    "new_feature", "bug_fix", "refactor", "optimization", "compliance", "tech_debt",
]))
@click.option("--priority", default="P2", type=click.Choice(["P0", "P1", "P2", "P3"]))
@click.option("--assignee", help="负责人")
@click.option("--due-date", help="截止日期(ISO 8601)")
@click.option("--tags", help="标签(逗号分隔)")
@click.option("--proposer", default="cli", help="提议人")
def create_cmd(component_id, title, description, user_story, acceptance_criteria,
               nfr, req_type, priority, assignee, due_date, tags, proposer):
    cfg = Config.load()
    console = make_console(cfg.output_color)
    client = ArchClient(cfg)

    import json
    data = {
        "title": title,
        "type": req_type,
        "priority": priority,
        "proposer": proposer,
    }
    if description:
        data["description"] = description
    if user_story:
        data["user_story"] = user_story
    if acceptance_criteria:
        data["acceptance_criteria"] = json.loads(acceptance_criteria)
    if nfr:
        data["nfr"] = json.loads(nfr)
    if assignee:
        data["assignee"] = assignee
    if due_date:
        data["due_date"] = due_date
    if tags:
        data["tags"] = [t.strip() for t in tags.split(",")]

    try:
        if component_id:
            result = client.create_requirement(component_id, data)
        else:
            result = client.create_requirement_flat(data)
    except Exception as e:
        console.print(f"[red]✗ 创建失败:[/red] {e}")
        sys.exit(1)

    console.print(f"[green]✓ 需求已登记:[/green] {result['id'][:8]} ({priority}/{req_type})")
    console.print(f"  {result['title'][:60]}")


@cli.command(name="update", help="更新需求(状态 / 优先级 / 负责人 / 描述 / 用户故事 / AC / NFR)")
@click.argument("req_id")
@click.option("--status", type=click.Choice([
    "draft", "triaged", "scheduled", "in_progress",
    "implemented", "verified", "rejected", "cancelled",
]))
@click.option("--priority", type=click.Choice(["P0", "P1", "P2", "P3"]))
@click.option("--assignee", help="负责人")
@click.option("--due-date", help="截止日期")
@click.option("--description", help="详细描述")
@click.option("--user-story", help="用户故事(2026-06-22 新增)")
@click.option("--ac", "acceptance_criteria", help='验收标准 JSON 字符串,如 \'[{"given":"...","when":"...","then":"..."}]\' (2026-06-22 新增)')
@click.option("--nfr", help='NFR JSON 字符串,如 \'{"performance":"p99<200ms"}\' (2026-06-22 新增)')
@click.option("--tags", help="标签(逗号分隔)")
def update_cmd(req_id, status, priority, assignee, due_date, description,
               user_story, acceptance_criteria, nfr, tags):
    cfg = Config.load()
    console = make_console(cfg.output_color)
    client = ArchClient(cfg)

    import json
    data = {}
    if status:
        data["status"] = status
    if priority:
        data["priority"] = priority
    if assignee:
        data["assignee"] = assignee
    if due_date:
        data["due_date"] = due_date
    if description:
        data["description"] = description
    if user_story:
        data["user_story"] = user_story
    if acceptance_criteria:
        data["acceptance_criteria"] = json.loads(acceptance_criteria)
    if nfr:
        data["nfr"] = json.loads(nfr)
    if tags:
        data["tags"] = [t.strip() for t in tags.split(",")]

    if not data:
        console.print("[yellow]未指定任何更新字段[/yellow]")
        sys.exit(1)

    try:
        result = client.patch_requirement(req_id, data)
    except Exception as e:
        console.print(f"[red]✗ 更新失败:[/red] {e}")
        sys.exit(1)

    console.print(f"[green]✓ 需求已更新:[/green] {result['id'][:8]}")
    console.print(f"  status={result.get('status')} priority={result.get('priority')}")


@cli.command(name="archive", help="软删除需求")
@click.argument("req_id")
def archive_cmd(req_id):
    cfg = Config.load()
    console = make_console(cfg.output_color)
    client = ArchClient(cfg)
    try:
        result = client.archive_requirement(req_id)
    except Exception as e:
        console.print(f"[red]✗ 归档失败:[/red] {e}")
        sys.exit(1)
    console.print(f"[green]✓ 需求已归档:[/green] {result['id'][:8]}")


@cli.command(name="restore", help="撤销软删除")
@click.argument("req_id")
def restore_cmd(req_id):
    cfg = Config.load()
    console = make_console(cfg.output_color)
    client = ArchClient(cfg)
    try:
        result = client.restore_requirement(req_id)
    except Exception as e:
        console.print(f"[red]✗ 恢复失败:[/red] {e}")
        sys.exit(1)
    console.print(f"[green]✓ 需求已恢复:[/green] {result['id'][:8]}")


@cli.command(name="link-feedback", help="显式回链 feedback → requirement")
@click.argument("req_id")
@click.argument("fb_id")
def link_feedback_cmd(req_id, fb_id):
    cfg = Config.load()
    console = make_console(cfg.output_color)
    client = ArchClient(cfg)
    try:
        result = client.link_feedback_requirement(fb_id, req_id)
    except Exception as e:
        console.print(f"[red]✗ 回链失败:[/red] {e}")
        sys.exit(1)
    console.print(f"[green]✓ 回链已建立:[/green] feedback={result['feedback_id'][:8]} ← requirement={result['requirement_id'][:8]}")