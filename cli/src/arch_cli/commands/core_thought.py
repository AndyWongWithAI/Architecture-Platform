"""arch core-thought — REQ-968b1c99 第 6 大实体(核心思想 / 道层面)

对齐 arch requirement 命令的风格与模式(reuse)。
7 子命令:list / get / create / update / archive / restore / seed-dao-governance
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

import click

from ..client import ArchClient
from ..config import Config
from ..output import make_console, print_core_thoughts, print_json


# ——— seed 用的常量 ———
SEED_TITLE_PREFIX = "治理的道:让人不必记规范也能不犯规范上的错"
SEED_PROPOSER = "黄谦敏"
SEED_ORIGIN = "memory/dao-governance-philosophy.md"
SEED_STATUS = "active"
SEED_TAGS = ["governance", "dao", "feedback-loop", "audit", "soft-hard-gate"]

# memory 文件候选路径(优先级从高到低)
DEFAULT_MEMORY_PATH = Path.home() / ".claude" / "projects" / "-home-hq" / "memory" / "dao-governance-philosophy.md"
SEED_MEMORY_PATH = Path(
    os.environ.get("ARCH_CORE_THOUGHT_SEED_PATH", str(DEFAULT_MEMORY_PATH))
)


@click.group(name="core-thought", help="CoreThought 核心思想登记(REQ-968b1c99,第 6 大实体)")
def cli():
    pass


# ——— 工具:解析 markdown 段落(按 ### 二级标题切片)———
def _parse_seed_sections(md_text: str) -> dict:
    """从 memory/dao-governance-philosophy.md 提取字段。

    切片规则:
      - rationale = 「过去的困局」+「真正的转变」+「背后的道」三段拼接(### 标题 + 段落)
      - thesis = 「一句话」+「展开」开头一段(从「### 过去的困局」之前的所有内容)
      - how_to_apply = 从 frontmatter description 里的 "How to apply:" 提示
                      + 文件底部 **How to apply:** 标记(两种策略:优先底部分隔线后)

    若 memory 文件结构变化,不会崩:解析不到就用原始 markdown 兜底。
    """
    # 去掉 frontmatter
    body = md_text
    if body.startswith("---"):
        end = body.find("\n---", 3)
        if end != -1:
            body = body[end + 4 :].lstrip("\n")

    sections: dict[str, str] = {}
    current_h2: str | None = None
    buf: list[str] = []

    def flush() -> None:
        if current_h2 is not None:
            sections[current_h2] = "\n".join(buf).strip()

    for line in body.splitlines():
        m = re.match(r"^##\s+(.+?)\s*$", line)
        if m:
            flush()
            current_h2 = m.group(1).strip()
            buf = []
        else:
            buf.append(line)
    flush()

    # thesis = 「## 一句话」+「## 展开」(「展开」只取到第一个 ### 子标题之前)
    thesis_parts: list[str] = []
    for key in ("一句话", "展开"):
        v = sections.get(key, "")
        if v:
            # 「展开」可能含 ### 子标题,只保留到第一个 ### 之前
            cut = re.search(r"^###\s+", v, flags=re.M)
            if cut:
                v = v[: cut.start()].rstrip()
            thesis_parts.append(f"## {key}\n\n{v}")
    thesis = "\n\n".join(thesis_parts).strip()

    # rationale = 「## 展开」下的「### 过去的困局」+「### 真正的转变」+「### 背后的道」
    # 「## 展开」整段都算 rationale
    rationale = sections.get("展开", "").strip()

    # how_to_apply 优先从文件底部分隔线后取,其次 frontmatter description 里的提示
    how_to_apply = ""
    sep_match = re.search(r"\n---\s*\n", body)
    after_sep = body[sep_match.end():] if sep_match else ""
    apply_match = re.search(r"\*\*How to apply:\*\*\s*(.+?)(?:\n\n|$)", after_sep, flags=re.S)
    if apply_match:
        how_to_apply = apply_match.group(1).strip()
    else:
        # 兜底:从 frontmatter description 提示
        m = re.search(r"How to apply:\s*([^\"']+?)\"", md_text[:1000])
        if m:
            how_to_apply = m.group(1).strip()

    return {
        "title": SEED_TITLE_PREFIX,
        "thesis": thesis or "让人不必记规范也能不犯规范上的错。",
        "rationale": rationale,
        "how_to_apply": how_to_apply,
    }


@cli.command(name="list", help="列出核心思想")
@click.option("--q", help="关键字(跨 title / thesis / rationale 模糊搜索)")
@click.option("--tag", help="按 tag 过滤(命中 tags 数组任一元素)")
@click.option("--status", type=click.Choice(["draft", "active", "superseded", "archived"]))
@click.option("--proposer", help="按提议人过滤")
@click.option("--include-archived", is_flag=True, help="包含已归档")
@click.option("--format", "fmt", type=click.Choice(["table", "json"]), default=None)
def list_cmd(q, tag, status, proposer, include_archived, fmt):
    cfg = Config.load()
    if fmt:
        cfg.output_format = fmt
    console = make_console(cfg.output_color)
    client = ArchClient(cfg)

    params: dict = {}
    if q:
        params["q"] = q
    if tag:
        params["tag"] = tag
    if status:
        params["status"] = status
    if proposer:
        params["proposer"] = proposer
    if include_archived:
        params["include_archived"] = True

    data = client.list_core_thoughts(**params)
    items = data.get("items", [])
    if cfg.output_format == "json":
        print_json(items, console)
    else:
        print_core_thoughts(items, console)
        console.print(f"[dim]共 {data.get('total', 0)} 条核心思想[/dim]")


@cli.command(name="get", help="核心思想详情")
@click.argument("ct_id")
def get_cmd(ct_id):
    cfg = Config.load()
    console = make_console(cfg.output_color)
    client = ArchClient(cfg)
    try:
        ct = client.get_core_thought(ct_id)
    except Exception as e:
        console.print(f"[red]✗ 查询失败:[/red] {e}")
        sys.exit(1)

    # JSON + 字段高亮(对齐 requirement get_cmd)
    print_json(ct, console)
    console.print("")
    console.print(f"[bold cyan]title:[/bold cyan]      {ct.get('title')}")
    console.print(f"[bold cyan]status:[/bold cyan]     {ct.get('status')}")
    tags = ct.get("tags") or []
    console.print(f"[bold cyan]tags:[/bold cyan]       {', '.join(tags) if tags else '-'}")
    console.print(f"[bold cyan]proposer:[/bold cyan]   {ct.get('proposer')}")
    examples = ct.get("examples") or []
    console.print(f"[bold cyan]examples:[/bold cyan]   {len(examples)} 条 component 引用")


@cli.command(name="create", help="创建核心思想")
@click.option("--title", required=True, help="一句话主张(20-500 字符)")
@click.option("--thesis", required=True, help="2-5 段精炼展开(Markdown)")
@click.option("--rationale", help="背景 / 困局 / 对比(Markdown)")
@click.option("--how-to-apply", help="应用指引(Markdown)")
@click.option("--origin", help="来源标注,如 memory/foo.md")
@click.option("--status", default="draft",
              type=click.Choice(["draft", "active", "superseded", "archived"]))
@click.option("--tags", help="标签(逗号分隔)")
@click.option("--examples", help='examples JSON 字符串,如 \'[{"component_id":"abc","note":"..."}]\'')
@click.option("--proposer", default="cli", help="提议人")
def create_cmd(title, thesis, rationale, how_to_apply, origin, status, tags, examples, proposer):
    cfg = Config.load()
    console = make_console(cfg.output_color)
    client = ArchClient(cfg)

    data: dict = {
        "title": title,
        "thesis": thesis,
        "status": status,
        "proposer": proposer,
    }
    if rationale:
        data["rationale"] = rationale
    if how_to_apply:
        data["how_to_apply"] = how_to_apply
    if origin:
        data["origin"] = origin
    if tags:
        data["tags"] = [t.strip() for t in tags.split(",") if t.strip()]
    if examples is not None:
        # P3.5 review 红旗 2:JSON 解析兜底,失败给友好提示
        try:
            data["examples"] = json.loads(examples)
        except json.JSONDecodeError as e:
            console.print(f"[red]✗ --examples JSON 解析失败:[/red] {e}")
            sys.exit(1)

    try:
        result = client.create_core_thought(data)
    except Exception as e:
        console.print(f"[red]✗ 创建失败:[/red] {e}")
        sys.exit(1)

    console.print(f"[green]✓ 核心思想已登记:[/green] {result['id'][:8]} ({status})")
    console.print(f"  {result['title'][:60]}")


@cli.command(name="update", help="更新核心思想(所有字段 Optional)")
@click.argument("ct_id")
@click.option("--title", help="一句话主张")
@click.option("--thesis", help="精炼展开(Markdown)")
@click.option("--rationale", help="背景 / 困局(Markdown)")
@click.option("--how-to-apply", help="应用指引(Markdown)")
@click.option("--origin", help="来源标注")
@click.option("--status", type=click.Choice(["draft", "active", "superseded", "archived"]))
@click.option("--tags", help="标签(逗号分隔,覆盖式)")
@click.option("--examples", help='examples JSON 字符串(覆盖式)')
@click.option("--proposer", help="提议人")
def update_cmd(ct_id, title, thesis, rationale, how_to_apply, origin,
               status, tags, examples, proposer):
    cfg = Config.load()
    console = make_console(cfg.output_color)
    client = ArchClient(cfg)

    data: dict = {}
    if title:
        data["title"] = title
    if thesis:
        data["thesis"] = thesis
    if rationale:
        data["rationale"] = rationale
    if how_to_apply:
        data["how_to_apply"] = how_to_apply
    if origin:
        data["origin"] = origin
    if status:
        data["status"] = status
    if tags:
        data["tags"] = [t.strip() for t in tags.split(",") if t.strip()]
    if examples is not None:
        # P3.5 review 红旗 2:JSON 解析兜底
        try:
            data["examples"] = json.loads(examples)
        except json.JSONDecodeError as e:
            console.print(f"[red]✗ --examples JSON 解析失败:[/red] {e}")
            sys.exit(1)
    if proposer:
        data["proposer"] = proposer

    if not data:
        console.print("[yellow]未指定任何更新字段[/yellow]")
        sys.exit(1)

    try:
        result = client.update_core_thought(ct_id, data)
    except Exception as e:
        console.print(f"[red]✗ 更新失败:[/red] {e}")
        sys.exit(1)

    console.print(f"[green]✓ 核心思想已更新:[/green] {result['id'][:8]}")
    console.print(f"  status={result.get('status')} title={result.get('title', '')[:50]}")


@cli.command(name="archive", help="软删除核心思想(is_archived=true)")
@click.argument("ct_id")
def archive_cmd(ct_id):
    cfg = Config.load()
    console = make_console(cfg.output_color)
    client = ArchClient(cfg)
    try:
        result = client.archive_core_thought(ct_id)
    except Exception as e:
        console.print(f"[red]✗ 归档失败:[/red] {e}")
        sys.exit(1)
    console.print(f"[green]✓ 核心思想已归档:[/green] {result['id'][:8]}")


@cli.command(name="restore", help="撤销软删除(is_archived=false)")
@click.argument("ct_id")
def restore_cmd(ct_id):
    cfg = Config.load()
    console = make_console(cfg.output_color)
    client = ArchClient(cfg)
    try:
        result = client.restore_core_thought(ct_id)
    except Exception as e:
        console.print(f"[red]✗ 恢复失败:[/red] {e}")
        sys.exit(1)
    console.print(f"[green]✓ 核心思想已恢复:[/green] {result['id'][:8]}")


@cli.command(name="seed-dao-governance", help="幂等 upsert 治理的道种子(从 memory 文件)")
def seed_dao_governance_cmd():
    """从 memory/dao-governance-philosophy.md 读取并幂等 upsert 第一条种子。

    策略:按 title 前缀查重(q="让人不必记规范"),命中则 update 增量字段,
    未命中则 create。失败任何一步都安全退出,不会留下半截数据。
    """
    cfg = Config.load()
    console = make_console(cfg.output_color)
    client = ArchClient(cfg)

    # 1. 读 memory 文件
    # P3.5 review 红旗 11:路径安全约束(防 ARCH_CORE_THOUGHT_SEED_PATH 被劫持读 /etc/passwd 等)
    seed_resolved = SEED_MEMORY_PATH.resolve()
    home_root = Path.home().resolve()
    if (
        not str(seed_resolved).startswith(str(home_root))
        or seed_resolved.suffix != ".md"
    ):
        console.print(
            f"[red]✗ 种子路径不安全:[/red] {seed_resolved}\n"
            f"  必须位于 home 目录({home_root})下且为 .md 后缀。"
            f"可通过环境变量 ARCH_CORE_THOUGHT_SEED_PATH 指向合法路径。"
        )
        sys.exit(1)

    if not seed_resolved.exists():
        console.print(
            f"[red]✗ 种子源文件不存在:[/red] {seed_resolved}\n"
            f"  可通过环境变量 ARCH_CORE_THOUGHT_SEED_PATH 覆盖路径。"
        )
        sys.exit(1)

    try:
        md_text = seed_resolved.read_text(encoding="utf-8")
    except Exception as e:
        console.print(f"[red]✗ 读取失败:[/red] {e}")
        sys.exit(1)

    # 2. 切片解析
    parsed = _parse_seed_sections(md_text)
    payload: dict = {
        "title": parsed["title"],
        "thesis": parsed["thesis"],
        "rationale": parsed["rationale"],
        "how_to_apply": parsed["how_to_apply"],
        "origin": SEED_ORIGIN,
        "proposer": SEED_PROPOSER,
        "status": SEED_STATUS,
        "tags": SEED_TAGS,
        "examples": [],
    }

    # 3. 查重
    try:
        # q 按 title 前缀特征搜索;若 list 支持 q 跨 title 模糊搜索
        existing = client.list_core_thoughts(q=SEED_TITLE_PREFIX, include_archived=True)
    except Exception as e:
        console.print(f"[red]✗ 查重失败:[/red] {e}")
        sys.exit(1)

    items = existing.get("items", [])
    # 兜底:即使 q 没命中,也按 title 严格匹配再扫一遍
    hit = next(
        (it for it in items if it.get("title", "").strip() == SEED_TITLE_PREFIX),
        None,
    )
    if hit is None:
        # 再用 list_core_thoughts_by_tag('dao') 兜底
        try:
            tagged = client.list_core_thoughts_by_tag("dao")
            hit = next(
                (it for it in tagged.get("items", [])
                 if it.get("title", "").strip() == SEED_TITLE_PREFIX),
                None,
            )
        except Exception:
            hit = None

    # 4. 幂等 upsert
    if hit is not None:
        ct_id = hit["id"]
        # update 增量字段(不覆盖 proposer / status / tags / examples,这些是稳定约束)
        update_payload = {
            "thesis": payload["thesis"],
            "rationale": payload["rationale"],
            "how_to_apply": payload["how_to_apply"],
            "origin": payload["origin"],
        }
        try:
            result = client.update_core_thought(ct_id, update_payload)
        except Exception as e:
            console.print(f"[red]✗ 更新失败:[/red] {e}")
            sys.exit(1)
        console.print(
            f"[green]✓ 种子已更新(id 已存在):[/green] {result['id'][:8]}\n"
            f"  {result['title']}"
        )
    else:
        try:
            result = client.create_core_thought(payload)
        except Exception as e:
            console.print(f"[red]✗ 创建失败:[/red] {e}")
            sys.exit(1)
        console.print(
            f"[green]✓ 种子已创建:[/green] {result['id'][:8]}\n"
            f"  {result['title']}"
        )
