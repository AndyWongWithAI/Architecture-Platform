"""arch deployment — 部署登记"""
from __future__ import annotations

import sys

import click

from ..client import ArchClient
from ..config import Config
from ..output import make_console, print_json


@click.group(name="deployment", help="Deployment 部署登记")
def cli():
    pass


@cli.command(name="create", help="登记部署")
@click.argument("version_id")
@click.option("--env", required=True, type=click.Choice(["dev", "staging", "prod"]))
@click.option("--host", required=True, help="主机标识,如 huawei-1")
@click.option("--path", "deploy_path", help="部署路径")
@click.option("--config-hash", help="配置文件 SHA256")
@click.option("--deployed-by", default="cli", help="部署人/工具")
@click.option("--lockfile-hash", help="依赖 lockfile SHA256")
@click.option("--reproducible/--no-reproducible", "build_reproducible", default=True)
@click.option("--resolved-versions", help="实际安装版本(JSON 字符串)")
def create_cmd(version_id, env, host, deploy_path, config_hash, deployed_by,
               lockfile_hash, build_reproducible, resolved_versions):
    cfg = Config.load()
    console = make_console(cfg.output_color)
    client = ArchClient(cfg)

    import json as _json
    data = {
        "env": env,
        "host": host,
        "deployed_by": deployed_by,
        "build_reproducible": build_reproducible,
    }
    if deploy_path:
        data["deploy_path"] = deploy_path
    if config_hash:
        data["config_hash"] = config_hash
    if lockfile_hash:
        data["lockfile_hash"] = lockfile_hash
    if resolved_versions:
        try:
            data["resolved_versions"] = _json.loads(resolved_versions)
        except Exception as e:
            console.print(f"[red]✗ resolved_versions JSON 解析失败:[/red] {e}")
            sys.exit(1)

    try:
        result = client.create_deployment(version_id, data)
    except Exception as e:
        console.print(f"[red]✗ 登记失败:[/red] {e}")
        sys.exit(1)

    console.print(f"[green]✓ 部署已登记:[/green] {result['id'][:8]} ({env}@{host})")


@cli.command(name="list", help="列出部署历史")
@click.option("--format", "fmt", type=click.Choice(["table", "json"]), default=None)
def list_cmd(fmt):
    cfg = Config.load()
    if fmt:
        cfg.output_format = fmt
    console = make_console(cfg.output_color)
    client = ArchClient(cfg)

    data = client.list_deployments()
    items = data.get("items", [])
    if cfg.output_format == "json":
        print_json(items, console)
    else:
        console.print(f"[dim]共 {data.get('total', 0)} 条部署记录[/dim]")
        for dep in items[:20]:
            console.print(f"  - {dep.get('host')}/{dep.get('env')} @ {dep.get('deployed_at', '')[:19]}")