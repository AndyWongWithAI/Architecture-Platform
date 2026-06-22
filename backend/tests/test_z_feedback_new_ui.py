"""REQ-5ebc9e3b Phase 3:反馈看板「新建 Open Bug」UI 测试

5 个测试:
1. kanban.html 含「新建 Open Bug」表单 + 必填字段
2. 组件下拉框被填充
3. POST /feedbacks/create 端到端:代理成功 → 303 重定向到 /feedbacks/{id}
4. bug_summary < 5 字符 → 422(后端 Pydantic 校验)
5. 不存在的 component_id → 404 错误
"""
import time
import threading

import httpx
import pytest
import uvicorn


# ——— 启动后端(与 test_ui.py 共享 fixture 模式)———

@pytest.fixture(scope="module")
def backend():
    import os
    os.environ.setdefault("ARCH_API_BASE", "http://127.0.0.1:8088")
    from app.main import app

    config = uvicorn.Config(app, host="127.0.0.1", port=8088, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    for _ in range(50):
        try:
            httpx.get("http://127.0.0.1:8088/healthz", timeout=1.0)
            break
        except Exception:
            time.sleep(0.1)

    yield "http://127.0.0.1:8088"
    server.should_exit = True
    thread.join(timeout=2)


@pytest.fixture(scope="module")
def test_component_with_version(backend):
    """创建测试组件 + version,scope=module 让所有 create 测试共享。"""
    # 创建组件
    create = httpx.post(
        f"{backend}/api/v1/components",
        json={
            "name": "ui-newbug-test-cache",
            "title": "UI NewBug Test Cache",
            "positioning": "REQ-5ebc9e3b UI 测试用的临时组件,测试后清理",
            "category": "cache",
            "scope": "infra",
            "layer": "L1_platform",
            "is_asset": True,
            "distribution_form": "package",
        },
        timeout=5.0,
    )
    assert create.status_code == 201, f"创建组件失败:{create.text}"
    comp_id = create.json()["id"]

    # 创建 version
    ver = httpx.post(
        f"{backend}/api/v1/components/ui-newbug-test-cache/versions",
        json={
            "version": "1.0.0",
            "semver_intent": "major",
            "changelog": "UI newbug 测试",
            "breaking_changes": "无",
        },
        timeout=5.0,
    )
    assert ver.status_code == 201, f"创建 version 失败:{ver.text}"
    ver_id = ver.json()["id"]

    yield {"component_id": comp_id, "version_id": ver_id, "name": "ui-newbug-test-cache"}

    # 清理(直接通过 API 删,失败也无妨 — 手工 sqlite3 兜底)
    try:
        httpx.delete(f"{backend}/api/v1/versions/{ver_id}", timeout=3.0)
    except Exception:
        pass


# ——— 1. UI 表单渲染测试 ———

def test_kanban_has_new_feedback_form(backend):
    """GET /feedbacks 应包含「新建 Open Bug」表单(REQ-5ebc9e3b acceptance #1)"""
    r = httpx.get(f"{backend}/feedbacks", timeout=5.0)
    assert r.status_code == 200
    text = r.text

    # 表单
    assert 'id="newFeedbackForm"' in text
    assert 'action="/feedbacks/create"' in text

    # 必填字段
    assert 'name="bug_summary"' in text
    assert 'name="severity"' in text
    assert 'name="component_id"' in text
    assert 'name="reporter"' in text
    assert 'name="reused_in_projects"' in text

    # 严重度下拉所有选项
    for sev in ["low", "medium", "high", "critical"]:
        assert f'value="{sev}"' in text, f"严重度 {sev} 缺失"

    # bug_summary 必填 + minlength 5(对应后端 schema)
    assert 'minlength="5"' in text

    # 提交按钮文案
    assert "提交 Open Bug" in text

    print("  → kanban.html 渲染「新建 Open Bug」表单 ✓")


def test_kanban_components_dropdown_populated(backend, test_component_with_version):
    """表单下拉应包含至少一个组件(seed 数据 + 测试组件)"""
    r = httpx.get(f"{backend}/feedbacks", timeout=5.0)
    assert r.status_code == 200
    text = r.text
    select_start = text.find('name="component_id"')
    select_end = text.find("</select>", select_start)
    select_block = text[select_start:select_end]
    assert "<option" in select_block
    assert 'value="' in select_block
    # 测试组件应在下拉中
    assert "ui-newbug-test-cache" in select_block
    print(f"  → component 下拉框有 {select_block.count('<option')} 个选项(包含测试组件)✓")


# ——— 2. POST 端到端测试 ———

def test_feedback_create_from_ui_redirects(backend, test_component_with_version):
    """UI POST /feedbacks/create → 303 redirect → 后端已创建 → 详情页可访问(REQ-5ebc9e3b acceptance #2)"""
    comp = test_component_with_version
    r = httpx.post(
        f"{backend}/feedbacks/create",
        data={
            "component_id": comp["component_id"],
            "bug_summary": "REQ-5ebc9e3b UI 测试创建 bug-不应保留-test-only-link",
            "severity": "medium",
            "reporter": "ui-test",
            "reused_in_projects": "arch-platform, intelab.cn-website",
        },
        timeout=5.0,
        follow_redirects=False,
    )
    assert r.status_code == 303, f"期望 303 redirect, got {r.status_code}: {r.text[:200]}"
    location = r.headers.get("location", "")
    assert "/feedbacks/" in location, f"redirect 应含 /feedbacks/:{location}"

    # 验证后端已创建
    fb_id = location.rsplit("/", 1)[-1]
    chk = httpx.get(f"{backend}/api/v1/feedbacks/{fb_id}", timeout=5.0)
    assert chk.status_code == 200
    data = chk.json()
    assert data["bug_summary"].startswith("REQ-5ebc9e3b UI 测试")
    assert data["severity"] == "medium"
    assert data["reporter"] == "ui-test"
    assert "arch-platform" in data["reused_in_projects"]
    assert "intelab.cn-website" in data["reused_in_projects"]
    assert data["status"] == "open"  # 新建默认 open

    # 详情页可访问
    detail = httpx.get(f"{backend}/feedbacks/{fb_id}", timeout=5.0)
    assert detail.status_code == 200
    assert "REQ-5ebc9e3b" in detail.text

    print(f"  → UI feedback create proxy: {fb_id[:8]} redirect + detail 渲染 + reused_in_projects ✓")


# ——— 3. 验证测试 ———

def test_feedback_create_rejects_too_short_summary(backend, test_component_with_version):
    """bug_summary < 5 字符 → 422(后端 Pydantic 校验)"""
    comp = test_component_with_version
    r = httpx.post(
        f"{backend}/api/v1/versions/{comp['version_id']}/feedbacks",
        json={
            "reporter": "ui-test",
            "bug_summary": "abc",  # 4 字符,违反 min_length=5
            "severity": "medium",
        },
        timeout=5.0,
    )
    assert r.status_code == 422
    assert "min_length" in r.text or "at least 5" in r.text or "bug_summary" in r.text
    print("  → bug_summary < 5 字符后端 422 拒绝 ✓")


def test_feedback_create_handles_invalid_component(backend):
    """不存在的 component_id → 404(JSONResponse)"""
    r = httpx.post(
        f"{backend}/feedbacks/create",
        data={
            "component_id": "nonexistent-component-xyz-123",
            "bug_summary": "测试不存在的组件",
            "severity": "low",
        },
        timeout=5.0,
    )
    assert r.status_code == 404
    assert "不存在" in r.json().get("error", "")
    print("  → 不存在的 component_id → 404 错误响应 ✓")
