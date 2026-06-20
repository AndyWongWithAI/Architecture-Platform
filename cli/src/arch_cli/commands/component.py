"""arch component — Component CRUD 命令

子命令:
- list   列出组件(支持 layer/category/is_asset 过滤)
- get    按 name 取详情
- create 创建组件
- update 更新组件(PATCH)
"""
from __future__ import annotations

import json
import sys
from typing import Optional

import click

from ..client import ArchClient
from ..config import Config
from ..output import make_console, print_components, print_json


@click.group(name="component", help="Component 组件 CRUD")
def cli():
    pass


@cli.command(name="list", help="列出组件")
@click.option("--layer", help="按层级过滤(L0_infrastructure / L1_platform / L2_capability / L3_application)")
@click.option("--category", help="按分类过滤(auth/db/cache/queue/...)")
@click.option("--asset/--no-asset", default=None, help="是否真资产")
@click.option("--q", help="关键字搜索(name/title/tags/positioning)")
@click.option("--format", "fmt", type=click.Choice(["table", "json"]), default=None)
def list_cmd(layer, category, asset, q, fmt):
    cfg = Config.load()
    if fmt:
        cfg.output_format = fmt
    console = make_console(cfg.output_color)
    client = ArchClient(cfg)

    params = {}
    if layer:
        params["layer"] = layer
    if category:
        params["category"] = category
    if asset is not None:
        params["is_asset"] = "true" if asset else "false"
    if q:
        params["q"] = q

    data = client.list_components(**params)
    items = data.get("items", [])

    if cfg.output_format == "json":
        print_json(items, console)
    else:
        print_components(items, console)
        console.print(f"[dim]共 {data.get('total', 0)} 个组件[/dim]")


@cli.command(name="get", help="按 name 取组件详情")
@click.argument("name")
@click.option("--format", "fmt", type=click.Choice(["table", "json"]), default=None)
def get_cmd(name, fmt):
    cfg = Config.load()
    if fmt:
        cfg.output_format = fmt
    console = make_console(cfg.output_color)
    client = ArchClient(cfg)
    data = client.get_component(name)
    if cfg.output_format == "json":
        print_json(data, console)
    else:
        # 关键字段高亮
        console.print(f"[bold cyan]{data['name']}[/bold cyan]")
        console.print(f"  title:       {data.get('title', '')}")
        console.print(f"  positioning: {data.get('positioning', '')}")
        console.print(f"  layer:       {data.get('layer', '')}")
        console.print(f"  category:    {data.get('category', '')}")
        console.print(f"  asset:       {'✓ 真资产' if data.get('is_asset') else '✗ 项目级'}")
        console.print(f"  form:        {data.get('distribution_form') or '-'}")
        console.print(f"  knowledge:   {data.get('knowledge_artifact')}")
        console.print(f"  atomic:      {data.get('atomic')}")
        console.print(f"  composed_of: {len(data.get('composed_of', []))} 个")
        console.print(f"  status:      {data.get('status', '')}")


@cli.command(name="create", help="创建新组件")
@click.option("--name", required=True, help="组件名(kebab-case,如 redis-cache)")
@click.option("--title", required=True, help="人类可读标题")
@click.option("--positioning", required=True, help="定位描述(必须稳定,10+ 字符)")
@click.option("--category", required=True, help="分类(auth/db/cache/queue/log/deploy/monitor/ui/util/other)")
@click.option("--layer", required=True, help="层级(L0_infrastructure / L1_platform / L2_capability / L3_application)")
@click.option("--scope", default="lib", help="作用域(app/infra/lib/tool)")
@click.option("--is-asset/--no-asset", "is_asset", default=True, help="是否真资产")
@click.option("--form", "distribution_form", help="分发形态(package/container/binary/source/http_api/schema/dataset/config_template/iac/skill/tool)")
@click.option("--atomic/--composite", default=True, help="是否原子组件")
@click.option("--interface-contract", help="接口契约(http_api 必填)")
@click.option("--knowledge-artifact/--no-knowledge-artifact", default=False, help="是否 AI 上下文资产")
@click.option("--tags", help="标签(逗号分隔)")
@click.option("--repo-url", help="仓库 URL")
@click.option("--package-name", help="包名(用于 install_command)")
@click.option("--install-command", help="一行安装命令")
@click.option("--usage-example", help="一行使用示例")
def create_cmd(name, title, positioning, category, layer, scope, is_asset,
               distribution_form, atomic, interface_contract, knowledge_artifact,
               tags, repo_url, package_name, install_command, usage_example):
    cfg = Config.load()
    console = make_console(cfg.output_color)
    client = ArchClient(cfg)

    data = {
        "name": name,
        "title": title,
        "positioning": positioning,
        "category": category,
        "layer": layer,
        "scope": scope,
        "is_asset": is_asset,
        "knowledge_artifact": knowledge_artifact,
        "atomic": atomic,
    }
    if distribution_form:
        data["distribution_form"] = distribution_form
    if interface_contract:
        data["interface_contract"] = interface_contract
    if tags:
        data["tags"] = [t.strip() for t in tags.split(",")]
    if repo_url:
        data["repo_url"] = repo_url
    if package_name:
        data["package_name"] = package_name
    if install_command:
        data["install_command"] = install_command
    if usage_example:
        data["usage_example"] = usage_example

    try:
        result = client.create_component(data)
    except Exception as e:
        console.print(f"[red]✗ 创建失败:[/red] {e}")
        sys.exit(1)

    console.print(f"[green]✓ 组件已创建:[/green] {result['name']} (id={result['id'][:8]}...)")
    if result.get("is_asset"):
        console.print(f"  形态: {result.get('distribution_form')}")


@cli.command(name="update", help="更新组件(部分字段 PATCH)")
@click.argument("name")
@click.option("--title", help="新标题")
@click.option("--positioning", help="新定位")
@click.option("--tags", help="新标签(逗号分隔)")
@click.option("--is-asset/--no-asset", "is_asset", default=None, help="是否真资产")
@click.option("--repo-url", help="新仓库 URL")
def update_cmd(name, title, positioning, tags, is_asset, repo_url):
    cfg = Config.load()
    console = make_console(cfg.output_color)
    client = ArchClient(cfg)

    data = {}
    if title:
        data["title"] = title
    if positioning:
        data["positioning"] = positioning
    if tags:
        data["tags"] = [t.strip() for t in tags.split(",")]
    if is_asset is not None:
        data["is_asset"] = is_asset
    if repo_url:
        data["repo_url"] = repo_url

    if not data:
        console.print("[yellow]未指定任何更新字段[/yellow]")
        sys.exit(1)

    try:
        result = client.update_component(name, data)
    except Exception as e:
        console.print(f"[red]✗ 更新失败:[/red] {e}")
        sys.exit(1)

    console.print(f"[green]✓ 组件已更新:[/green] {result['name']}")