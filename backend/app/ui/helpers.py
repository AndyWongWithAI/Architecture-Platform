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
SEVERITY_COLOR = {
    "critical": "pico-color-red-650",
    "high": "pico-color-orange-500",
    "medium": "pico-color-amber-450",
    "low": "pico-color-green-550",
}

# status → 颜色
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
    env.filters["is_asset_badge"] = is_asset_badge
    env.filters["form_label"] = distribution_form_label