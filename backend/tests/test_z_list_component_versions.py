"""后端 GET /components/{id}/versions 端点测试

覆盖 FB-6f84124c:arch CLI version list 报 405 修复。
之前该 endpoint 不存在(只有 POST 创建版本),CLI list 调 GET 直接 405。
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
from app.auth import require_api_key  # noqa: E402


@pytest.fixture
def client():
    app.dependency_overrides[require_api_key] = lambda: None
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _create_component(client, name: str) -> str:
    """创建一个组件(不开鉴权)"""
    r = client.post("/api/v1/components", json={
        "name": f"{name}-{uuid.uuid4().hex[:8]}",
        "title": f"Test {name}",
        "positioning": "用于 FB-6f84124c list versions 测试的临时组件,定位足够长。",
        "category": "other",
        "scope": "tool",
        "layer": "L0_infrastructure",
        "atomic": True,
        "is_asset": False,
    })
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_list_versions_returns_empty_for_new_component(client):
    """新组件 0 版本,GET 应返回 items=[], total=0(不再 405)"""
    comp_id = _create_component(client, "fb6f-empty")
    r = client.get(f"/api/v1/components/{comp_id}/versions")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["items"] == []
    assert data["total"] == 0


def test_list_versions_returns_created_versions(client):
    """创建 2 个版本后,GET 应按 created_at 倒序返回"""
    from unittest.mock import patch
    # 直接走 ORM 创建版本(API Key 创建需要鉴权)
    from app.database import SessionLocal
    from app.models import Version, SemverIntent

    comp_id = _create_component(client, "fb6f-with-ver")
    db = SessionLocal()
    try:
        v1 = Version(
            id=str(uuid.uuid4()),
            component_id=comp_id,
            version="0.1.0",
            semver_intent=SemverIntent.minor,
            changelog="init",
        )
        v2 = Version(
            id=str(uuid.uuid4()),
            component_id=comp_id,
            version="0.2.0",
            semver_intent=SemverIntent.minor,
            changelog="feat",
        )
        db.add(v1)
        db.add(v2)
        db.commit()
    finally:
        db.close()

    r = client.get(f"/api/v1/components/{comp_id}/versions")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["total"] == 2
    assert len(data["items"]) == 2
    # 倒序:v2 应在 v1 之前
    assert data["items"][0]["version"] == "0.2.0"
    assert data["items"][1]["version"] == "0.1.0"


def test_list_versions_accepts_name_or_id(client):
    """GET 端点应支持 name 或 id(component_id 路由已统一)"""
    # 创建并用 name 查
    from app.database import SessionLocal
    db = SessionLocal()
    try:
        comp_name = f"fb6f-name-{uuid.uuid4().hex[:8]}"
        r = client.post("/api/v1/components", json={
            "name": comp_name,
            "title": "test",
            "positioning": "用于 name vs id 路由测试的临时组件,定位足够长。",
            "category": "other",
            "scope": "tool",
            "layer": "L0_infrastructure",
            "atomic": True,
            "is_asset": False,
        })
        assert r.status_code == 201, r.text
    finally:
        db.close()

    r = client.get(f"/api/v1/components/{comp_name}/versions")
    assert r.status_code == 200, r.text
    assert r.json()["items"] == []


def test_list_versions_404_for_nonexistent_component(client):
    """不存在的组件应 404(非 405)"""
    r = client.get("/api/v1/components/nonexistent-component/versions")
    assert r.status_code == 404, r.text