"""app/ui/markdown_renderer.py — 把 docs/*.md 渲染成 HTML 片段

REQ-8be0f95c(2026-06-23):为架构平台自建 /help 路由,展示 docs/ 目录下的 markdown 文件。

复用原则(CLAUDE.md §3):
- 不自己写 markdown 解析器,直接用 mistune(纯 Python,fastapi 生态兼容)
- 代码高亮用 Pygments(mistune 的 renderer 钩子)
- 关注点分离:本模块只负责「读 .md → 转 HTML」,不涉及路由/模板

定位稳定性:本模块只服务 /help 路由,不做 cache(文档更新频率低),
不做搜索(搜索走 /search 路由 + 后端 API)。
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

import mistune
from pygments import highlight
from pygments.formatters.html import HtmlFormatter
from pygments.lexers import get_lexer_by_name, guess_lexer
from pygments.util import ClassNotFound


# ——— 路径配置 ———

# docs/ 路径解析:候选多个位置(本地开发 / 容器 / pip install editable)
#
# 本地开发:从文件路径反推 → <repo_root>/docs/
# 容器(Dockerfile):COPY docs/ /app/docs/
# pip install editable(./backend):文件被装到 /app/app/ui/markdown_renderer.py,
#   但 docs 仍可能在 /app/docs/ 或源仓库目录
#
# 我们用「候选路径 + 存在性探测」策略(跟 main.py:_seed_components_if_empty 模式一致)

def _resolve_docs_dir() -> Path:
    """从候选位置里挑第一个存在的 docs/ 目录"""
    candidates = [
        # 本地开发(从文件位置反推)
        Path(__file__).resolve().parent.parent.parent.parent / "docs",
        # 容器标准路径(Dockerfile: COPY docs/ /app/docs/)
        Path("/app/docs"),
        # pip install editable 但 source 还在原位
        Path("/app/../docs"),
    ]
    for c in candidates:
        try:
            c_resolved = c.resolve()
        except OSError:
            continue
        if c_resolved.is_dir() and any(c_resolved.rglob("*.md")):
            return c_resolved
    # 兜底:返回最可能的位置(即使不存在),让 list_markdown_files 返回 []
    return Path(__file__).resolve().parent.parent.parent.parent / "docs"


DOCS_DIR = _resolve_docs_dir()


# ——— 路径解析 → category ——

_CATEGORY_BY_PREFIX = [
    ("adr", "ADR"),
    ("components", "组件"),
    ("design", "设计"),
]

CATEGORY_ORDER = ["概述", "设计", "ADR", "组件"]


def _category_for(rel_path: Path) -> str:
    """从相对 docs/ 的路径推断 category

    规则:
    - docs/*.md           → 概述
    - docs/adr/*.md       → ADR
    - docs/components/*.md → 组件
    - docs/design/*.md    → 设计
    - 其他子目录          → 用子目录名(兜底)
    """
    parts = rel_path.parts
    if len(parts) == 1:
        return "概述"
    sub = parts[0]
    for prefix, label in _CATEGORY_BY_PREFIX:
        if sub == prefix:
            return label
    return sub


# ——— 标题抽取 ——

_H1_RE = re.compile(r"^#\s+(.+?)\s*$", re.MULTILINE)


def _extract_title(text: str, fallback: str) -> str:
    """从 markdown 文本中抽第一个 # 头;抽不到用 fallback"""
    m = _H1_RE.search(text)
    if m:
        return m.group(1).strip()
    return fallback


# ——— mistune + Pygments renderer ——

_PYGMENTS_FORMATTER = HtmlFormatter(  # 持久化 formatter,避免重复构造
    cssclass="codehilite",
    linenos=False,
    nobackground=True,
)


def _highlight(code: str, lang: str) -> str:
    """用 Pygments 高亮代码块;失败时回退到纯文本"""
    if lang:
        try:
            lexer = get_lexer_by_name(lang, stripall=True)
        except ClassNotFound:
            lexer = None
    else:
        lexer = None
    if lexer is None:
        try:
            lexer = guess_lexer(code)
        except ClassNotFound:
            from pygments.lexers.special import TextLexer
            lexer = TextLexer()
    return highlight(code, lexer, _PYGMENTS_FORMATTER)


class _PygmentsRenderer(mistune.HTMLRenderer):
    """mistune HTMLRenderer 子类,重写 block_code 走 Pygments 高亮"""

    def block_code(self, code: str, info: Optional[str] = None) -> str:  # type: ignore[override]
        lang = (info or "").strip().split(maxsplit=1)[0] if info else ""
        return _highlight(code, lang)


_MARKDOWN = mistune.create_markdown(
    renderer=_PygmentsRenderer(),
    plugins=["table", "strikethrough", "footnotes"],
)


# ——— 公开 API ——


def list_markdown_files() -> list[dict]:
    """列出 docs/ 下所有 .md,按 category + 文件名排序

    返回格式:
        [
            {
                "name": "er-diagram",
                "path": "er-diagram.md",          # 相对 docs/
                "slug": "er-diagram",              # URL slug(= name 不带 .md)
                "title": "架构平台 ER 图",         # 第一个 # 头
                "mtime": 1719123456.0,            # 文件 mtime
                "category": "概述",                 # 推断的分类
            },
            ...
        ]
    """
    if not DOCS_DIR.exists():
        return []

    items: list[dict] = []
    for md_path in sorted(DOCS_DIR.rglob("*.md")):
        rel = md_path.relative_to(DOCS_DIR)
        try:
            text = md_path.read_text(encoding="utf-8")
        except OSError:
            continue
        title = _extract_title(text, fallback=md_path.stem)
        items.append(
            {
                "name": md_path.stem,
                "path": str(rel),
                "slug": str(rel.with_suffix("")),
                "title": title,
                "mtime": md_path.stat().st_mtime,
                "category": _category_for(rel),
            }
        )

    # category 在前(按 CATEGORY_ORDER),同名按 name 升序
    cat_rank = {c: i for i, c in enumerate(CATEGORY_ORDER)}
    items.sort(key=lambda x: (cat_rank.get(x["category"], 99), x["name"]))
    return items


def list_markdown_files_grouped() -> list[dict]:
    """把 list_markdown_files() 按 category 分组

    返回:
        [
            {"category": "概述", "files": [...]},
            {"category": "设计", "files": [...]},
            ...
        ]
    """
    files = list_markdown_files()
    grouped: dict[str, list[dict]] = {}
    for f in files:
        grouped.setdefault(f["category"], []).append(f)

    # 按 CATEGORY_ORDER 输出,未识别的 category 排最后
    cat_rank = {c: i for i, c in enumerate(CATEGORY_ORDER)}
    sorted_cats = sorted(grouped.keys(), key=lambda c: cat_rank.get(c, 99))
    return [{"category": cat, "files": grouped[cat]} for cat in sorted_cats]


def resolve_slug(slug: str) -> Optional[Path]:
    """slug → docs/ 下的 .md 路径;不存在返回 None

    安全:slug 不允许 ../ 或绝对路径(防止越权读 docs 以外的文件)
    """
    if not slug or "/" in slug and slug.startswith("/"):
        return None
    # 去掉可能的尾部 /
    slug = slug.rstrip("/")
    if not slug:
        return None
    # 拒绝包含 .. 的路径片段
    if any(part == ".." for part in slug.split("/")):
        return None
    # 拼路径
    target = (DOCS_DIR / slug).with_suffix(".md")
    # 必须落在 DOCS_DIR 内(resolve 后比对,防 symlink 越界)
    try:
        target_resolved = target.resolve()
        docs_resolved = DOCS_DIR.resolve()
    except OSError:
        return None
    if not str(target_resolved).startswith(str(docs_resolved)):
        return None
    if not target_resolved.is_file():
        return None
    return target_resolved


def render_markdown_file(path: Path) -> str:
    """读 markdown 文件并返回渲染好的 HTML 字符串"""
    text = path.read_text(encoding="utf-8")
    return _MARKDOWN(text)


def get_pygments_css() -> str:
    """返回 Pygments 生成的 CSS(/help 页用,让代码高亮生效)

    内联在 detail.html 的 <style> 里,避免引入 /static 静态资源路径问题。
    """
    return _PYGMENTS_FORMATTER.get_style_defs(".codehilite")