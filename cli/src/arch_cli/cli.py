"""arch CLI 主入口

用法:
  arch component list
  arch component get <name>
  arch component create --name ... --title ... --positioning ... --layer ...
  arch version create <component> --version 1.0.0 --intent major --changelog ...
  arch feedback create <version_id> --summary ... --severity high
  arch deployment create <version_id> --env prod --host huawei-1
  arch search <query>
  arch use <component>
  arch tree <component>
  arch outdated
  arch lock -o .aip-lock.toml
  arch detect [path]
  arch config show
  arch config set-url https://arch.intelab.cn
  arch config set-key sk-xxx
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import click

from . import __version__
from .client import ArchClient
from .config import Config
from .commands.component import cli as component_cli
from .commands.version import cli as version_cli
from .commands.feedback import cli as feedback_cli
from .commands.requirement import cli as requirement_cli
from .commands.doubt import cli as doubt_cli
from .commands.deployment import cli as deployment_cli
from .commands.search import search_cmd, use_cmd, tree_cmd
from .commands.config_cmd import cli as config_cli
from .commands.outdated import outdated_cmd, lock_cmd
from .output import make_console


@click.group()
@click.version_option(version=__version__, prog_name="arch")
@click.option("--server", envvar="ARCH_PLATFORM_URL", help="API URL(覆盖配置)")
@click.option("--api-key", envvar="ARCH_PLATFORM_API_KEY", help="API Key(覆盖配置)")
@click.pass_context
def main(ctx, server, api_key):
    """架构平台 CLI — 组件登记 / 版本 / 反馈 / 部署"""
    ctx.ensure_object(dict)
    cfg = Config.load()
    if server:
        cfg.server_url = server
    if api_key:
        cfg.api_key = api_key
    ctx.obj["config"] = cfg


# 注册子命令
main.add_command(component_cli)
main.add_command(version_cli)
main.add_command(feedback_cli)
main.add_command(requirement_cli)
main.add_command(doubt_cli)
main.add_command(deployment_cli)
main.add_command(config_cli)
main.add_command(search_cmd)
main.add_command(use_cmd)
main.add_command(tree_cmd)
main.add_command(outdated_cmd)
main.add_command(lock_cmd)


# ——— detect 命令(读 aip.json 自动预填)———
@main.command(name="detect", help="读 aip.json 自动预填参数")
@click.argument("path", default=".")
def detect_cmd(path):
    """读 aip.json,自动显示或预填组件参数"""
    p = Path(path)
    aip = p / "aip.json" if p.is_dir() else p

    if not aip.exists():
        click.echo(f"✗ aip.json 不存在:{aip}", err=True)
        sys.exit(1)

    try:
        data = json.loads(aip.read_text())
    except json.JSONDecodeError as e:
        click.echo(f"✗ aip.json 解析失败:{e}", err=True)
        sys.exit(1)

    click.echo(f"✓ 读取 {aip}")
    click.echo("")
    click.echo("字段:")
    for k, v in data.items():
        click.echo(f"  {k:20s} = {v}")

    # 如果是已登记组件,验证
    if "name" in data:
        click.echo("")
        click.echo("检查架构平台是否已登记...")
        cfg = Config.load()
        client = ArchClient(cfg)
        try:
            comp = client.get_component(data["name"])
            click.echo(f"  ✓ 已登记:id={comp['id'][:8]}, version={comp.get('current_version_id', '?')[:8]}")
        except Exception:
            click.echo(f"  ✗ 未登记。可用:arch component create --name {data['name']} ...")


# ——— health 子命令 ———
@main.command(name="health", help="健康检查")
def health_cmd():
    cfg = Config.load()
    console = make_console(cfg.output_color)
    client = ArchClient(cfg)
    try:
        h = client.healthz()
        if h.get("db_check"):
            console.print(f"[green]✓ 服务正常:[/green] {cfg.server_url} (DB OK)")
        else:
            console.print(f"[yellow]⚠ 服务在线但 DB 异常:[/yellow] {h}")
    except Exception as e:
        console.print(f"[red]✗ 服务不可达:[/red] {cfg.server_url} - {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()