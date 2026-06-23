"""arch component — Component CRUD 命令

子命令:
- list        列出组件(支持 layer/category/is_asset 过滤)
- get         按 name 取详情
- create      创建组件
- bulk-create 从 YAML 批量创建(FB-1 修复)
- update      更新组件(PATCH)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

import click
import yaml  # FB-1 新增依赖

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
@click.option("--atomic/--no-atomic", default=True, help="是否原子组件(FB-3 修复:统一布尔对命名,删除 --composite 别名)")
@click.option("--composed-of", "composed_of", help="复合组件子项,格式 'name:constraint' 逗号分隔(FB-2 修复:如 'auth:^1.0,db:~2.1')")
@click.option("--interface-contract", help="接口契约(http_api 必填)")
@click.option("--knowledge-artifact/--no-knowledge-artifact", default=False, help="是否 AI 上下文资产")
@click.option("--tags", help="标签(逗号分隔)")
@click.option("--repo-url", help="仓库 URL")
@click.option("--package-name", help="包名(用于 install_command)")
@click.option("--install-command", help="一行安装命令")
@click.option("--usage-example", help="一行使用示例")
def create_cmd(name, title, positioning, category, layer, scope, is_asset,
               distribution_form, atomic, composed_of, interface_contract, knowledge_artifact,
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

    # FB-2 修复:composed_of 支持 'name:constraint' 格式(逗号分隔多组)
    # CLI 内部先 lookup 每个 name 拿 component_id 再 POST
    if composed_of:
        if atomic:
            console.print("[red]✗ --atomic 不能与 --composed-of 同时使用[/red]")
            sys.exit(1)
        entries = []
        for entry in composed_of.split(","):
            entry = entry.strip()
            if ":" not in entry:
                console.print(f"[red]✗ --composed-of 格式错误: '{entry}',应为 'name:constraint'[/red]")
                sys.exit(1)
            child_name, constraint = entry.split(":", 1)
            # 查子组件 ID(用 list + name 过滤,FB-4 修复后可用)
            child = client.get_component(child_name.strip())
            entries.append({
                "component_id": child["id"],
                "version_constraint": constraint.strip(),
            })
        data["composed_of"] = entries

    try:
        result = client.create_component(data)
    except Exception as e:
        console.print(f"[red]✗ 创建失败:[/red] {e}")
        sys.exit(1)

    console.print(f"[green]✓ 组件已创建:[/green] {result['name']} (id={result['id'][:8]}...)")
    if result.get("is_asset"):
        console.print(f"  形态: {result.get('distribution_form')}")


@cli.command(name="bulk-create", help="[FB-1] 从 YAML 文件批量创建组件,支持 dry-run")
@click.option("--from-file", "from_file", required=True, type=click.Path(exists=True),
              help="YAML 文件路径,顶层是 components 列表")
@click.option("--dry-run", is_flag=True, help="只打印将创建的组件,不实际调用 API")
@click.option("--continue-on-error", is_flag=True, help="遇错继续(默认遇错立即停止)")
def bulk_create_cmd(from_file, dry_run, continue_on_error):
    """从 YAML 批量创建组件

    YAML 格式(顶层 list,每个元素一个 component):
    ```yaml
    - name: redis-cache
      title: Redis 缓存客户端
      positioning: ...
      category: cache
      layer: L1_platform
      is_asset: true
      distribution_form: package
      atomic: true
    - name: user-mgmt-svc
      title: 用户管理服务
      positioning: ...
      category: auth
      layer: L2_capability
      atomic: false
      composed_of:
        - { name: redis-cache, constraint: "^1.0" }
    ```
    """
    cfg = Config.load()
    console = make_console(cfg.output_color)
    client = ArchClient(cfg)

    with open(from_file, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if not isinstance(data, list):
        console.print("[red]✗ YAML 顶层必须是 list(每个元素一个 component)[/red]")
        sys.exit(1)

    if dry_run:
        console.print(f"[yellow]DRY-RUN:[/yellow] 将创建 {len(data)} 个组件(不实际调用 API)")
        for i, comp in enumerate(data, 1):
            console.print(f"  {i}. [cyan]{comp.get('name', '?')}[/cyan] - {comp.get('title', '?')[:40]}")
        return

    success = 0
    failed = 0
    for i, comp_data in enumerate(data, 1):
        name = comp_data.get("name", "?")
        # 处理 composed_of(从 {name, constraint} 转 {component_id, version_constraint})
        if "composed_of" in comp_data:
            entries = []
            for entry in comp_data["composed_of"]:
                child_name = entry.get("name")
                constraint = entry.get("constraint", "^0.0.0")
                if not child_name:
                    console.print(f"[red]✗ {name}: composed_of 缺 name 字段[/red]")
                    failed += 1
                    break
                try:
                    child = client.get_component(child_name)
                    entries.append({
                        "component_id": child["id"],
                        "version_constraint": constraint,
                    })
                except Exception as e:
                    console.print(f"[red]✗ {name}: 查子组件 {child_name} 失败: {e}[/red]")
                    failed += 1
                    break
            else:
                comp_data["composed_of"] = entries
                try:
                    result = client.create_component(comp_data)
                    console.print(f"  [green]✓[/green] {i}/{len(data)} [cyan]{result['name']}[/cyan] ({result.get('distribution_form', '-')})")
                    success += 1
                except Exception as e:
                    console.print(f"  [red]✗[/red] {i}/{len(data)} {name}: {e}")
                    failed += 1
                    if not continue_on_error:
                        sys.exit(1)
                continue
            if not continue_on_error:
                sys.exit(1)
            continue

        try:
            result = client.create_component(comp_data)
            console.print(f"  [green]✓[/green] {i}/{len(data)} [cyan]{result['name']}[/cyan] ({result.get('distribution_form', '-')})")
            success += 1
        except Exception as e:
            console.print(f"  [red]✗[/red] {i}/{len(data)} {name}: {e}")
            failed += 1
            if not continue_on_error:
                sys.exit(1)

    console.print(f"\n[bold]完成:[/bold] 成功 {success} / 失败 {failed} / 总计 {len(data)}")
    if failed > 0:
        sys.exit(1)


@cli.command(name="update", help="更新组件(部分字段 PATCH)")
@click.argument("name")
@click.option("--title", help="新标题")
@click.option("--positioning", help="新定位")
@click.option("--tags", help="新标签(逗号分隔)")
@click.option("--is-asset/--no-asset", "is_asset", default=None, help="是否真资产")
@click.option("--repo-url", help="新仓库 URL")
@click.option("--composed-of", "composed_of", help="复合组件子项,格式 'name:constraint' 逗号分隔(FB-38f2024f 修复:支持 PATCH 补 composed_of)")
@click.option("--atomic/--no-atomic", "atomic", default=None, help="原子/复合标记(配合 --composed-of 使用)")
@click.option("--sub-layer", "sub_layer", type=click.Choice(["orchestration", "normal"]), help="ADR-0001:子层标记(orchestration/normal)")
@click.option("--cross-cutting/--no-cross-cutting", "cross_cutting", default=None, help="ADR-0001:是否横切关注点")
@click.option("--runtime-dependency", "runtime_dependency", help="ADR-0001:运行时依赖,格式 'name:constraint:relation' 逗号分隔(relation=orchestration|peer|deployment)")
def update_cmd(name, title, positioning, tags, is_asset, repo_url,
               composed_of, atomic, sub_layer, cross_cutting, runtime_dependency):
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
    if atomic is not None:
        data["atomic"] = atomic
    if sub_layer is not None:
        data["sub_layer"] = sub_layer
    if cross_cutting is not None:
        data["cross_cutting"] = cross_cutting

    # FB-38f2024f 修复:composed_of 走 name→id 解析,跟 create_cmd 一致
    if composed_of:
        if atomic:
            console.print("[red]✗ --atomic 不能与 --composed-of 同时使用[/red]")
            sys.exit(1)
        entries = []
        for entry in composed_of.split(","):
            entry = entry.strip()
            if ":" not in entry:
                console.print(f"[red]✗ --composed-of 格式错误: '{entry}',应为 'name:constraint'[/red]")
                sys.exit(1)
            child_name, constraint = entry.split(":", 1)
            child = client.get_component(child_name.strip())
            entries.append({
                "component_id": child["id"],
                "version_constraint": constraint.strip(),
            })
        data["composed_of"] = entries

    # ADR-0001 续:runtime_dependency 接受 name:constraint:relation 三段
    if runtime_dependency:
        rd_entries = []
        for entry in runtime_dependency.split(","):
            entry = entry.strip()
            parts = entry.split(":")
            if len(parts) < 2:
                console.print(f"[red]✗ --runtime-dependency 格式错误: '{entry}',应为 'name:constraint[:relation]'[/red]")
                sys.exit(1)
            child_name = parts[0].strip()
            constraint = parts[1].strip()
            relation = parts[2].strip() if len(parts) >= 3 else None
            child = client.get_component(child_name)
            rd_entries.append({
                "component_id": child["id"],
                "version_constraint": constraint,
                **({"relation": relation} if relation else {}),
            })
        data["runtime_dependency"] = rd_entries

    if not data:
        console.print("[yellow]未指定任何更新字段[/yellow]")
        sys.exit(1)

    try:
        result = client.update_component(name, data)
    except Exception as e:
        console.print(f"[red]✗ 更新失败:[/red] {e}")
        sys.exit(1)

    console.print(f"[green]✓ 组件已更新:[/green] {result['name']}")