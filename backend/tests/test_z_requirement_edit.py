"""REQ-c7b6e4a4 需求编辑功能测试 — API + UI 端到端

测试目标:
- 验证 /requirements/{id}/edit GET 渲染表单
- 验证 POST 代理 PATCH 成功 + 字段更新
- 验证 JSON 字段(AC/nfr)校验
- 验证 title 在非 draft 状态被锁定(PATCH 端点强制)
- 验证不存在的 id → 404
"""
import os
import sys
# 必须在 import app 之前设环境变量 — proxy.py 在 import 时读 ARCH_API_BASE
# 用 pop + set 而不是 setdefault,因为 test_ui.py 可能先于本文件 import 了 proxy
os.environ.pop("ARCH_API_BASE", None)
os.environ["ARCH_API_BASE"] = "http://127.0.0.1:8089"

import subprocess
import threading
import time
import importlib

import httpx
import pytest


@pytest.fixture(scope="module", autouse=True)
def _reload_proxy_to_pick_env():
    """强制 reload proxy 模块,确保 ARCH_API_BASE=8089 生效

    pytest 在 collect 阶段会导入所有测试文件,proxy 已经被 import 过一次且
    API_BASE 被锁定。fixture autouse=True 在 module 作用域下保证本文件测试
    运行前重新加载。
    """
    if "app.ui.proxy" in sys.modules:
        importlib.reload(sys.modules["app.ui.proxy"])
    # 同时强制 ui.routes 重新加载(它已经持有 proxy 引用)
    if "app.ui.routes" in sys.modules:
        importlib.reload(sys.modules["app.ui.routes"])
    yield


# ——— 后端 fixture(对齐 test_ui.py 模式)——

@pytest.fixture(scope="module")
def backend():
    """启动 FastAPI 测试服务器 127.0.0.1:8089(避开 test_ui.py 用的 8088)"""
    import uvicorn
    from app.main import app

    config = uvicorn.Config(app, host="127.0.0.1", port=8089, log_level="warning")
    server = uvicorn.Server(config)

    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    for _ in range(50):
        try:
            httpx.get("http://127.0.0.1:8089/healthz", timeout=1.0)
            break
        except Exception:
            time.sleep(0.1)

    yield "http://127.0.0.1:8089"

    server.should_exit = True
    thread.join(timeout=2)


@pytest.fixture
def created_req(backend):
    """创建一个 draft 状态测试需求,测试后清理"""
    api_key = os.environ.get("ARCH_API_KEY", "")
    headers = {"X-API-Key": api_key} if api_key else {}

    r = httpx.post(
        f"{backend}/api/v1/requirements",
        json={
            "title": "REQ-c7b6e4a4 测试需求 - 不应保留 test-only",
            "type": "tech_debt",
            "priority": "P2",
            "description": "原始描述",
            "tags": ["test", "draft"],
        },
        headers=headers,
        timeout=5.0,
    )
    assert r.status_code == 201, f"创建需求失败:{r.status_code} {r.text}"
    req_id = r.json()["id"]
    yield {"id": req_id, "data": r.json()}

    # 清理:DELETE(archive)即可
    httpx.delete(f"{backend}/api/v1/requirements/{req_id}", headers=headers, timeout=5.0)


# ===== 编辑页 GET 渲染 =====

def test_edit_page_renders(backend, created_req):
    """GET /requirements/{id}/edit → 200 + 含 form 字段"""
    r = httpx.get(f"{backend}/requirements/{created_req['id']}/edit", timeout=5.0)
    assert r.status_code == 200, f"edit 页加载失败:{r.status_code}"
    text = r.text
    # 关键字段
    assert "编辑需求" in text
    assert 'name="title"' in text
    assert 'name="description"' in text
    assert 'name="user_story"' in text
    assert 'name="acceptance_criteria"' in text
    assert 'name="nfr"' in text
    assert 'name="priority"' in text
    assert 'name="assignee"' in text
    assert 'name="due_date"' in text
    assert 'name="tags"' in text
    # draft 状态下 title 不锁定
    assert "readonly" not in text.split('name="title"')[1].split(">")[0]
    # 预填值
    assert "原始描述" in text
    # tags CSV 预填(_prepare_req_for_edit 用 ", " 连接)
    assert 'value="test, draft"' in text
    print(f"  → GET /requirements/{created_req['id'][:8]}/edit: 200 + form 字段齐 ✓")


def test_edit_page_404_for_missing(backend):
    """编辑不存在需求 → 404"""
    r = httpx.get(f"{backend}/requirements/00000000-0000-0000-0000-000000000000/edit", timeout=5.0)
    assert r.status_code == 404


# ===== POST 代理 PATCH =====

def test_edit_submit_full_fields(backend, created_req):
    """POST 编辑全部字段 → 303 重定向 → 后端数据已更新"""
    import json as _json
    req_id = created_req["id"]

    ac = [{"given": "g1", "when": "w1", "then": "t1"}]
    nfr = {"performance": "< 100ms p99"}

    r = httpx.post(
        f"{backend}/requirements/{req_id}/edit",
        data={
            "title": "REQ-c7b6e4a4 测试需求 - 已编辑 title 不应保留 test-only",
            "description": "已更新的描述",
            "user_story": "As a dev, I want edit, so that iterate fast",
            "acceptance_criteria": _json.dumps(ac, ensure_ascii=False),
            "nfr": _json.dumps(nfr, ensure_ascii=False),
            "priority": "P1",
            "assignee": "claude",
            "due_date": "2026-07-15",
            "tags": "edited, full, test",
        },
        follow_redirects=False,
        timeout=5.0,
    )
    assert r.status_code == 303, f"期望 303,got {r.status_code}:{r.text[:300]}"
    assert r.headers.get("location", "").endswith(f"/requirements/{req_id}")

    # 验证后端
    chk = httpx.get(f"{backend}/api/v1/requirements/{req_id}", timeout=5.0)
    assert chk.status_code == 200
    data = chk.json()
    assert data["description"] == "已更新的描述"
    assert data["user_story"] == "As a dev, I want edit, so that iterate fast"
    assert data["acceptance_criteria"] == ac
    assert data["nfr"] == nfr
    assert data["priority"] == "P1"
    assert data["assignee"] == "claude"
    assert data["tags"] == ["edited", "full", "test"]
    print(f"  → POST full edit: 303 + 全部字段已持久化 ✓")


def test_edit_submit_partial_fields(backend, created_req):
    """POST 只改 description,其他字段不被覆盖"""
    req_id = created_req["id"]

    # 先重置 description 为已知值
    httpx.post(
        f"{backend}/requirements/{req_id}/edit",
        data={"description": "partial 测试 - 原始 description 不应保留 test-only"},
        follow_redirects=False,
        timeout=5.0,
    )

    # 只改 priority
    r = httpx.post(
        f"{backend}/requirements/{req_id}/edit",
        data={"priority": "P3"},
        follow_redirects=False,
        timeout=5.0,
    )
    assert r.status_code == 303

    chk = httpx.get(f"{backend}/api/v1/requirements/{req_id}", timeout=5.0).json()
    assert chk["priority"] == "P3"
    # description 应保留(之前写入的值)
    assert "partial 测试" in chk["description"]
    print(f"  → POST partial edit: priority 改 + description 保留 ✓")


def test_edit_submit_invalid_ac_json(backend, created_req):
    """POST 非法 AC JSON → 422"""
    r = httpx.post(
        f"{backend}/requirements/{created_req['id']}/edit",
        data={"acceptance_criteria": "{not valid json"},
        follow_redirects=False,
        timeout=5.0,
    )
    assert r.status_code == 422, f"非法 JSON 应被 422 拒绝,got {r.status_code}"
    assert "JSON 解析失败" in r.text
    print(f"  → POST invalid AC JSON: 422 ✓")


def test_edit_submit_invalid_nfr_json(backend, created_req):
    """POST 非法 NFR JSON(不是 dict)→ 422"""
    import json as _json
    r = httpx.post(
        f"{backend}/requirements/{created_req['id']}/edit",
        data={"nfr": _json.dumps([1, 2, 3])},  # 数组而非 dict
        follow_redirects=False,
        timeout=5.0,
    )
    assert r.status_code == 422
    assert "JSON 解析失败" in r.text
    print(f"  → POST invalid NFR JSON (非 dict): 422 ✓")


# ===== 后端 PATCH 端点 title 锁定 =====

def test_patch_title_locked_in_non_draft(backend, created_req):
    """直接 PATCH:在非 draft 状态改 title → 422"""
    req_id = created_req["id"]
    api_key = os.environ.get("ARCH_API_KEY", "")
    headers = {"X-API-Key": api_key} if api_key else {}

    # 推进到 triaged 状态
    r = httpx.patch(
        f"{backend}/api/v1/requirements/{req_id}",
        json={"status": "triaged", "assignee": "claude"},
        headers=headers,
        timeout=5.0,
    )
    assert r.status_code == 200, f"推进 triaged 失败:{r.status_code} {r.text}"

    # 此时改 title 应被拒
    r = httpx.patch(
        f"{backend}/api/v1/requirements/{req_id}",
        json={"title": "试图改 title 但状态已锁定 - 不应保留"},
        headers=headers,
        timeout=5.0,
    )
    assert r.status_code == 422, f"非 draft 改 title 应被拒,got {r.status_code}"
    assert "draft" in r.text.lower()
    print(f"  → PATCH title in non-draft: 422 (CLAUDE.md 定位稳定性锁定) ✓")


def test_patch_404_for_missing(backend):
    """PATCH 不存在 id → 404"""
    api_key = os.environ.get("ARCH_API_KEY", "")
    headers = {"X-API-Key": api_key} if api_key else {}
    r = httpx.patch(
        f"{backend}/api/v1/requirements/00000000-0000-0000-0000-000000000000",
        json={"description": "x"},
        headers=headers,
        timeout=5.0,
    )
    assert r.status_code == 404


def test_patch_tags_support(backend, created_req):
    """tags 字段 PATCH 支持(Phase 1 findings 错的,schema 已支持)"""
    req_id = created_req["id"]
    api_key = os.environ.get("ARCH_API_KEY", "")
    headers = {"X-API-Key": api_key} if api_key else {}

    r = httpx.patch(
        f"{backend}/api/v1/requirements/{req_id}",
        json={"tags": ["new1", "new2", "ui-edit-test"]},
        headers=headers,
        timeout=5.0,
    )
    assert r.status_code == 200
    assert sorted(r.json()["tags"]) == ["new1", "new2", "ui-edit-test"]
    print(f"  → PATCH tags 字段: 200 + 持久化 ✓")


def test_edit_page_shows_title_locked_for_non_draft(backend, created_req):
    """非 draft 状态下,编辑页 title 字段应 readonly"""
    req_id = created_req["id"]
    api_key = os.environ.get("ARCH_API_KEY", "")
    headers = {"X-API-Key": api_key} if api_key else {}

    # 推进到 triaged
    httpx.patch(
        f"{backend}/api/v1/requirements/{req_id}",
        json={"status": "triaged", "assignee": "claude"},
        headers=headers,
        timeout=5.0,
    )

    r = httpx.get(f"{backend}/requirements/{req_id}/edit", timeout=5.0)
    assert r.status_code == 200
    # title input 应含 readonly + disabled
    title_input = r.text.split('name="title"')[1].split(">")[0]
    assert "readonly" in title_input
    assert "disabled" in title_input
    print(f"  → GET edit page for non-draft: title readonly+disabled ✓")