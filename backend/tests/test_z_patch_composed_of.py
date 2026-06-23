"""后端 PATCH /components/{id} composed_of 字段测试

覆盖 FB-38f2024f + REQ-1f45f486 / ADR-0001:ComponentUpdate schema 已支持
composed_of / sub_layer / cross_cutting / runtime_dependency 字段。

按 [[feedback-test-ordering]] 约定,共享 DB/env 用 test_z_ 前缀排最后。
"""
from __future__ import annotations

import sys
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.main import app  # noqa: E402
from app.database import get_db  # noqa: E402
from app.auth import require_api_key  # noqa: E402


@pytest.fixture
def client():
    """绕过 API Key 鉴权(测试用),用真实 DB session"""
    app.dependency_overrides[require_api_key] = lambda: None
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _create_atomic(client, name: str):
    """helper:创建一个 atomic=true 的组件,返回其 id。name 自动加 UUID 后缀避免重名"""
    unique = f"{name}-{uuid.uuid4().hex[:8]}"
    r = client.post("/api/v1/components", json={
        "name": unique,
        "title": f"Test {unique}",
        "positioning": "用于 FB-38f2024f PATCH 测试的临时组件,定位足够长。",
        "category": "other",
        "scope": "tool",
        "layer": "L0_infrastructure",
        "atomic": True,
        "is_asset": False,
    })
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _create_child(client, name: str):
    return _create_atomic(client, name)


def test_patch_component_accepts_composed_of(client):
    """PATCH /components/{id} 应该接受 composed_of 字段(FB-38f2024f)"""
    parent_id = _create_atomic(client, "fb38f-parent")
    child_id = _create_child(client, "fb38f-child1")

    # atomic=true → composed_of 必须为空;先切到 atomic=false
    r = client.patch(f"/api/v1/components/{parent_id}", json={
        "atomic": False,
        "composed_of": [
            {"component_id": child_id, "version_constraint": "^1.0"},
        ],
    })
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["atomic"] is False
    assert len(data["composed_of"]) == 1
    assert data["composed_of"][0]["component_id"] == child_id
    assert data["composed_of"][0]["version_constraint"] == "^1.0"


def test_patch_component_accepts_sub_layer_and_cross_cutting(client):
    """PATCH 应同步支持 ADR-0001 的 sub_layer / cross_cutting"""
    comp_id = _create_atomic(client, "fb38f-adr0001")
    r = client.patch(f"/api/v1/components/{comp_id}", json={
        "sub_layer": "orchestration",
        "cross_cutting": True,
    })
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["sub_layer"] == "orchestration"
    assert data["cross_cutting"] is True


def test_patch_component_accepts_runtime_dependency(client):
    """PATCH 应支持 runtime_dependency 字段"""
    comp_id = _create_atomic(client, "fb38f-rtdep")
    target_id = _create_child(client, "fb38f-rtdep-target")
    r = client.patch(f"/api/v1/components/{comp_id}", json={
        "runtime_dependency": [
            {"component_id": target_id, "version_constraint": "^1.0", "relation": "peer"},
        ],
    })
    assert r.status_code == 200, r.text
    data = r.json()
    assert len(data["runtime_dependency"]) == 1
    assert data["runtime_dependency"][0]["relation"] == "peer"


def test_patch_atomic_with_composed_of_422(client):
    """业务规则:atomic=true 时 composed_of 必须为空(校验仍然生效)"""
    comp_id = _create_atomic(client, "fb38f-bizrule")
    child_id = _create_child(client, "fb38f-bizrule-child")
    r = client.patch(f"/api/v1/components/{comp_id}", json={
        "composed_of": [
            {"component_id": child_id, "version_constraint": "^1.0"},
        ],
        # 不改 atomic,沿用 True → 应触发业务规则 422
    })
    assert r.status_code == 422, r.text
    assert "atomic=true" in r.text and "composed_of" in r.text