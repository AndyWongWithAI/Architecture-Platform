"""Component → mermaid DSL 转换器(REQ-a77efd18)

设计要点:
- 输入:Component 对象(SQLAlchemy model)
- 输出:mermaid graph LR DSL 字符串
- 节点:组件自身 + 直接依赖的 component
- 边:composed_of → -->  ;runtime_dependency → -.->(虚线)
- subgraph 按 layer 分组(L0/L1/L2/L3 → 自下而上)
- 异常:
  - 找不到 component → 返回空字符串 + 注释
  - 无依赖 → 返回单节点
  - 循环依赖 → 用 mermaid 注释,不破坏渲染
"""
from __future__ import annotations

from typing import Iterable, List, Tuple

from sqlalchemy.orm import Session

from ..models import Component, Layer


# ===== 配色(对齐 PicoCSS 视觉风格)=====
LAYER_CLASS_DEFS = [
    ('L0', '#fee', '#c00', '基础设施层'),
    ('L1', '#ffd', '#a80', '平台层'),
    ('L2', '#ddf', '#06c', '能力层'),
    ('L3', '#dfd', '#080', '应用层'),
]

# Layer enum 值 → mermaid subgraph key
LAYER_TO_KEY = {
    Layer.L0_infrastructure: "L0",
    Layer.L1_platform: "L1",
    Layer.L2_capability: "L2",
    Layer.L3_application: "L3",
}

# L0 → L3 的渲染顺序(下层先画,mermaid LR 自动布局更自然)
LAYER_ORDER: List[Layer] = [
    Layer.L0_infrastructure,
    Layer.L1_platform,
    Layer.L2_capability,
    Layer.L3_application,
]


def _safe_id(name: str) -> str:
    """mermaid node id 必须是 [a-zA-Z_][a-zA-Z0-9_]*,- . 等会被解析错误
    这里用 - 替换为 _ 再前缀 'n_' 保证合法
    """
    cleaned = "".join(c if (c.isalnum() or c == "_") else "_" for c in name)
    if cleaned and cleaned[0].isdigit():
        cleaned = "n_" + cleaned
    return cleaned or "n_unknown"


def _node_label(name: str) -> str:
    """mermaid 节点 label — 用双引号包起来,允许特殊字符"""
    return f'"{name}"'


def _edge(a: str, b: str, kind: str, label: str | None = None) -> str:
    """生成 mermaid 边
    kind: 'solid'(composed_of) / 'dashed'(runtime_dependency)
    label: 可选,显示在边上
    """
    a_id = _safe_id(a)
    b_id = _safe_id(b)
    arrow = "-->" if kind == "solid" else "-.->"
    if label:
        return f"  {a_id} {arrow}|{label}| {b_id}"
    return f"  {a_id} {arrow} {b_id}"


def _collect_direct_dependencies(component: Component) -> Tuple[List[Tuple[str, str]], List[Tuple[str, str]]]:
    """从 component 的 composed_of / runtime_dependency 收集直接依赖
    返回 (composed_edges, runtime_edges) — 每项是 (from_name, to_name)
    composed_edges: 顶层 component → 子 component
    runtime_edges: 顶层 component → 运行时依赖 component
    """
    composed_edges: List[Tuple[str, str]] = []
    for entry in component.composed_of or []:
        to_id = entry.get("component_id") if isinstance(entry, dict) else None
        if to_id:
            composed_edges.append((component.name, to_id))

    runtime_edges: List[Tuple[str, str]] = []
    for entry in component.runtime_dependency or []:
        to_id = entry.get("component_id") if isinstance(entry, dict) else None
        if to_id:
            runtime_edges.append((component.name, to_id))

    return composed_edges, runtime_edges


def _resolve_components(
    db: Session, names: Iterable[str]
) -> dict[str, Component]:
    """批量按 name 查 Component,返回 {name: Component}
    找不到的 name 不在 dict 中(调用方跳过)
    """
    name_set = list(set(names))
    if not name_set:
        return {}
    rows = db.query(Component).filter(Component.name.in_(name_set)).all()
    return {row.name: row for row in rows}


def build_component_graph(component_name: str, db: Session) -> str:
    """返回 mermaid graph LR DSL 字符串,展示 component + 直接依赖

    参数:
        component_name: 按 Component.name 查询
        db: SQLAlchemy Session(由调用方注入,UI 层用 get_db())

    返回:
        mermaid DSL 字符串(可直接喂给 mermaid.initialize)

    异常处理:
        - 找不到 component → 注释 `%% component not found: {name}` + 返回空字符串
        - 无依赖 → 单节点 subgraph(自身)
        - 循环依赖 → `%% cycle: A<->B` 注释,不渲染该边(理论上不该有,composed_of 应是 DAG)
    """
    # 1. 查自身
    comp = db.query(Component).filter(Component.name == component_name).first()
    if not comp:
        return f"%% component not found: {component_name}\n"

    # 2. 收集直接依赖
    composed_edges, runtime_edges = _collect_direct_dependencies(comp)

    # 3. 查所有涉及的 component
    all_names = {comp.name}
    for _, to_id in composed_edges + runtime_edges:
        all_names.add(to_id)
    by_name = _resolve_components(db, all_names)

    # 4. 按 layer 分组 nodes
    layer_to_nodes: dict[str, list[str]] = {k: [] for k in ("L0", "L1", "L2", "L3")}
    for name in all_names:
        c = by_name.get(name)
        if not c:
            continue
        layer_key = LAYER_TO_KEY.get(c.layer, "L2")
        layer_to_nodes[layer_key].append(name)

    # 5. 检测循环(简单处理:composed_of 不该有环;若 from==to 跳过)
    seen_composed: set[tuple[str, str]] = set()
    seen_runtime: set[tuple[str, str]] = set()
    cycle_comments: list[str] = []
    for f, t in composed_edges:
        if f == t:
            cycle_comments.append(f"%% cycle: {f}<->{t}")
            continue
        seen_composed.add((f, t))
    for f, t in runtime_edges:
        if f == t:
            cycle_comments.append(f"%% cycle: {f}<->{t}")
            continue
        seen_runtime.add((f, t))

    # 6. 生成 DSL
    lines: list[str] = ["graph LR"]

    # classDef 配色
    for key, fill, stroke, _ in LAYER_CLASS_DEFS:
        lines.append(f"  classDef {key} fill:{fill},stroke:{stroke}")
    lines.append("")  # 空行分隔

    # subgraph + 节点定义
    for layer_enum in LAYER_ORDER:
        layer_key = LAYER_TO_KEY[layer_enum]
        nodes = sorted(layer_to_nodes.get(layer_key, []))
        if not nodes:
            continue
        # 找 layer 中文名
        zh = next((zh for k, _, _, zh in LAYER_CLASS_DEFS if k == layer_key), layer_key)
        lines.append(f'  subgraph {layer_key}["{zh}"]')
        for name in nodes:
            lines.append(f"    {_safe_id(name)}[{_node_label(name)}]")
        lines.append("  end")
    lines.append("")

    # 边
    if cycle_comments:
        for cc in cycle_comments:
            lines.append(cc)

    for f, t in sorted(seen_composed):
        # 只渲染端点都解析成功的边
        if f in by_name and t in by_name:
            lines.append(_edge(f, t, "solid", "composed_of"))
    for f, t in sorted(seen_runtime):
        if f in by_name and t in by_name:
            label = "runtime_dep"
            # 找 relation(若有)
            for entry in (comp.runtime_dependency or []):
                if isinstance(entry, dict) and entry.get("component_id") == t:
                    rel = entry.get("relation")
                    if rel:
                        label = f"runtime:{rel}"
                    break
            lines.append(_edge(f, t, "dashed", label))
    lines.append("")

    # 节点 class 绑定
    for layer_enum in LAYER_ORDER:
        layer_key = LAYER_TO_KEY[layer_enum]
        nodes = layer_to_nodes.get(layer_key, [])
        if not nodes:
            continue
        ids = " ".join(_safe_id(n) for n in sorted(nodes))
        lines.append(f"  class {ids} {layer_key}")

    # 末尾空行
    lines.append("")

    return "\n".join(lines)
