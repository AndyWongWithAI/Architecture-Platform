"""Markdown → SQLite importer
读 docs/components/*.md(YAML frontmatter + Markdown body),写入 Component 表。
Phase 1.0:只导入 Component,不导入 Version / Deployment / Feedback。
"""
import os
from pathlib import Path
from typing import List
import frontmatter
from sqlalchemy.orm import Session

from ..models import (
    Component, Layer, Category, Scope, Language,
    DistributionForm, ComponentStatus,
)


class ImportResult:
    def __init__(self):
        self.created = 0
        self.updated = 0
        self.skipped = 0
        self.errors: List[str] = []

    def __repr__(self):
        return (
            f"ImportResult(created={self.created}, updated={self.updated}, "
            f"skipped={self.skipped}, errors={len(self.errors)})"
        )


class MarkdownImporter:
    """把 docs/components/*.md 导入数据库"""

    def __init__(self, db: Session, components_dir: str):
        self.db = db
        self.components_dir = Path(components_dir)

    def import_all(self) -> ImportResult:
        """导入目录下所有 .md(README.md 除外)"""
        result = ImportResult()
        if not self.components_dir.exists():
            result.errors.append(f"directory not found: {self.components_dir}")
            return result

        for md_file in sorted(self.components_dir.glob("*.md")):
            if md_file.name == "README.md":
                continue
            try:
                self._import_one(md_file, result)
            except Exception as e:
                result.errors.append(f"{md_file.name}: {e}")
        self.db.commit()
        return result

    def _import_one(self, md_file: Path, result: ImportResult):
        post = frontmatter.load(md_file)
        fm = post.metadata
        name = fm.get("name")
        if not name:
            result.errors.append(f"{md_file.name}: missing 'name'")
            result.skipped += 1
            return

        # 解析 enums(空字符串转 None)
        def enum_or_none(enum_cls, val):
            if val is None or val == "":
                return None
            try:
                return enum_cls(val)
            except ValueError:
                return None

        existing = self.db.query(Component).filter(Component.name == name).first()
        is_new = existing is None

        comp = existing or Component(
            id=_gen_uuid(),
            name=name,
        )

        comp.title = fm.get("title", name)
        comp.positioning = _extract_positioning(post.content) or fm.get("title", name)
        comp.category = enum_or_none(Category, fm.get("category")) or Category.other
        comp.scope = enum_or_none(Scope, fm.get("scope")) or Scope.tool
        comp.layer = enum_or_none(Layer, fm.get("layer")) or Layer.L1_platform
        comp.status = enum_or_none(ComponentStatus, fm.get("status")) or ComponentStatus.draft

        comp.atomic = bool(fm.get("atomic", True))
        comp.composed_of = fm.get("composed_of", []) or []
        comp.tags = fm.get("tags", []) or []
        comp.repo_url = _str_or_none(fm.get("repo_url"))
        comp.language = enum_or_none(Language, fm.get("language"))
        comp.package_name = _str_or_none(fm.get("package_name"))
        comp.install_command = _str_or_none(fm.get("install_command"))
        comp.usage_example = _str_or_none(fm.get("usage_example"))

        # 资产判定(2026-06-20 修订新增)
        comp.is_asset = bool(fm.get("is_asset", True))
        comp.distribution_form = enum_or_none(DistributionForm, fm.get("distribution_form"))
        comp.interface_contract = _str_or_none(fm.get("interface_contract"))
        comp.knowledge_artifact = bool(fm.get("knowledge_artifact", False))

        if is_new:
            self.db.add(comp)
            result.created += 1
        else:
            result.updated += 1

    def import_one(self, md_file: str) -> ImportResult:
        """导入单个文件"""
        result = ImportResult()
        try:
            self._import_one(Path(md_file), result)
        except Exception as e:
            result.errors.append(f"{md_file}: {e}")
        self.db.commit()
        return result


def _extract_positioning(body: str) -> str:
    """从 Markdown body 提取 ## 定位 段的内容"""
    if not body:
        return ""
    in_section = False
    lines = []
    for line in body.split("\n"):
        if line.strip().startswith("## "):
            if in_section:
                break
            if "定位" in line:
                in_section = True
                continue
        elif in_section:
            if line.strip():
                lines.append(line.strip())
    return " ".join(lines)[:500]


def _str_or_none(val) -> str | None:
    if val is None or val == "":
        return None
    return str(val)


def _gen_uuid() -> str:
    import uuid
    return str(uuid.uuid4())