"""REQ-7c4bcb32 Literature 资产 CRUD + UI 端到端测试

测试目标:
- API CRUD(GET list/detail / POST create / PATCH update / DELETE archive / restore)
- 过滤 + 搜索(q + tag)
- API Key 校验
- UI 页面渲染(/literature list/new/detail/edit)
- UI 表单提交代理(create + edit)
- 软删除一致性(对齐 Requirement.is_archived)
"""
import os
import sys
import importlib
import threading
import time

# 必须在 import app 之前设环境变量 — proxy.py 在 import 时读 ARCH_API_BASE
os.environ.pop("ARCH_API_BASE", None)
os.environ["ARCH_API_BASE"] = "http://127.0.0.1:8091"

import httpx
import pytest


@pytest.fixture(scope="module", autouse=True)
def _reload_proxy_to_pick_env():
    """强制 reload proxy/ui.routes,确保 ARCH_API_BASE=8091 生效"""
    for mod in ("app.ui.proxy", "app.ui.routes"):
        if mod in sys.modules:
            importlib.reload(sys.modules[mod])
    yield


# ——— 后端 fixture(避开 test_ui.py 8088 / test_z_requirement_edit.py 8089 / test_z_requirements 8090)—

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


def _create_lit(backend, **overrides) -> dict:
    """创建一个测试文献,返回完整 dict"""
    payload = {
        "title": "REQ-7c4bcb32 测试文献 - 不应保留 test-only",
        "url": "https://example.com/paper",
        "authors": "Author A, Author B",
        "tags": ["test", "distributed"],
        "summary": "测试文献摘要",
        "source": "manually added",
        "added_by": "pytest",
    }
    payload.update(overrides)
    r = httpx.post(
        f"{backend}/api/v1/literatures",
        json=payload,
        headers=_auth_headers(),
        timeout=5.0,
    )
    assert r.status_code == 201, f"create failed: {r.status_code} {r.text}"
    return r.json()


def _cleanup(backend, lit_id: str):
    """清理:archive(避免影响 list 默认视图)"""
    httpx.delete(
        f"{backend}/api/v1/literatures/{lit_id}",
        headers=_auth_headers(),
        timeout=5.0,
    )


# ===== API CRUD happy path =====

def test_create_literature(backend):
    """POST /api/v1/literatures → 201 + 返回完整对象"""
    payload = {
        "title": "REQ-7c4bcb32 创建测试 - 不应保留 test-only",
        "url": "https://example.com/test",
        "authors": "Test Author",
        "tags": ["test", "create"],
        "summary": "test summary",
        "source": "manually added",
    }
    r = httpx.post(
        f"{backend}/api/v1/literatures",
        json=payload,
        headers=_auth_headers(),
        timeout=5.0,
    )
    assert r.status_code == 201, f"{r.status_code} {r.text}"
    data = r.json()
    assert data["title"] == payload["title"]
    assert data["url"] == payload["url"]
    assert sorted(data["tags"]) == ["create", "test"]
    assert data["is_archived"] is False
    assert data["added_by"] == "api"  # 缺省值
    assert "id" in data
    assert "added_at" in data
    print(f"  → POST create: 201 + {data['id'][:8]} + added_by=api 缺省 ✓")
    _cleanup(backend, data["id"])


def test_list_literatures(backend):
    """GET /api/v1/literatures → 列表含已创建项"""
    lit = _create_lit(backend, title="REQ-7c4bcb32 列表测试 - 不应保留 test-only")
    try:
        r = httpx.get(f"{backend}/api/v1/literatures", timeout=5.0)
        assert r.status_code == 200
        body = r.json()
        assert "items" in body and "total" in body
        ids = [it["id"] for it in body["items"]]
        assert lit["id"] in ids, f"刚创建的文献应出现在列表中:{ids[:5]}"
        print(f"  → GET list: 200 + total={body['total']} + 新建已可见 ✓")
    finally:
        _cleanup(backend, lit["id"])


def test_get_literature_detail(backend):
    """GET /api/v1/literatures/{id} → 200 + 完整字段"""
    lit = _create_lit(backend, title="REQ-7c4bcb32 详情测试 - 不应保留 test-only")
    try:
        r = httpx.get(f"{backend}/api/v1/literatures/{lit['id']}", timeout=5.0)
        assert r.status_code == 200
        data = r.json()
        assert data["id"] == lit["id"]
        assert data["title"] == lit["title"]
        assert data["url"] == lit["url"]
        assert data["tags"] == lit["tags"]
        print(f"  → GET detail: 200 + 字段完整 ✓")
    finally:
        _cleanup(backend, lit["id"])


def test_update_literature(backend):
    """PATCH /api/v1/literatures/{id} → 200 + 字段已更新"""
    lit = _create_lit(backend, title="REQ-7c4bcb32 更新测试 - 不应保留 test-only")
    try:
        r = httpx.patch(
            f"{backend}/api/v1/literatures/{lit['id']}",
            json={"title": "REQ-7c4bcb32 已更新 - 不应保留 test-only",
                  "tags": ["updated", "new-tag"]},
            headers=_auth_headers(),
            timeout=5.0,
        )
        assert r.status_code == 200, f"{r.status_code} {r.text}"
        data = r.json()
        assert "已更新" in data["title"]
        assert sorted(data["tags"]) == ["new-tag", "updated"]
        # url 不在 payload 中应保留
        assert data["url"] == lit["url"]
        print(f"  → PATCH update: 200 + title/tags 已更新 + url 保留 ✓")
    finally:
        _cleanup(backend, lit["id"])


def test_archive_and_restore_literature(backend):
    """DELETE → archive;POST /restore → 恢复"""
    lit = _create_lit(backend, title="REQ-7c4bcb32 软删测试 - 不应保留 test-only")
    lit_id = lit["id"]

    # archive
    r = httpx.delete(
        f"{backend}/api/v1/literatures/{lit_id}",
        headers=_auth_headers(),
        timeout=5.0,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == lit_id
    assert body["is_archived"] is True

    # 列表默认不含 archived
    r = httpx.get(f"{backend}/api/v1/literatures", timeout=5.0)
    assert lit_id not in [it["id"] for it in r.json()["items"]]

    # include_archived=True 含
    r = httpx.get(f"{backend}/api/v1/literatures?include_archived=true", timeout=5.0)
    assert lit_id in [it["id"] for it in r.json()["items"]]

    # restore
    r = httpx.post(
        f"{backend}/api/v1/literatures/{lit_id}/restore",
        headers=_auth_headers(),
        timeout=5.0,
    )
    assert r.status_code == 200
    assert r.json()["is_archived"] is False

    # 列表又可见
    r = httpx.get(f"{backend}/api/v1/literatures", timeout=5.0)
    assert lit_id in [it["id"] for it in r.json()["items"]]
    print(f"  → DELETE archive + POST restore: 状态机翻转正确 ✓")
    _cleanup(backend, lit_id)


def test_update_archived_blocked(backend):
    """PATCH archived 文献 → 422"""
    lit = _create_lit(backend, title="REQ-7c4bcb32 archive-更新测试 - 不应保留 test-only")
    httpx.delete(
        f"{backend}/api/v1/literatures/{lit['id']}",
        headers=_auth_headers(),
        timeout=5.0,
    )
    try:
        r = httpx.patch(
            f"{backend}/api/v1/literatures/{lit['id']}",
            json={"title": "试图改 archive - 不应保留"},
            headers=_auth_headers(),
            timeout=5.0,
        )
        assert r.status_code == 422, f"archive 后改应被拒,got {r.status_code}"
        assert "archived" in r.text.lower()
        print(f"  → PATCH archived lit: 422 ✓")
    finally:
        # restore → 再 cleanup
        httpx.post(
            f"{backend}/api/v1/literatures/{lit['id']}/restore",
            headers=_auth_headers(),
            timeout=5.0,
        )
        _cleanup(backend, lit["id"])


# ===== 过滤 + 搜索 =====

def test_search_by_q(backend):
    """GET /api/v1/literatures?q=xxx → title/authors/summary 命中"""
    marker = "REQ-7c4bcb32 search-marker-不应保留"
    lit = _create_lit(backend, title=marker, summary="其他无关内容")
    try:
        r = httpx.get(
            f"{backend}/api/v1/literatures",
            params={"q": "search-marker"},
            timeout=5.0,
        )
        assert r.status_code == 200
        ids = [it["id"] for it in r.json()["items"]]
        assert lit["id"] in ids, f"按 q 搜索应命中:ids={ids[:3]}"
        print(f"  → GET ?q= 搜索: 命中 marker 文献 ✓")
    finally:
        _cleanup(backend, lit["id"])


def test_filter_by_tag(backend):
    """GET /api/v1/literatures?tag=xxx → tag 命中"""
    lit = _create_lit(
        backend,
        title="REQ-7c4bcb32 tag-filter - 不应保留 test-only",
        tags=["unique-tag-xyz", "test"],
    )
    try:
        r = httpx.get(
            f"{backend}/api/v1/literatures",
            params={"tag": "unique-tag-xyz"},
            timeout=5.0,
        )
        assert r.status_code == 200
        ids = [it["id"] for it in r.json()["items"]]
        assert lit["id"] in ids
        print(f"  → GET ?tag= 过滤: 命中 unique-tag ✓")
    finally:
        _cleanup(backend, lit["id"])


# ===== API Key 校验 =====

def test_create_requires_auth_when_key_set(backend, monkeypatch):
    """API Key 启用时,无 Key POST → 401"""
    if not os.environ.get("ARCH_PLATFORM_API_KEY"):
        pytest.skip("ARCH_PLATFORM_API_KEY 未设置,跳过鉴权测试")

    # 不带 Key
    r = httpx.post(
        f"{backend}/api/v1/literatures",
        json={"title": "无 Key 测试", "url": "https://x.com"},
        timeout=5.0,
    )
    assert r.status_code == 401, f"无 Key 应被 401,got {r.status_code}"
    print(f"  → POST 无 X-API-Key: 401 ✓")


def test_create_rejects_bad_key(backend):
    """错误 Key POST → 401"""
    if not os.environ.get("ARCH_PLATFORM_API_KEY"):
        pytest.skip("ARCH_PLATFORM_API_KEY 未设置,跳过鉴权测试")

    r = httpx.post(
        f"{backend}/api/v1/literatures",
        json={"title": "错误 Key", "url": "https://x.com"},
        headers={"X-API-Key": "wrong-key-xyz"},
        timeout=5.0,
    )
    assert r.status_code == 401
    print(f"  → POST 错误 X-API-Key: 401 ✓")


def test_get_no_auth_required(backend):
    """GET 公开(不需要 API Key)"""
    # 直接 GET 任意文献(可能空,只要 200/200-with-empty 不要求 401)
    r = httpx.get(f"{backend}/api/v1/literatures", timeout=5.0)
    assert r.status_code == 200
    print(f"  → GET 无 Key: 200(公开读)✓")


def test_404_for_missing(backend):
    """GET/PATCH 不存在 id → 404"""
    fake = "00000000-0000-0000-0000-000000000000"
    assert httpx.get(f"{backend}/api/v1/literatures/{fake}", timeout=5.0).status_code == 404
    assert httpx.patch(
        f"{backend}/api/v1/literatures/{fake}",
        json={"title": "x"},
        headers=_auth_headers(),
        timeout=5.0,
    ).status_code == 404
    print(f"  → 404 for missing id ✓")


# ===== UI 页面渲染 =====

def test_literature_list_page(backend):
    """GET /literature → 200 + 表单(表格或空态文案)"""
    r = httpx.get(f"{backend}/literature", timeout=5.0)
    assert r.status_code == 200
    assert "文献" in r.text
    # 至少有「登记」入口(页面渲染正确)
    assert "/literature/new" in r.text
    # 空态显示「暂无文献」,有数据时显示 <table>
    assert "暂无文献" in r.text or "<table" in r.text
    print(f"  → GET /literature: 200 + 入口/空态/表格 至少一项 ✓")


def test_literature_new_page(backend):
    """GET /literature/new → 200 + form 字段"""
    r = httpx.get(f"{backend}/literature/new", timeout=5.0)
    assert r.status_code == 200
    for field in ("name=\"title\"", "name=\"url\"", "name=\"authors\"",
                  "name=\"summary\"", "name=\"tags\""):
        assert field in r.text, f"new 表单缺字段 {field}"
    print(f"  → GET /literature/new: 200 + 全字段 ✓")


def test_literature_detail_page(backend):
    """GET /literature/{id} → 200 + 详情"""
    lit = _create_lit(backend, title="REQ-7c4bcb32 UI 详情测试 - 不应保留 test-only")
    try:
        r = httpx.get(f"{backend}/literature/{lit['id']}", timeout=5.0)
        assert r.status_code == 200
        assert lit["title"] in r.text
        # 外链 target=_blank
        assert 'target="_blank"' in r.text
        # tag badge
        assert "test" in r.text
        print(f"  → GET /literature/{{id}}: 200 + 外链 + tag ✓")
    finally:
        _cleanup(backend, lit["id"])


def test_literature_detail_404(backend):
    """GET /literature/{不存在的id} → 404"""
    r = httpx.get(
        f"{backend}/literature/00000000-0000-0000-0000-000000000000",
        timeout=5.0,
    )
    assert r.status_code == 404
    print(f"  → GET /literature/{{missing}}: 404 ✓")


def test_literature_edit_page(backend):
    """GET /literature/{id}/edit → 200 + 表单预填"""
    lit = _create_lit(
        backend,
        title="REQ-7c4bcb32 UI 编辑测试 - 不应保留 test-only",
        tags=["edit-test", "ui"],
    )
    try:
        r = httpx.get(f"{backend}/literature/{lit['id']}/edit", timeout=5.0)
        assert r.status_code == 200
        # 预填值
        assert "UI 编辑测试" in r.text
        assert "edit-test, ui" in r.text  # tags CSV 预填
        print(f"  → GET /literature/{{id}}/edit: 200 + 预填 ✓")
    finally:
        _cleanup(backend, lit["id"])


# ===== UI 表单提交代理 =====

def test_literature_create_proxy(backend):
    """POST /literature/create → 303 + 后端已建"""
    r = httpx.post(
        f"{backend}/literature/create",
        data={
            "title": "REQ-7c4bcb32 UI 创建测试 - 不应保留 test-only",
            "url": "https://example.com/ui-test",
            "authors": "UI Author",
            "tags": "ui, create, test",
            "summary": "UI 表单测试",
        },
        follow_redirects=False,
        timeout=5.0,
    )
    assert r.status_code == 303, f"期望 303,got {r.status_code}:{r.text[:200]}"
    location = r.headers.get("location", "")
    assert "/literature/" in location
    lit_id = location.rsplit("/", 1)[-1]

    # 验证后端
    chk = httpx.get(f"{backend}/api/v1/literatures/{lit_id}", timeout=5.0)
    assert chk.status_code == 200
    data = chk.json()
    assert data["title"].startswith("REQ-7c4bcb32")
    assert sorted(data["tags"]) == ["create", "test", "ui"]
    assert data["added_by"] == "web-ui"  # UI 提交自动加标记
    print(f"  → POST /literature/create: 303 + tags/added_by 正确 ✓")
    _cleanup(backend, lit_id)


def test_literature_edit_proxy(backend):
    """POST /literature/{id}/edit → 303 + 后端已更新"""
    lit = _create_lit(
        backend,
        title="REQ-7c4bcb32 UI 编辑提交测试 - 不应保留 test-only",
        tags=["before"],
    )
    try:
        r = httpx.post(
            f"{backend}/literature/{lit['id']}/edit",
            data={
                "title": "REQ-7c4bcb32 UI 编辑已改 - 不应保留 test-only",
                "tags": "after, edit",
            },
            follow_redirects=False,
            timeout=5.0,
        )
        assert r.status_code == 303
        location = r.headers.get("location", "")
        assert location.endswith(f"/literature/{lit['id']}")

        chk = httpx.get(f"{backend}/api/v1/literatures/{lit['id']}", timeout=5.0)
        data = chk.json()
        assert "已改" in data["title"]
        assert sorted(data["tags"]) == ["after", "edit"]
        # url 保留(没在 payload 中)
        assert data["url"] == lit["url"]
        print(f"  → POST /literature/{{id}}/edit: 303 + title/tags 更新 + url 保留 ✓")
    finally:
        _cleanup(backend, lit["id"])


# ===== model/table import smoke =====

def test_literature_model_import():
    """模型可被导入(供外部脚本/CLI 用)"""
    from app.models import Literature
    assert Literature.__tablename__ == "literatures"
    cols = {c.name for c in Literature.__table__.columns}
    for required in ("id", "title", "url", "tags", "added_at", "is_archived"):
        assert required in cols, f"missing column {required}"
    print(f"  → Literature model: tablename + columns 完整 ✓")
