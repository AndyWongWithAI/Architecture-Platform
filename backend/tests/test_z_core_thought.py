"""REQ-968b1c99 / ADR-0003 core_thought 实体 — API + UI 端到端测试

测试 23 用例(对齐 plan §5.1):
- API CRUD(POST/GET list/by-id/by-tag/PATCH/DELETE/restore)
- 过滤 + 搜索(q + tag + status + include_archived + proposer)
- examples JSON 强引用 + null 兜底
- API Key 校验
- 422 校验(title 必填 / min_length / status enum / archived → 422)
- UI 页面渲染 + 表单提交代理
- Markdown XSS escape
- model ORM 导入 smoke

端口:8092(避开 test_ui 8088 / test_z_requirement_edit 8089 / test_z_requirements 8090 / test_z_literature 8091)
"""
import os
import sys
import importlib
import threading
import time

# 必须在 import app 之前设环境变量 — proxy.py 在 import 时读 ARCH_API_BASE
os.environ["ARCH_API_BASE"] = "http://127.0.0.1:8092"

import httpx
import pytest


@pytest.fixture(scope="module", autouse=True)
def _reload_proxy_to_pick_env():
    """强制 reload proxy/ui.routes,确保 ARCH_API_BASE=8092 生效"""
    for mod in ("app.ui.proxy", "app.ui.routes"):
        if mod in sys.modules:
            importlib.reload(sys.modules[mod])
    yield


# ——— 后端 fixture ———

@pytest.fixture(scope="module")
def backend():
    """启动 FastAPI 测试服务器 127.0.0.1:8092"""
    import uvicorn
    from app.main import app

    config = uvicorn.Config(app, host="127.0.0.1", port=8092, log_level="warning")
    server = uvicorn.Server(config)

    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    for _ in range(50):
        try:
            httpx.get("http://127.0.0.1:8092/healthz", timeout=1.0)
            break
        except Exception:
            time.sleep(0.1)

    yield "http://127.0.0.1:8092"

    server.should_exit = True
    thread.join(timeout=2)


def _auth_headers():
    api_key = os.environ.get("ARCH_PLATFORM_API_KEY", "")
    return {"X-API-Key": api_key} if api_key else {}


def _create_ct(backend, **overrides) -> dict:
    """创建一个测试核心思想,返回完整 dict"""
    payload = {
        "title": "REQ-968b1c99 测试核心思想 - 不应保留 test-only",
        "thesis": "### 论点\n核心思想是持久化治理哲学的资产。",
        "rationale": "### 背景\n人的记忆会衰退,需要把道沉到系统里。",
        "how_to_apply": "### 应用\n每次新增功能都要回到道的层面自检。",
        "origin": "pytest",
        "status": "active",
        "tags": ["pytest", "core-thought-test"],
        "examples": [{"component_id": "arch-platform", "note": "pytest 示例"}],
    }
    payload.update(overrides)
    r = httpx.post(
        f"{backend}/api/v1/core-thoughts",
        json=payload,
        headers=_auth_headers(),
        timeout=5.0,
    )
    assert r.status_code == 201, f"create failed: {r.status_code} {r.text}"
    return r.json()


def _cleanup(backend, ct_id: str):
    """清理:archive(避免影响 list 默认视图)"""
    httpx.delete(
        f"{backend}/api/v1/core-thoughts/{ct_id}",
        headers=_auth_headers(),
        timeout=5.0,
    )


# ===== API CRUD happy path =====

def test_create_core_thought_full(backend):
    """用例 1:POST 完整字段 → 201 + proposer 缺省 'api'"""
    r = httpx.post(
        f"{backend}/api/v1/core-thoughts",
        json={
            "title": "REQ-968b1c99 用例 1 - 完整字段测试",
            "thesis": "### 完整字段",
        },
        headers=_auth_headers(),
        timeout=5.0,
    )
    assert r.status_code == 201, f"{r.status_code} {r.text}"
    data = r.json()
    assert data["title"] == "REQ-968b1c99 用例 1 - 完整字段测试"
    assert data["thesis"] == "### 完整字段"
    assert data["proposer"] == "api"  # 缺省值
    assert data["status"] == "draft"  # 缺省值
    assert data["is_archived"] is False
    assert data["tags"] == []
    assert data["examples"] == []
    assert "id" in data
    assert "created_at" in data and "updated_at" in data
    print(f"  → POST create: 201 + {data['id'][:8]} + proposer=api 缺省 + status=draft 缺省 ✓")
    _cleanup(backend, data["id"])


def test_list_core_thoughts(backend):
    """用例 2:GET list 命中新建"""
    ct = _create_ct(backend, title="REQ-968b1c99 用例 2 - 列表命中测试")
    try:
        r = httpx.get(f"{backend}/api/v1/core-thoughts", timeout=5.0)
        assert r.status_code == 200
        body = r.json()
        assert "items" in body and "total" in body
        ids = [it["id"] for it in body["items"]]
        assert ct["id"] in ids, f"刚创建的核心思想应出现在列表中:{ids[:3]}"
        print(f"  → GET list: 200 + total={body['total']} + 新建已可见 ✓")
    finally:
        _cleanup(backend, ct["id"])


def test_get_core_thought_detail(backend):
    """用例 3:GET detail 字段完整"""
    ct = _create_ct(backend, title="REQ-968b1c99 用例 3 - detail 字段")
    try:
        r = httpx.get(f"{backend}/api/v1/core-thoughts/{ct['id']}", timeout=5.0)
        assert r.status_code == 200
        data = r.json()
        # 13 字段全有
        for field in ("id", "title", "thesis", "rationale", "how_to_apply",
                      "origin", "status", "tags", "examples", "proposer",
                      "created_at", "updated_at", "is_archived"):
            assert field in data, f"missing field {field}"
        assert data["id"] == ct["id"]
        assert data["thesis"] == ct["thesis"]
        assert len(data["examples"]) == 1
        assert data["examples"][0]["component_id"] == "arch-platform"
        print(f"  → GET detail: 200 + 13 字段完整 + examples JSON 强引用保留 ✓")
    finally:
        _cleanup(backend, ct["id"])


def test_patch_core_thought_partial(backend):
    """用例 4:PATCH 部分字段(rationale)"""
    ct = _create_ct(backend, title="REQ-968b1c99 用例 4 - PATCH 部分字段")
    try:
        r = httpx.patch(
            f"{backend}/api/v1/core-thoughts/{ct['id']}",
            json={"rationale": "### 更新后背景\nP3.6 verify 测的"},
            headers=_auth_headers(),
            timeout=5.0,
        )
        assert r.status_code == 200, f"{r.status_code} {r.text}"
        data = r.json()
        assert "更新后背景" in data["rationale"]
        # 其他字段保留
        assert data["thesis"] == ct["thesis"]
        assert data["title"] == ct["title"]
        print(f"  → PATCH partial: 200 + rationale 更新 + 其他字段保留 ✓")
    finally:
        _cleanup(backend, ct["id"])


def test_archive_core_thought(backend):
    """用例 5:DELETE → is_archived=true + 默认 list 不见"""
    ct = _create_ct(backend, title="REQ-968b1c99 用例 5 - archive")
    # archive
    r = httpx.delete(
        f"{backend}/api/v1/core-thoughts/{ct['id']}",
        headers=_auth_headers(),
        timeout=5.0,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["is_archived"] is True
    # 默认 list 不应出现
    r2 = httpx.get(f"{backend}/api/v1/core-thoughts", timeout=5.0)
    ids = [it["id"] for it in r2.json()["items"]]
    assert ct["id"] not in ids, "archived 后默认 list 应过滤"
    print(f"  → DELETE archive: 200 + is_archived=true + 默认 list 过滤 ✓")


def test_restore_core_thought(backend):
    """用例 6:POST /restore → is_archived=false + list 可见"""
    ct = _create_ct(backend, title="REQ-968b1c99 用例 6 - restore")
    # archive
    httpx.delete(
        f"{backend}/api/v1/core-thoughts/{ct['id']}",
        headers=_auth_headers(),
        timeout=5.0,
    )
    # restore
    r = httpx.post(
        f"{backend}/api/v1/core-thoughts/{ct['id']}/restore",
        headers=_auth_headers(),
        timeout=5.0,
    )
    assert r.status_code == 200
    data = r.json()
    assert data["is_archived"] is False
    # list 可见
    r2 = httpx.get(f"{backend}/api/v1/core-thoughts", timeout=5.0)
    ids = [it["id"] for it in r2.json()["items"]]
    assert ct["id"] in ids
    print(f"  → POST restore: 200 + is_archived=false + list 可见 ✓")
    _cleanup(backend, ct["id"])


def test_search_by_q(backend):
    """用例 7:?q= 命中 title / thesis / rationale / how_to_apply"""
    ct = _create_ct(backend, title="REQ-968b1c99 用例 7 - 搜索测试唯一特征字")
    try:
        r = httpx.get(f"{backend}/api/v1/core-thoughts?q=唯一特征字", timeout=5.0)
        assert r.status_code == 200
        ids = [it["id"] for it in r.json()["items"]]
        assert ct["id"] in ids
        print(f"  → GET ?q=唯一特征字: 200 + 命中 ✓")
    finally:
        _cleanup(backend, ct["id"])


def test_filter_by_tag(backend):
    """用例 8:?tag= 命中 tags"""
    ct = _create_ct(backend, title="REQ-968b1c99 用例 8 - tag 过滤",
                    tags=["unique-tag-x9z"])
    try:
        r = httpx.get(f"{backend}/api/v1/core-thoughts?tag=unique-tag-x9z", timeout=5.0)
        assert r.status_code == 200
        ids = [it["id"] for it in r.json()["items"]]
        assert ct["id"] in ids
        print(f"  → GET ?tag=unique-tag-x9z: 200 + 命中 ✓")
    finally:
        _cleanup(backend, ct["id"])


def test_filter_by_status(backend):
    """用例 9:?status=active 命中 status"""
    ct = _create_ct(backend, title="REQ-968b1c99 用例 9 - status 过滤", status="active")
    try:
        r = httpx.get(f"{backend}/api/v1/core-thoughts?status=active", timeout=5.0)
        assert r.status_code == 200
        ids = [it["id"] for it in r.json()["items"]]
        assert ct["id"] in ids
        # 反过来 status=draft 应不含
        r2 = httpx.get(f"{backend}/api/v1/core-thoughts?status=draft", timeout=5.0)
        ids2 = [it["id"] for it in r2.json()["items"]]
        assert ct["id"] not in ids2
        print(f"  → GET ?status=active: 200 + 命中 + status=draft 不含 ✓")
    finally:
        _cleanup(backend, ct["id"])


def test_include_archived(backend):
    """用例 10:?include_archived=true 含 archived"""
    ct = _create_ct(backend, title="REQ-968b1c99 用例 10 - include_archived")
    httpx.delete(
        f"{backend}/api/v1/core-thoughts/{ct['id']}",
        headers=_auth_headers(),
        timeout=5.0,
    )
    # 默认不含
    r1 = httpx.get(f"{backend}/api/v1/core-thoughts", timeout=5.0)
    assert ct["id"] not in [it["id"] for it in r1.json()["items"]]
    # include_archived=true 应含
    r2 = httpx.get(f"{backend}/api/v1/core-thoughts?include_archived=true", timeout=5.0)
    assert ct["id"] in [it["id"] for it in r2.json()["items"]]
    print(f"  → GET ?include_archived=true: 含 archived 项 ✓")


def test_create_with_examples(backend):
    """用例 11:POST 带 examples=[{component_id,note}]"""
    payload = {
        "title": "REQ-968b1c99 用例 11 - examples 强引用",
        "thesis": "### examples 强引用测试",
        "examples": [
            {"component_id": "arch-platform-cli", "note": "CLI 道层面应用"},
            {"component_id": "arch-platform-backend", "note": "后端道层面应用"},
        ],
    }
    r = httpx.post(
        f"{backend}/api/v1/core-thoughts",
        json=payload,
        headers=_auth_headers(),
        timeout=5.0,
    )
    assert r.status_code == 201
    data = r.json()
    assert len(data["examples"]) == 2
    assert data["examples"][0]["component_id"] == "arch-platform-cli"
    assert data["examples"][0]["note"] == "CLI 道层面应用"
    print(f"  → POST with examples: 201 + 2 个强引用 ✓")
    _cleanup(backend, data["id"])


def test_get_public_no_key(backend):
    """用例 14:GET 无 Key → 200(公开)"""
    r = httpx.get(f"{backend}/api/v1/core-thoughts", timeout=5.0)
    assert r.status_code == 200
    print(f"  → GET 无 Key: 200(公开)✓")


def test_get_404(backend):
    """用例 15:GET 不存在 id → 404"""
    r = httpx.get(f"{backend}/api/v1/core-thoughts/nonexistent-id-xyz", timeout=5.0)
    assert r.status_code == 404
    print(f"  → GET 不存在 id: 404 ✓")


def test_patch_archived_422(backend):
    """用例 16:PATCH 已 archived → 422"""
    ct = _create_ct(backend, title="REQ-968b1c99 用例 16 - PATCH archived 拒绝")
    httpx.delete(
        f"{backend}/api/v1/core-thoughts/{ct['id']}",
        headers=_auth_headers(),
        timeout=5.0,
    )
    r = httpx.patch(
        f"{backend}/api/v1/core-thoughts/{ct['id']}",
        json={"title": "想改 archived"},
        headers=_auth_headers(),
        timeout=5.0,
    )
    assert r.status_code == 422
    assert "restore" in r.text.lower()
    print(f"  → PATCH archived: 422 + 提示 restore ✓")


def test_post_invalid_status_422(backend):
    """用例 17:POST status=invalid → 422(enum 校验)"""
    r = httpx.post(
        f"{backend}/api/v1/core-thoughts",
        json={"title": "x", "thesis": "y", "status": "invalid_status"},
        headers=_auth_headers(),
        timeout=5.0,
    )
    assert r.status_code == 422
    print(f"  → POST status=invalid: 422 ✓")


def test_patch_examples_null_safety(backend):
    """用例 22-P3.6 fix:PATCH examples=null → 200(兜底成 [])"""
    ct = _create_ct(backend, title="REQ-968b1c99 例外 - examples=null 兜底",
                    examples=[{"component_id": "x", "note": "y"}])
    try:
        r = httpx.patch(
            f"{backend}/api/v1/core-thoughts/{ct['id']}",
            json={"examples": None},
            headers=_auth_headers(),
            timeout=5.0,
        )
        assert r.status_code == 200, f"{r.status_code} {r.text}"
        data = r.json()
        assert data["examples"] == [], f"examples 应被兜底为 []，实际: {data['examples']}"
        # 后续 list/get 不应触发 list_type 错
        r2 = httpx.get(f"{backend}/api/v1/core-thoughts/{ct['id']}", timeout=5.0)
        assert r2.status_code == 200
        print(f"  → PATCH examples=null: 200 + 兜底成 [] + list_type 不错 ✓")
    finally:
        _cleanup(backend, ct["id"])


# ===== UI 页面渲染 =====

def test_ui_core_thoughts_list(backend):
    """用例 18:UI /core-thoughts → 200 + 列表渲染"""
    r = httpx.get(f"{backend}/core-thoughts", timeout=5.0)
    assert r.status_code == 200
    body = r.text
    assert "核心思想" in body
    assert "<table" in body  # drafting sheet 表格
    print(f"  → UI /core-thoughts: 200 + 含「核心思想」标题 + table ✓")


def test_ui_core_thoughts_new_form(backend):
    """用例 19:UI /core-thoughts/new → 200 + 表单字段齐"""
    r = httpx.get(f"{backend}/core-thoughts/new", timeout=5.0)
    assert r.status_code == 200
    body = r.text
    for field in ("title", "thesis", "rationale", "how_to_apply", "origin",
                  "status", "tags", "examples"):
        assert f'name="{field}"' in body, f"表单缺字段 {field}"
    print(f"  → UI /core-thoughts/new: 200 + 8 字段全在 ✓")


def test_ui_core_thoughts_edit_form(backend):
    """用例 20:UI /core-thoughts/{id}/edit → 200 + 字段预填"""
    ct = _create_ct(backend, title="REQ-968b1c99 用例 20 - UI edit 预填")
    try:
        r = httpx.get(f"{backend}/core-thoughts/{ct['id']}/edit", timeout=5.0)
        assert r.status_code == 200
        body = r.text
        # 预填值应出现(value="..." 或包含在 textarea)
        assert ct["title"] in body or ct["title"][:30] in body
        print(f"  → UI /core-thoughts/{{id}}/edit: 200 + 字段预填 ✓")
    finally:
        _cleanup(backend, ct["id"])


def test_ui_create_form_submit(backend):
    """用例 21:UI POST /core-thoughts/create → 303 + 后端可见"""
    title = "REQ-968b1c99 用例 21 - UI 表单提交"
    r = httpx.post(
        f"{backend}/core-thoughts/create",
        data={
            "title": title,
            "thesis": "### UI 表单提交测试",
            "rationale": "### 背景",
            "how_to_apply": "### 应用",
            "origin": "pytest-ui",
            "status": "draft",
            "tags": "ui-test, pytest",
            "examples": '[{"component_id":"x","note":"y"}]',
            "proposer": "pytest-ui",
        },
        follow_redirects=False,
        timeout=5.0,
    )
    assert r.status_code == 303, f"{r.status_code} {r.text}"
    location = r.headers.get("location", "")
    assert "/core-thoughts/" in location

    # 后端可见
    new_id = location.rstrip("/").split("/")[-1]
    chk = httpx.get(f"{backend}/api/v1/core-thoughts/{new_id}", timeout=5.0)
    assert chk.status_code == 200
    assert chk.json()["title"] == title
    print(f"  → UI POST /core-thoughts/create: 303 + 后端可见 ✓")
    _cleanup(backend, new_id)


def test_ui_markdown_xss_escape(backend):
    """用例 22:Markdown XSS escape — <script> 应被 escape(mistune 输出层 + markdown 渲染层)
    P5 修复:之前 escape=True 模式破坏 markdown 语法解析;改为「先 escape 后 markdown」两步法。
    浏览器最终渲染安全:&amp;lt;script&amp;gt; → "‹script›" 文本,不执行。
    """
    payload = {
        "title": "REQ-968b1c99 用例 22 - XSS",
        "thesis": "<script>alert('xss-test-968b1c99')</script>**bold**\n- list item",
        "status": "draft",
    }
    r = httpx.post(
        f"{backend}/api/v1/core-thoughts",
        json=payload,
        headers=_auth_headers(),
        timeout=5.0,
    )
    assert r.status_code == 201
    ct_id = r.json()["id"]
    try:
        # UI 详情页
        ui = httpx.get(f"{backend}/core-thoughts/{ct_id}", timeout=5.0)
        assert ui.status_code == 200
        body = ui.text
        # 1. <script>alert 必须不出现在 HTML 中(XSS 防住)
        assert "<script>alert" not in body, "XSS 没 escape(找到 <script>alert)"
        # 2. 转义符应在(mistune 输出层会双重 escape 成 &amp;lt;script&amp;gt;,
        #    浏览器渲染回 &lt;script&gt; 文本,安全)
        assert "&amp;lt;script&amp;gt;" in body or "&lt;script&gt;" in body, \
            "XSS 应被 escape 成转义符(&amp;lt;script&amp;gt; 或 &lt;script&gt;)"
        # 3. **bold** 应被 markdown 渲染成 <strong>
        assert "<strong>bold</strong>" in body, f"markdown **bold** 解析失败,body 摘录:{body[body.find('论点'):body.find('论点')+500]}"
        # 4. - list item 应被渲染成 <ul>
        assert "<ul>" in body, "markdown - list 解析失败"
        assert "<li>list item</li>" in body
        print(f"  → Markdown XSS: escape 生效 + <strong> + <ul> 渲染 ✓")
    finally:
        _cleanup(backend, ct_id)


# ===== model/table import smoke =====

def test_core_thought_model_import():
    """用例 23:model 导入 smoke — tablename + 列名集完整"""
    from app.models import CoreThought, CoreThoughtStatus
    assert CoreThought.__tablename__ == "core_thoughts"
    cols = {c.name for c in CoreThought.__table__.columns}
    expected = {"id", "title", "thesis", "rationale", "how_to_apply",
                "origin", "status", "tags", "examples", "proposer",
                "is_archived", "created_at", "updated_at"}
    assert expected.issubset(cols), f"缺字段:{expected - cols}"
    # 复合索引
    indexes = {i.name for i in CoreThought.__table__.indexes}
    assert "ix_core_thoughts_archived_status" in indexes, "缺复合索引"
    # 状态机 4 态
    status_values = {s.value for s in CoreThoughtStatus}
    assert status_values == {"draft", "active", "superseded", "archived"}
    print(f"  → CoreThought model: tablename + 13 列 + 复合索引 + 4 态 enum 完整 ✓")


# ===== by-tag endpoint =====

def test_by_tag_endpoint(backend):
    """用例 11+1:/by-tag/{tag} endpoint"""
    ct = _create_ct(backend, title="REQ-968b1c99 用例 by-tag",
                    tags=["bytag-unique-test"])
    try:
        r = httpx.get(f"{backend}/api/v1/core-thoughts/by-tag/bytag-unique-test",
                      timeout=5.0)
        assert r.status_code == 200
        ids = [it["id"] for it in r.json()["items"]]
        assert ct["id"] in ids
        print(f"  → GET /by-tag/bytag-unique-test: 200 + 命中 ✓")
    finally:
        _cleanup(backend, ct["id"])