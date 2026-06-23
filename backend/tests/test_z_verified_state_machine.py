"""REQ-69212ee4 — 状态机加 verified → triaged/rejected + reason 字段

业务规则(对齐 REQ-69212ee4 description):
- ALLOWED_TRANSITIONS[verified] 新增 {triaged, rejected}
- verified → triaged/rejected 必填 reason(≥10 字符),否则 422
- reason 会被拼到 description 末尾(用 "\n---\nreason: " 分隔)
- reason 触发 decided_at 写入(打回 = 重新评估的决策点)

测试约定(对齐 test_z_requirements_state_machine_error.py):
- 后端 fixture 启动在 127.0.0.1:8091(避开既有 8088/8089/8090)
- 每个 case 自己创建 draft req + component + version,推进到 verified,再触发转换
- assert 200/422 + reason 必填规则
"""
import os
import sys
import importlib
import threading
import time

# 必须在 import app 之前设环境变量
os.environ.pop("ARCH_API_BASE", None)
os.environ["ARCH_API_BASE"] = "http://127.0.0.1:8091"

import httpx
import pytest


@pytest.fixture(scope="module", autouse=True)
def _reload_proxy_to_pick_env():
    """强制 reload proxy,确保 ARCH_API_BASE=8091 生效"""
    if "app.ui.proxy" in sys.modules:
        importlib.reload(sys.modules["app.ui.proxy"])
    if "app.ui.routes" in sys.modules:
        importlib.reload(sys.modules["app.ui.routes"])
    yield


# ——— 后端 fixture(避开 test_ui.py 8088 / test_z_requirement_edit.py 8089 /
#     test_z_requirements_state_machine_error.py 8090) ———

@pytest.fixture(scope="module")
def backend():
    """启动 FastAPI 测试服务器 127.0.0.1:8091"""
    import uvicorn
    from app.main import app

    config = uvicorn.Config(app, host="127.0.0.1", port=8091, log_level="warning")
    server = uvicorn.Server(config)

    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    for _ in range(50):
        try:
            httpx.get("http://127.0.0.1:8091/healthz", timeout=1.0)
            break
        except Exception:
            time.sleep(0.1)

    yield "http://127.0.0.1:8091"

    server.should_exit = True
    thread.join(timeout=2)


def _auth_headers():
    api_key = os.environ.get("ARCH_PLATFORM_API_KEY", "")
    return {"X-API-Key": api_key} if api_key else {}


def _create_req(backend, suffix: str) -> str:
    """创建一个 draft 测试需求,返回 id"""
    r = httpx.post(
        f"{backend}/api/v1/requirements",
        json={
            "title": f"REQ-69212ee4 verified reopen 测试 - {suffix}",
            "type": "refactor",
            "priority": "P1",
            "description": "初始 description,用于验证 reason 拼接",
            "tags": ["test", "req-69212ee4"],
        },
        headers=_auth_headers(),
        timeout=5.0,
    )
    assert r.status_code == 201, f"create failed: {r.status_code} {r.text}"
    return r.json()["id"]


def _cleanup(backend, req_id: str):
    httpx.delete(f"{backend}/api/v1/requirements/{req_id}", headers=_auth_headers(), timeout=5.0)


def _patch_status(backend, req_id: str, status: str, **extra):
    """推进需求到指定状态,处理必填字段"""
    payload = {"status": status}
    payload.update(extra)
    # draft → triaged 必填 assignee
    if status == "triaged" and "assignee" not in payload:
        payload["assignee"] = "claude"
    r = httpx.patch(
        f"{backend}/api/v1/requirements/{req_id}",
        json=payload,
        headers=_auth_headers(),
        timeout=5.0,
    )
    return r


def _attach_component(backend, req_id: str) -> None:
    """为 req 关联 component + version(满足 implemented → verified 校验)"""
    from app.database import SessionLocal
    from app.models import Component, Version, Requirement

    db = SessionLocal()
    try:
        comp_id = f"test-comp-{req_id[:8]}"
        comp = Component(
            id=comp_id,
            name=f"test-comp-{req_id[:8]}",
            title="测试组件",
            positioning="用于 verified reopen 测试的临时组件",
            category="other",
            scope="tool",
            layer="L1_platform",
            is_asset=False,
        )
        db.add(comp)
        db.flush()
        ver = Version(
            id=f"test-ver-{req_id[:8]}",
            component_id=comp_id,
            version="0.0.1",
            semver_intent="patch",
            changelog="test",
        )
        db.add(ver)
        db.flush()
        comp.current_version_id = ver.id
        req = db.query(Requirement).filter_by(id=req_id).first()
        req.component_id = comp_id
        db.commit()
    finally:
        db.close()


def _advance_to_verified(backend, req_id: str) -> None:
    """把 req 推进到 verified 状态(走完整 main path)"""
    _attach_component(backend, req_id)
    for s in ["triaged", "scheduled", "in_progress", "implemented", "verified"]:
        r = _patch_status(backend, req_id, s)
        assert r.status_code == 200, f"推进 {s} 失败:{r.status_code} {r.text}"


# ===== REQ-69212ee4:3 个核心 case =====

def test_verified_to_triaged_with_reason_200(backend):
    """case 1:verified → triaged 带 reason → 200,description 末尾追加 reason 块"""
    req_id = _create_req(backend, "case-1-triaged-ok")
    try:
        _advance_to_verified(backend, req_id)

        reason_text = "验证发现 NFR 性能未达标,需要重新评估优先级"
        r = _patch_status(backend, req_id, "triaged", reason=reason_text)
        assert r.status_code == 200, (
            f"verified→triaged 带 reason 应 200,got {r.status_code}:{r.text}"
        )
        body = r.json()
        assert body["status"] == "triaged", f"status 应为 triaged,got {body['status']}"

        # reason 应拼到 description 末尾
        desc = body.get("description", "")
        assert "初始 description" in desc, f"原 description 应保留:got {desc!r}"
        assert "reason:" in desc, f"description 应含 reason 标记:got {desc!r}"
        assert reason_text in desc, f"description 应含完整 reason 文本:got {desc!r}"

        # decided_at 应被写入
        assert body.get("decided_at"), "decided_at 应被写入(打回 = 重新评估的决策点)"

        print(f"  → case 1 verified→triaged(reason): 200 + description 拼接 ✓")
    finally:
        _cleanup(backend, req_id)


def test_verified_to_triaged_without_reason_422(backend):
    """case 2:verified → triaged 无 reason → 422(reason 必填)"""
    req_id = _create_req(backend, "case-2-triaged-no-reason")
    try:
        _advance_to_verified(backend, req_id)

        r = _patch_status(backend, req_id, "triaged")
        assert r.status_code == 422, (
            f"verified→triaged 无 reason 应 422,got {r.status_code}:{r.text}"
        )
        # Pydantic schema 层的 min_length=10 也会触发 422
        # 应用层 _validate_transition 也会触发 422
        body_text = r.text
        # 两种可能的 422 来源:reason 字段校验 / 业务规则
        assert "reason" in body_text.lower() or "triaged" in body_text.lower(), (
            f"422 响应应提到 reason 或 triaged:got {body_text[:300]}"
        )

        # 显式再试 reason 太短(<10 字符)也应 422
        r2 = _patch_status(backend, req_id, "triaged", reason="太短")
        assert r2.status_code == 422, (
            f"reason<10 字符应 422,got {r2.status_code}:{r2.text}"
        )

        print(f"  → case 2 verified→triaged(无 reason): 422(reason 必填) ✓")
    finally:
        _cleanup(backend, req_id)


def test_verified_to_rejected_with_reason_200(backend):
    """case 3:verified → rejected 带 reason → 200,description 追加 reason 块"""
    req_id = _create_req(backend, "case-3-rejected-ok")
    try:
        _advance_to_verified(backend, req_id)

        reason_text = "线上回归发现 component 实现与 SOP 不符,直接 reject"
        r = _patch_status(backend, req_id, "rejected", reason=reason_text)
        assert r.status_code == 200, (
            f"verified→rejected 带 reason 应 200,got {r.status_code}:{r.text}"
        )
        body = r.json()
        assert body["status"] == "rejected", f"status 应为 rejected,got {body['status']}"

        # reason 应拼到 description 末尾
        desc = body.get("description", "")
        assert "初始 description" in desc, f"原 description 应保留:got {desc!r}"
        assert "reason:" in desc, f"description 应含 reason 标记:got {desc!r}"
        assert reason_text in desc, f"description 应含完整 reason 文本:got {desc!r}"

        # decided_at 应被写入(rejected 也算决策点)
        assert body.get("decided_at"), "decided_at 应被写入"

        print(f"  → case 3 verified→rejected(reason): 200 + description 拼接 ✓")
    finally:
        _cleanup(backend, req_id)
