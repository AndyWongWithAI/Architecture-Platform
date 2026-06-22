"""测试 ADR-0001 新增 schema 字段(REQ-1f45f486 Phase 3)

覆盖:
1. ComposedOfEntry.relation 字段(orchestration/peer/deployment + None)
2. ComponentBase.sub_layer 字段(pattern 校验 orchestration/normal)
3. ComponentBase.cross_cutting 字段
4. ComponentBase.runtime_dependency 字段
5. ComponentUpdate PATCH 兼容性(3 字段 Optional,None 默认)
"""
import pytest
from pydantic import ValidationError

from app.schemas import (
    ComposedOfEntry,
    ComponentBase,
    ComponentUpdate,
)


def test_composed_of_entry_relation_optional():
    """ComposedOfEntry.relation 可选(向后兼容 composed_of 旧用法)"""
    e1 = ComposedOfEntry(component_id="x", version_constraint="^1.0")
    assert e1.relation is None

    e2 = ComposedOfEntry(component_id="x", version_constraint="^1.0", relation="orchestration")
    assert e2.relation.value == "orchestration"


def test_component_base_sub_layer_pattern():
    """ComponentBase.sub_layer pattern 校验:仅 orchestration/normal"""
    base_kwargs = dict(
        name="test-comp",
        title="Test Component",
        positioning="用于测试 ADR-0001 新字段的 component",
        category="util",
        scope="tool",
        layer="L2_capability",
    )
    # 合法值
    c1 = ComponentBase(**base_kwargs, sub_layer="orchestration")
    assert c1.sub_layer == "orchestration"
    c2 = ComponentBase(**base_kwargs, sub_layer="normal")
    assert c2.sub_layer == "normal"
    c3 = ComponentBase(**base_kwargs, sub_layer=None)
    assert c3.sub_layer is None

    # 非法值
    with pytest.raises(ValidationError):
        ComponentBase(**base_kwargs, sub_layer="invalid")


def test_component_base_cross_cutting_default_false():
    """ComponentBase.cross_cutting 默认 False(向后兼容)"""
    base_kwargs = dict(
        name="test-comp",
        title="Test Component",
        positioning="用于测试 ADR-0001 新字段的 component",
        category="util",
        scope="tool",
        layer="L2_capability",
    )
    c = ComponentBase(**base_kwargs)
    assert c.cross_cutting is False
    c2 = ComponentBase(**base_kwargs, cross_cutting=True)
    assert c2.cross_cutting is True


def test_component_base_runtime_dependency_default_empty():
    """ComponentBase.runtime_dependency 默认空 list(向后兼容)"""
    base_kwargs = dict(
        name="test-comp",
        title="Test Component",
        positioning="用于测试 ADR-0001 新字段的 component",
        category="util",
        scope="tool",
        layer="L2_capability",
    )
    c = ComponentBase(**base_kwargs)
    assert c.runtime_dependency == []
    c2 = ComponentBase(
        **base_kwargs,
        runtime_dependency=[
            ComposedOfEntry(component_id="cli", version_constraint="^2", relation="deployment"),
        ],
    )
    assert len(c2.runtime_dependency) == 1
    assert c2.runtime_dependency[0].relation.value == "deployment"


def test_component_update_new_fields_optional():
    """ComponentUpdate 新字段 Optional,None 默认(PATCH 兼容)"""
    u1 = ComponentUpdate()
    assert u1.sub_layer is None
    assert u1.cross_cutting is None
    assert u1.runtime_dependency is None
    # composed_of 也应 Optional(FB-38f2024f 已修)
    assert u1.composed_of is None

    u2 = ComponentUpdate(sub_layer="orchestration", cross_cutting=True)
    assert u2.sub_layer == "orchestration"
    assert u2.cross_cutting is True


def test_component_update_sub_layer_pattern():
    """ComponentUpdate.sub_layer 也走 pattern 校验(非法值应抛 ValidationError)"""
    with pytest.raises(ValidationError):
        ComponentUpdate(sub_layer="invalid")
    # 合法值应通过
    u = ComponentUpdate(sub_layer="orchestration")
    assert u.sub_layer == "orchestration"
