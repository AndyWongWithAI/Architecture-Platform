"""REQ-ad545f78 状态机错误响应增强 — API 层

FB-b6311cf6 修复方案第 2 层(长期):422 body 必须包含
  - allowed_transitions: []
  - state_machine_doc: <SOP 链接>
  - suggestion: <明确路径文案>

帮 subagent 自我修正非法转换,不再依赖试错。

测试约定(对齐 test_z_requirement_edit.py):
- 后端 fixture 启动在 127.0.0.1:8090(避开 8088/8089)
- 每个 case 自己创建 draft req,推进到目标状态,再触发非法转换
- assert 422 + body 字段 + suggestion 含关键中文
"""
import os
import sys
import importlib
import threading
import time

# 必须在 import app 之前设环境变量
os.environ.pop("ARCH_API_BASE", None)
os.environ["ARCH_API_BASE"] = "http://127.0.0.1:8090"

import httpx
import pytest


@pytest.fixture(scope="module", autouse=True)
def _reload_proxy_to_pick_env():
    """强制 reload proxy,确保 ARCH_API_BASE=8090 生效(对齐 test_z_requirement_edit.py 模式)"""
    if "app.ui.proxy" in sys.modules:
        importlib.reload(sys.modules["app.ui.proxy"])
    if "app.ui.routes" in sys.modules:
        importlib.reload(sys.modules["app.ui.routes"])
    yield


# ——— 后端 fixture(避开 test_ui.py 8088 / test_z_requirement_edit.py 8089)—

@pytest.fixture(scope="module")
def backend():
    """启动 FastAPI 测试服务器 127.0.0.1:8090"""
    import uvicorn
    from app.main import app

    config = uvicorn.Config(app, host="127.0.0.1", port=8090, log_level="warning")
    server = uvicorn.Server(config)

    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    for _ in range(50):
        try:
            httpx.get("http://127.0.0.1:8090/healthz", timeout=1.0)
            break
        except Exception:
            time.sleep(0.1)

    yield "http://127.0.0.1:8090"

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
            "title": f"REQ-ad545f78 状态机错误增强测试 - {suffix}",
            "type": "tech_debt",
            "priority": "P2",
            "description": "用于状态机错误响应测试",
            "tags": ["test", "state-machine"],
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


def _assert_state_machine_422(r, current: str, attempted: str, expected_allowed: list):
    """统一断言:422 + body 含完整字段"""
    assert r.status_code == 422, (
        f"期望 422,got {r.status_code}:{r.text[:300]}"
    )
    body = r.json()
    detail = body.get("detail")
    assert isinstance(detail, dict), (
        f"期望 detail 是 dict,got {type(detail).__name__}:{detail}"
    )
    assert detail["current_status"] == current, f"current_status 不匹配:{detail}"
    assert detail["attempted_status"] == attempted, f"attempted_status 不匹配:{detail}"
    assert detail["allowed_transitions"] == expected_allowed, (
        f"allowed_transitions 不匹配:期望 {expected_allowed},got {detail.get('allowed_transitions')}"
    )
    assert "state_machine_doc" in detail, "缺少 state_machine_doc 字段"
    assert "specs/sdlc/SOP.md" in detail["state_machine_doc"], (
        f"state_machine_doc 应指向 SOP.md:got {detail['state_machine_doc']}"
    )
    suggestion = detail.get("suggestion", "")
    assert isinstance(suggestion, str) and len(suggestion) > 10, (
        f"suggestion 应是非空字符串:got {suggestion!r}"
    )
    # suggestion 应提到当前状态
    assert current in suggestion, (
        f"suggestion 应包含 current_status '{current}':got {suggestion!r}"
    )
    return detail


# ===== 4 个核心 case =====

def test_in_progress_to_verified_blocked(backend):
    """(a) in_progress → verified:非法,422 + allowed=[cancelled, implemented]"""
    req_id = _create_req(backend, "case-a")
    try:
        # 推进到 in_progress
        for s in ["triaged", "scheduled", "in_progress"]:
            r = _patch_status(backend, req_id, s)
            assert r.status_code == 200, f"推进 {s} 失败:{r.status_code} {r.text}"

        # 触发非法转换
        r = _patch_status(backend, req_id, "verified")
        detail = _assert_state_machine_422(r, "in_progress", "verified", ["cancelled", "implemented"])
        # suggestion 应提示先 implemented
        assert "implemented" in detail["suggestion"], (
            f"suggestion 应提示 implemented:got {detail['suggestion']!r}"
        )
        print(f"  → case (a) in_progress→verified: 422 + allowed=[implemented] + suggestion ✓")
    finally:
        _cleanup(backend, req_id)


def test_draft_to_scheduled_blocked(backend):
    """(b) draft → scheduled:非法,422 + allowed=[triaged]"""
    req_id = _create_req(backend, "case-b")
    try:
        # 直接从 draft 跳 scheduled
        r = _patch_status(backend, req_id, "scheduled")
        detail = _assert_state_machine_422(r, "draft", "scheduled", ["cancelled", "triaged"])
        # suggestion 应提示先 triaged
        assert "triaged" in detail["suggestion"], (
            f"suggestion 应提示 triaged:got {detail['suggestion']!r}"
        )
        print(f"  → case (b) draft→scheduled: 422 + allowed=[triaged,cancelled] + suggestion ✓")
    finally:
        _cleanup(backend, req_id)


def test_verified_to_in_progress_blocked(backend):
    """(c) verified → in_progress:非法,422 + allowed=['complete'] (REQ-b871169e:verified 不再是终态)"""
    req_id = _create_req(backend, "case-c")
    try:
        # 推进到 verified 需要 component 有 current_version_id — 跳过此 case 的全推进
        # 改用直接 SQL 标记为 verified(测试隔离,不走业务路径)
        # 或者我们走 main path 但跳过 verified 校验:先创建 component + version
        # 这里采用更简单方式:直接验证 state machine logic,通过创建一个 component
        from app.database import SessionLocal
        from app.models import Component, Version

        db = SessionLocal()
        try:
            # 创建 component + version 以满足 verified 校验
            comp_id = f"test-comp-{req_id[:8]}"
            comp = Component(
                id=comp_id,
                name=f"test-comp-{req_id[:8]}",
                title="测试组件",
                positioning="用于状态机错误测试的临时组件",
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
            # 关联 req 到 component
            req = db.query(__import__('app.models', fromlist=['Requirement']).Requirement).filter_by(id=req_id).first()
            req.component_id = comp_id
            db.commit()
        finally:
            db.close()

        # 推进:triaged → scheduled → in_progress → implemented → verified
        for s in ["triaged", "scheduled", "in_progress", "implemented", "verified"]:
            r = _patch_status(backend, req_id, s)
            assert r.status_code == 200, f"推进 {s} 失败:{r.status_code} {r.text}"

        # 触发非法转换:verified → in_progress
        # REQ-b871169e:verified 现在是中间态,只能往 complete 走
        r = _patch_status(backend, req_id, "in_progress")
        detail = _assert_state_machine_422(r, "verified", "in_progress", ["complete"])
        # suggestion 应提示先 complete
        assert "complete" in detail["suggestion"], (
            f"suggestion 应提示 complete:got {detail['suggestion']!r}"
        )
        print(f"  → case (c) verified→in_progress: 422 + allowed=['complete'] + suggestion ✓")
    finally:
        _cleanup(backend, req_id)


def test_implemented_to_verified_allowed(backend):
    """(d) implemented → verified:合法,200(确保增强没破坏合法路径)"""
    req_id = _create_req(backend, "case-d")
    try:
        # 关联 component + version 才能 verified
        from app.database import SessionLocal
        from app.models import Component, Version, Requirement

        db = SessionLocal()
        try:
            comp_id = f"test-comp-{req_id[:8]}"
            comp = Component(
                id=comp_id,
                name=f"test-comp-{req_id[:8]}",
                title="测试组件",
                positioning="用于状态机错误测试的临时组件",
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

        # 推进到 implemented
        for s in ["triaged", "scheduled", "in_progress", "implemented"]:
            r = _patch_status(backend, req_id, s)
            assert r.status_code == 200, f"推进 {s} 失败:{r.status_code} {r.text}"

        # implemented → verified:合法路径
        r = _patch_status(backend, req_id, "verified")
        assert r.status_code == 200, (
            f"合法转换 implemented→verified 应 200,got {r.status_code}:{r.text}"
        )
        assert r.json()["status"] == "verified"
        print(f"  → case (d) implemented→verified: 200(合法路径未被破坏) ✓")
    finally:
        _cleanup(backend, req_id)


# ===== 额外补充 case:suggestion 文案质量 =====

def test_suggestion_mentions_next_step(backend):
    """suggestion 应明确告诉 subagent 下一步该推哪个状态"""
    req_id = _create_req(backend, "case-e")
    try:
        # in_progress → verified 应提示先 implemented
        for s in ["triaged", "scheduled", "in_progress"]:
            _patch_status(backend, req_id, s)
        r = _patch_status(backend, req_id, "verified")
        body = r.json()
        suggestion = body["detail"]["suggestion"]
        # suggestion 必须:含 implemented + 含 verified(目标)
        assert "implemented" in suggestion
        assert "verified" in suggestion
        # 且不含模糊词「可能」「也许」(确定性文案)
        assert "可能" not in suggestion and "也许" not in suggestion, (
            f"suggestion 应确定不含模糊词:{suggestion!r}"
        )
        print(f"  → suggestion 文案含明确 next step: {suggestion}")
    finally:
        _cleanup(backend, req_id)


# ===== REQ-b871169e:complete 状态机 verified→complete 单向链 =====

def _create_req_with_component(backend, suffix: str) -> str:
    """创建 draft 测试需求 + 关联 component + version,以便推进到 verified"""
    req_id = _create_req(backend, suffix)
    from app.database import SessionLocal
    from app.models import Component, Version, Requirement

    db = SessionLocal()
    try:
        comp_id = f"test-comp-{req_id[:8]}"
        comp = Component(
            id=comp_id,
            name=f"test-comp-{req_id[:8]}",
            title="测试组件",
            positioning="用于 complete 状态机测试的临时组件",
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
    return req_id


def test_verified_to_complete_succeeds(backend):
    """REQ-b871169e (a):verified → complete 应为 200(单向链)"""
    req_id = _create_req_with_component(backend, "complete-a")
    try:
        # 推进到 verified
        for s in ["triaged", "scheduled", "in_progress", "implemented", "verified"]:
            r = _patch_status(backend, req_id, s)
            assert r.status_code == 200, f"推进 {s} 失败:{r.status_code} {r.text}"

        # verified → complete:合法路径
        r = _patch_status(backend, req_id, "complete")
        assert r.status_code == 200, (
            f"合法转换 verified→complete 应 200,got {r.status_code}:{r.text}"
        )
        assert r.json()["status"] == "complete"
        print(f"  → case (a) verified→complete: 200(单向链已通) ✓")
    finally:
        _cleanup(backend, req_id)


def test_implemented_to_complete_fails(backend):
    """REQ-b871169e (b):implemented → complete 应为 422(必须先过 verified)"""
    req_id = _create_req_with_component(backend, "complete-b")
    try:
        # 推进到 implemented(跳过 verified)
        for s in ["triaged", "scheduled", "in_progress", "implemented"]:
            r = _patch_status(backend, req_id, s)
            assert r.status_code == 200, f"推进 {s} 失败:{r.status_code} {r.text}"

        # implemented → complete:非法,必须先 verified
        r = _patch_status(backend, req_id, "complete")
        detail = _assert_state_machine_422(r, "implemented", "complete", ["in_progress", "verified"])
        # suggestion 应提示先 verified
        assert "verified" in detail["suggestion"], (
            f"suggestion 应提示 verified:got {detail['suggestion']!r}"
        )
        print(f"  → case (b) implemented→complete: 422 + 必须先 verified ✓")
    finally:
        _cleanup(backend, req_id)


def test_complete_is_terminal(backend):
    """REQ-b871169e (c):complete → in_progress 应为 422(终止态不可逆)"""
    req_id = _create_req_with_component(backend, "complete-c")
    try:
        # 推进到 complete
        for s in ["triaged", "scheduled", "in_progress", "implemented", "verified", "complete"]:
            r = _patch_status(backend, req_id, s)
            assert r.status_code == 200, f"推进 {s} 失败:{r.status_code} {r.text}"

        # complete → in_progress:非法,终止态不可逆
        r = _patch_status(backend, req_id, "in_progress")
        detail = _assert_state_machine_422(r, "complete", "in_progress", [])
        # suggestion 应包含「终止态」字样
        assert "终止态" in detail["suggestion"], (
            f"suggestion 应说明终态:got {detail['suggestion']!r}"
        )
        print(f"  → case (c) complete→in_progress: 422 + 终态不可逆 ✓")
    finally:
        _cleanup(backend, req_id)