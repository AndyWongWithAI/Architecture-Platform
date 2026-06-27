"""模板辅助函数:layer 颜色、severity 颜色、status 颜色、日期格式化

PicoCSS 友好的颜色命名(用 data 属性 + CSS 类):
- layer:primary/secondary/info/success/warning/danger
- severity:对应 severity 名称
- status:对应 status 名称
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional


# ——— 颜色映射(PicoCSS 友好)———

# layer → 颜色 class
LAYER_COLOR = {
    "L0_infrastructure": "pico-color-red-550",    # 底层 = 警示色(出问题影响大)
    "L1_platform": "pico-color-amber-550",         # 平台 = 警示黄
    "L2_capability": "pico-color-blue-550",        # 能力 = 蓝色
    "L3_application": "pico-color-green-550",      # 应用 = 绿色
}

# severity → 颜色
# REQ-010fb7b5:合并 feedback(4 档)+ audit(3 档)命名,共享一套颜色语义
# feedback: critical / high / medium / low
# audit:    blocker / warn / info(语义对齐:严重 → 警示色)
SEVERITY_COLOR = {
    # feedback(原值,保持不变)
    "critical": "pico-color-red-650",
    "high": "pico-color-orange-500",
    "medium": "pico-color-amber-450",
    "low": "pico-color-green-550",
    # audit(REQ-7328c640)合并命名 — 与 AUDIT_SEVERITY_COLOR 共享
    "blocker": "pico-color-red-650",
    "warn": "pico-color-amber-450",
    "info": "pico-color-blue-550",
}

# status → 颜色(feedback 模块通用)
STATUS_COLOR = {
    "open": "pico-color-amber-500",
    "triaged": "pico-color-blue-500",
    "fixing": "pico-color-cyan-500",
    "fixed": "pico-color-green-550",
    "wontfix": "pico-color-grey-500",
}

# decision → 颜色
DECISION_COLOR = {
    "optimize": "pico-color-green-550",
    "fork_new": "pico-color-blue-550",
    "keep_as_is": "pico-color-grey-500",
    "reassess_form": "pico-color-purple-550",
}


def layer_color(layer: str) -> str:
    return LAYER_COLOR.get(layer, "")


def severity_color(severity: Optional[str]) -> str:
    return SEVERITY_COLOR.get(severity or "", "")


def status_color(status: Optional[str]) -> str:
    return STATUS_COLOR.get(status or "", "")


def decision_color(decision: Optional[str]) -> str:
    return DECISION_COLOR.get(decision or "", "")


# ——— 文本格式化 ———

def short_id(uid: Optional[str], length: int = 8) -> str:
    """UUID 前 N 位缩写"""
    if not uid:
        return ""
    return uid[:length]


def format_dt(dt: Any) -> str:
    """格式化 datetime → '2026-06-20 21:34' 或空字符串"""
    if not dt:
        return ""
    if isinstance(dt, str):
        return dt[:16].replace("T", " ")
    if isinstance(dt, datetime):
        return dt.strftime("%Y-%m-%d %H:%M")
    return str(dt)


def truncate(text: Optional[str], length: int = 80) -> str:
    """文本截断 + 省略号"""
    if not text:
        return ""
    if len(text) <= length:
        return text
    return text[:length - 1] + "…"


def truncate_middle(text: Optional[str], max_len: int = 40) -> str:
    """文本中间截断 + 省略号

    适用于 URL / UUID / 长 ID 等需要保留首尾语义的可视化场景:
        "https://example.com/very/long/path/to/something" → "https://example.com/very…something"

    行为:
      - 长度 <= max_len:原样返回
      - 长度 >  max_len:保留前 ~60% / 后 ~30% 字符,中间加 …
    """
    if not text:
        return ""
    if max_len < 5:
        # 太短,直接 truncate 兜底
        return text[:max_len]
    if len(text) <= max_len:
        return text
    # 头 60% 尾 30%(保证 max_len 至少 5)
    keep_head = max(2, int(max_len * 0.6))
    keep_tail = max(2, max_len - keep_head - 1)
    return text[:keep_head] + "…" + text[-keep_tail:] if keep_tail else text[:keep_head] + "…"


def is_asset_badge(is_asset: bool) -> str:
    """资产标记:✓ 真资产 / ✗ 项目级"""
    return "✓ 真资产" if is_asset else "✗ 项目级"


def distribution_form_label(form: Optional[str]) -> str:
    """distribution_form 显示名(中英对照)"""
    labels = {
        "package": "包(pip/npm)",
        "container": "容器",
        "binary": "二进制",
        "source": "源码",
        "http_api": "HTTP API",
        "schema": "Schema",
        "dataset": "数据集",
        "config_template": "配置模板",
        "iac": "IaC(Terraform)",
        "skill": "Skill(AI)",
        "tool": "Tool(AI)",
    }
    return labels.get(form or "", "-")


# ——— FB-A 修复:enum 中英文映射 ———

# Literature tag 颜色(基于 tag 字符串 hash,稳定 → 同一 tag 同一颜色)
LIT_TAG_COLORS = [
    "pico-color-blue-550",
    "pico-color-green-550",
    "pico-color-amber-550",
    "pico-color-red-550",
    "pico-color-purple-550",
    "pico-color-cyan-550",
    "pico-color-pink-550",
    "pico-color-orange-500",
]


def lit_tag_color(tag: Optional[str]) -> str:
    """Literature tag → PicoCSS 颜色(确定性 hash → 同 tag 同颜色)"""
    if not tag:
        return ""
    return LIT_TAG_COLORS[hash(tag) % len(LIT_TAG_COLORS)]


LAYER_ZH = {
    "L0_infrastructure": "L0 基础设施",
    "L1_platform": "L1 平台",
    "L2_capability": "L2 能力",
    "L3_application": "L3 应用",
}

CATEGORY_ZH = {
    "auth": "认证",
    "db": "数据库",
    "cache": "缓存",
    "queue": "队列",
    "log": "日志",
    "deploy": "部署",
    "monitor": "监控",
    "ui": "界面",
    "util": "工具",
    "other": "其他",
}

STATUS_ZH = {
    "open": "待分诊",
    "triaged": "已分诊",
    "fixing": "修复中",
    "fixed": "已修复",
    "wontfix": "不修复",
}

DECISION_ZH = {
    "optimize": "优化组件",
    "fork_new": "新建组件",
    "keep_as_is": "保持不变",
    "reassess_form": "重审形态",
}

SEVERITY_ZH = {
    "critical": "致命",
    "high": "高",
    "medium": "中",
    "low": "低",
}

# Phase 1.2 Requirement 模块(2026-06-21)
REQ_PRIORITY_COLOR = {
    "P0": "pico-color-red-650",
    "P1": "pico-color-orange-500",
    "P2": "pico-color-amber-450",
    "P3": "pico-color-grey-500",
}

# REQ-010fb7b5:对齐 status_color 的设计 — 通用「生命周期」色板
# 草稿(draft)=灰;分诊/排期=蓝;进行中=青;已实现/已验证/已完成=绿;拒绝/取消=暗灰
REQ_STATUS_COLOR = {
    "draft": "pico-color-grey-500",
    "triaged": "pico-color-blue-500",
    "scheduled": "pico-color-blue-550",
    "in_progress": "pico-color-cyan-500",
    "implemented": "pico-color-green-550",
    "verified": "pico-color-green-550",
    "complete": "pico-color-green-650",
    "rejected": "pico-color-grey-500",
    "cancelled": "pico-color-grey-500",
}

# Audit Module(REQ-7328c640, 2026-06-23)
# audit finding severity 三档:info / warn / blocker
AUDIT_SEVERITY_COLOR = {
    "info": "pico-color-blue-550",
    "warn": "pico-color-amber-450",
    "blocker": "pico-color-red-650",
}

AUDIT_SEVERITY_ZH = {
    "info": "提示",
    "warn": "警告",
    "blocker": "阻塞",
}

REQ_PRIORITY_ZH = {"P0": "P0 紧急", "P1": "P1 高", "P2": "P2 普通", "P3": "P3 低"}

REQ_TYPE_ZH = {
    "new_feature": "新功能",
    "bug_fix": "Bug 修复",
    "refactor": "重构",
    "optimization": "优化",
    "compliance": "合规",
    "tech_debt": "技术债",
}

REQ_STATUS_ZH = {
    "draft": "草稿",
    "triaged": "已分诊",
    "scheduled": "已排期",
    "in_progress": "进行中",
    "implemented": "已实现",
    "verified": "已验证",
    "complete": "已完成",
    "rejected": "已拒绝",
    "cancelled": "已取消",
}


def req_priority_color(p: Optional[str]) -> str:
    return REQ_PRIORITY_COLOR.get(p or "", "")


def req_status_color(s: Optional[str]) -> str:
    """需求状态 → PicoCSS 颜色 class(对齐 status_color 的设计语言)"""
    return REQ_STATUS_COLOR.get(s or "", "")


def req_priority_zh(p: Optional[str]) -> str:
    return REQ_PRIORITY_ZH.get(p or "", p or "")


def req_type_zh(t: Optional[str]) -> str:
    return REQ_TYPE_ZH.get(t or "", t or "")


def req_status_zh(s: Optional[str]) -> str:
    return REQ_STATUS_ZH.get(s or "", s or "")


# ——— Audit Module(REQ-7328c640)———

def audit_severity_color(severity: Optional[str]) -> str:
    """audit finding severity → PicoCSS 颜色 class"""
    return AUDIT_SEVERITY_COLOR.get(severity or "", "")


def audit_severity_zh(severity: Optional[str]) -> str:
    """audit finding severity 中文化(info → 提示 / warn → 警告 / blocker → 阻塞)"""
    return AUDIT_SEVERITY_ZH.get(severity or "", severity or "")


def layer_zh(layer: Optional[str]) -> str:
    return LAYER_ZH.get(layer or "", layer or "")


def category_zh(category: Optional[str]) -> str:
    return CATEGORY_ZH.get(category or "", category or "")


def status_zh(status: Optional[str]) -> str:
    return STATUS_ZH.get(status or "", status or "")


def decision_zh(decision: Optional[str]) -> str:
    return DECISION_ZH.get(decision or "", decision or "")


def severity_zh(severity: Optional[str]) -> str:
    return SEVERITY_ZH.get(severity or "", severity or "")


# Jinja2 过滤器注册函数
def register_filters(env):
    """把上述函数注册为 Jinja2 过滤器"""
    env.filters["layer_color"] = layer_color
    env.filters["severity_color"] = severity_color
    env.filters["status_color"] = status_color
    env.filters["decision_color"] = decision_color
    env.filters["short_id"] = short_id
    env.filters["format_dt"] = format_dt
    env.filters["truncate"] = truncate
    env.filters["truncate_middle"] = truncate_middle
    env.filters["is_asset_badge"] = is_asset_badge
    env.filters["form_label"] = distribution_form_label
    # FB-A: 中文映射过滤器
    env.filters["layer_zh"] = layer_zh
    env.filters["category_zh"] = category_zh
    env.filters["status_zh"] = status_zh
    env.filters["decision_zh"] = decision_zh
    env.filters["severity_zh"] = severity_zh
    # Phase 1.2 Requirement
    env.filters["req_priority_color"] = req_priority_color
    env.filters["req_status_color"] = req_status_color
    env.filters["req_priority_zh"] = req_priority_zh
    env.filters["req_type_zh"] = req_type_zh
    env.filters["req_status_zh"] = req_status_zh
    # Literature(REQ-7c4bcb32,2026-06-23)
    env.filters["lit_tag_color"] = lit_tag_color
    # Audit Module(REQ-7328c640)
    env.filters["audit_severity_color"] = audit_severity_color
    env.filters["audit_severity_zh"] = audit_severity_zh
    # REQ-968b1c99(2026-06-27):core_thought detail 页 — 渲染 markdown 字段
    env.filters["markdown"] = _markdown_filter


# REQ-968b1c99(2026-06-27):core_thought detail 页用 — 渲染数据库存的 markdown 字段
def _markdown_filter(text):
    """Jinja2 过滤器:把 markdown 文本渲染成 HTML 片段(走 Pygments 代码高亮)"""
    from .markdown_renderer import render_markdown
    return render_markdown(text)
