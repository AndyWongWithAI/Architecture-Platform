"""REQ-d1deda65 组件软删除/恢复 — API 层

8 个测试用例:
1. test_delete_component_success_200 — 创建 atomic → delete → 200 + is_archived=true
2. test_delete_nonexistent_404 — delete 不存在的 id → 404
3. test_delete_already_archived_422 — 重复 delete → 422
4. test_delete_referenced_composite_409 — 创建复合组件 A(含 B)→ delete B → 409
5. test_delete_without_reason_422 — reason 长度 < 10 → 422(Pydantic Query min_length)
6. test_list_excludes_archived_by_default — delete 后 list 不见;include_archived=true 见到
7. test_restore_success_200 — delete → restore → is_archived=false
8. test_restore_not_archived_422 — restore 未归档组件 → 422

测试约定(对齐 test_z_requirements_state_machine_error.py):
- 后端 fixture 启动在 127.0.0.1:8091(避开 8088/8089/8090)
- 每个 case 自己创建测试 component,清理时 DELETE 一并归档
"""
import os
import sys
import importlib
import threading
import time
import uuid

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


# ——— 后端 fixture(避开 test_ui.py 8088 / test_z_requirement_edit.py 8089 / test_z_requirements_state_machine_error.py 8090)—

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


def _create_atomic_component(backend, suffix: str) -> str:
    """创建一个 atomic 测试组件,返回 name(用于后续 DELETE/PATCH/GET)"""
    name = f"pytest-del-{suffix}-{uuid.uuid4().hex[:6]}"
    r = httpx.post(
        f"{backend}/api/v1/components",
        json={
            "name": name,
            "title": f"pytest 删除测试组件 {suffix}",
            "positioning": "用于 REQ-d1deda65 组件删除/恢复测试的临时原子组件",
            "category": "other",
            "scope": "tool",
            "layer": "L1_platform",
            "is_asset": False,
            "atomic": True,
        },
        headers=_auth_headers(),
        timeout=5.0,
    )
    assert r.status_code == 201, f"create atomic failed: {r.status_code} {r.text}"
    return name


def _create_composite_component(backend, child_name: str, suffix: str) -> str:
    """创建引用 child_name 的复合组件"""
    name = f"pytest-compo-{suffix}-{uuid.uuid4().hex[:6]}"
    # 先查 child 的 id
    r = httpx.get(f"{backend}/api/v1/components/{child_name}", timeout=5.0)
    assert r.status_code == 200, f"get child failed: {r.text}"
    child_id = r.json()["id"]
    r = httpx.post(
        f"{backend}/api/v1/components",
        json={
            "name": name,
            "title": f"pytest 复合组件 {suffix}",
            "positioning": "用于 REQ-d1deda65 引用检查的临时复合组件",
            "category": "other",
            "scope": "tool",
            "layer": "L2_capability",
            "is_asset": False,
            "atomic": False,
            "composed_of": [{"component_id": child_id, "version_constraint": "^1.0"}],
        },
        headers=_auth_headers(),
        timeout=5.0,
    )
    assert r.status_code == 201, f"create composite failed: {r.status_code} {r.text}"
    return name


def _delete(backend, name: str, reason: str = "测试用临时删除-链路-不应保留-组件清理"):
    """DELETE 归档(忽略错误,用于 cleanup)"""
    return httpx.delete(
        f"{backend}/api/v1/components/{name}",
        params={"reason": reason},
        headers=_auth_headers(),
        timeout=5.0,
    )


# ===== 8 个核心 case =====

def test_delete_component_success_200(backend):
    """(1) atomic → delete → 200 + is_archived=true"""
    name = _create_atomic_component(backend, "ok-200")
    try:
        r = httpx.delete(
            f"{backend}/api/v1/components/{name}",
            params={"reason": "测试删除成功路径-链路-不应保留-cleanup"},
            headers=_auth_headers(),
            timeout=5.0,
        )
        assert r.status_code == 200, f"expected 200, got {r.status_code}:{r.text}"
        body = r.json()
        assert body["is_archived"] is True, f"is_archived 应为 True:got {body}"
        assert body["name"] == name
        # GET 还能取到详情(未真删,只软删)
        r2 = httpx.get(f"{backend}/api/v1/components/{name}", timeout=5.0)
        assert r2.status_code == 200
        assert r2.json()["is_archived"] is True
        print(f"  → case 1 atomic delete: 200 + is_archived=true ✓")
    finally:
        # 已归档,无需再清理(但 try 一下以防万一)
        _delete(backend, name)


def test_delete_nonexistent_404(backend):
    """(2) delete 不存在的 id → 404"""
    r = httpx.delete(
        f"{backend}/api/v1/components/nonexistent-comp-{uuid.uuid4().hex[:8]}",
        params={"reason": "测试删除不存在的组件-不应保留"},
        headers=_auth_headers(),
        timeout=5.0,
    )
    assert r.status_code == 404, f"expected 404, got {r.status_code}:{r.text}"
    print(f"  → case 2 delete nonexistent: 404 ✓")


def test_delete_already_archived_422(backend):
    """(3) 重复 delete → 422(对齐 Requirement archive 模式)"""
    name = _create_atomic_component(backend, "dup-422")
    try:
        # 第一次
        r1 = httpx.delete(
            f"{backend}/api/v1/components/{name}",
            params={"reason": "首次归档-测试用例-不应保留-cleanup"},
            headers=_auth_headers(),
            timeout=5.0,
        )
        assert r1.status_code == 200
        # 第二次
        r2 = httpx.delete(
            f"{backend}/api/v1/components/{name}",
            params={"reason": "再次归档-测试用例-不应保留-cleanup"},
            headers=_auth_headers(),
            timeout=5.0,
        )
        assert r2.status_code == 422, f"expected 422, got {r2.status_code}:{r2.text}"
        assert "already archived" in r2.text or "archived" in r2.text.lower()
        print(f"  → case 3 double delete: 422 + already archived ✓")
    finally:
        _delete(backend, name)


def test_delete_referenced_composite_409(backend):
    """(4) 创建复合组件 A(含 B)→ delete B → 409(被引用,先解除依赖)"""
    child_name = _create_atomic_component(backend, "child-409")
    parent_name = _create_composite_component(backend, child_name, "parent-409")
    try:
        r = httpx.delete(
            f"{backend}/api/v1/components/{child_name}",
            params={"reason": "试图删除被引用子组件-测试不应保留"},
            headers=_auth_headers(),
            timeout=5.0,
        )
        assert r.status_code == 409, f"expected 409, got {r.status_code}:{r.text}"
        body = r.json()
        # detail 可能是 str 也可能是 dict(取决于 FastAPI)
        detail_str = str(body.get("detail", ""))
        assert parent_name in detail_str or "referenced" in detail_str.lower(), (
            f"409 响应应提示被引用:got {detail_str}"
        )
        print(f"  → case 4 referenced delete: 409 + reference hint ✓")
    finally:
        # 清理:先 delete parent,再 delete child
        _delete(backend, parent_name)
        _delete(backend, child_name)


def test_delete_without_reason_422(backend):
    """(5) reason 长度 < 10 → 422(Pydantic Query min_length)"""
    name = _create_atomic_component(backend, "no-reason-422")
    try:
        r = httpx.delete(
            f"{backend}/api/v1/components/{name}",
            params={"reason": "short"},  # 仅 5 字符
            headers=_auth_headers(),
            timeout=5.0,
        )
        assert r.status_code == 422, f"expected 422, got {r.status_code}:{r.text}"
        # FastAPI 对 Query min_length 失败返回 422 with detail 列表
        body = r.json()
        assert "detail" in body
        print(f"  → case 5 short reason: 422 + min_length violation ✓")
    finally:
        _delete(backend, name)


def test_list_excludes_archived_by_default(backend):
    """(6) delete 后 list 默认不见;include_archived=true 见到"""
    suffix = f"list-{uuid.uuid4().hex[:6]}"
    name = _create_atomic_component(backend, suffix)
    try:
        # 先确认 list 见到
        r1 = httpx.get(f"{backend}/api/v1/components", params={"name": name}, timeout=5.0)
        assert r1.status_code == 200
        assert r1.json()["total"] == 1, f"创建后应能 list 到:{r1.json()}"

        # delete
        r_del = httpx.delete(
            f"{backend}/api/v1/components/{name}",
            params={"reason": "测试 list 默认过滤-不应保留-cleanup"},
            headers=_auth_headers(),
            timeout=5.0,
        )
        assert r_del.status_code == 200

        # 默认 list 看不到
        r2 = httpx.get(f"{backend}/api/v1/components", params={"name": name}, timeout=5.0)
        assert r2.status_code == 200
        assert r2.json()["total"] == 0, f"归档后默认 list 应过滤:{r2.json()}"

        # include_archived=true 能看到
        r3 = httpx.get(
            f"{backend}/api/v1/components",
            params={"name": name, "include_archived": "true"},
            timeout=5.0,
        )
        assert r3.status_code == 200
        assert r3.json()["total"] == 1, f"include_archived=true 应见到:{r3.json()}"
        print(f"  → case 6 list filter: default hides + include_archived sees ✓")
    finally:
        _delete(backend, name)


def test_restore_success_200(backend):
    """(7) delete → restore → is_archived=false"""
    name = _create_atomic_component(backend, "restore-ok")
    try:
        r_del = httpx.delete(
            f"{backend}/api/v1/components/{name}",
            params={"reason": "测试 restore 前置归档-不应保留-cleanup"},
            headers=_auth_headers(),
            timeout=5.0,
        )
        assert r_del.status_code == 200
        assert r_del.json()["is_archived"] is True

        r_rest = httpx.post(
            f"{backend}/api/v1/components/{name}/restore",
            headers=_auth_headers(),
            timeout=5.0,
        )
        assert r_rest.status_code == 200, f"restore 应 200, got {r_rest.status_code}:{r_rest.text}"
        assert r_rest.json()["is_archived"] is False
        # list 默认又能见到
        r_list = httpx.get(f"{backend}/api/v1/components", params={"name": name}, timeout=5.0)
        assert r_list.json()["total"] == 1
        print(f"  → case 7 delete+restore: 200 + is_archived=false ✓")
    finally:
        _delete(backend, name)


def test_restore_not_archived_422(backend):
    """(8) restore 未归档组件 → 422"""
    name = _create_atomic_component(backend, "restore-bad")
    try:
        r = httpx.post(
            f"{backend}/api/v1/components/{name}/restore",
            headers=_auth_headers(),
            timeout=5.0,
        )
        assert r.status_code == 422, f"expected 422, got {r.status_code}:{r.text}"
        assert "not archived" in r.text.lower() or "not archived" in str(r.json())
        print(f"  → case 8 restore not-archived: 422 + not archived ✓")
    finally:
        _delete(backend, name)
