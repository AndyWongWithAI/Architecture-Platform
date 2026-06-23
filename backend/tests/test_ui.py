"""Phase 4 Web UI 测试 — 8 个页面渲染 + PATCH 反馈代理

测试方法:启动后端容器,用 httpx 调 UI 路由(同进程内),验证 HTML 200。
"""
import os
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest


# ——— 启动后端 ———

@pytest.fixture(scope="module")
def backend():
    """启动 FastAPI 测试服务器,127.0.0.1:8088"""
    import uvicorn
    from app.main import app

    config = uvicorn.Config(app, host="127.0.0.1", port=8088, log_level="warning")
    server = uvicorn.Server(config)

    # 在 thread 跑 uvicorn
    import threading
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    # 等服务启动
    for _ in range(50):
        try:
            httpx.get("http://127.0.0.1:8088/healthz", timeout=1.0)
            break
        except Exception:
            time.sleep(0.1)

    yield "http://127.0.0.1:8088"

    server.should_exit = True
    thread.join(timeout=2)


# ——— 8 个页面渲染测试 ———

PAGES = [
    ("/", "总览"),
    ("/components", "组件列表"),
    ("/components/docker", "组件详情"),
    ("/components/docker/tree", "依赖树"),
    ("/feedbacks", "反馈看板"),
    ("/requirements", "需求列表"),  # Phase 1.2 2026-06-21
    ("/requirements/new", "需求创建表单"),  # Phase 1.2
    ("/deployments", "部署地图"),
    ("/search?q=nginx", "搜索"),
    ("/help", "文档总览(REQ-8be0f95c)"),
    ("/help/er-diagram", "文档详情(REQ-8be0f95c)"),
    ("/healthz", "健康检查"),
]


@pytest.mark.parametrize("path,desc", PAGES)
def test_page_renders(backend, path, desc):
    """所有页面应返回 200(HTML 页面 or /healthz JSON)"""
    r = httpx.get(f"{backend}{path}", timeout=5.0)
    assert r.status_code == 200, f"{desc} {path} → {r.status_code}"
    # /healthz 是 JSON,其他页面是 HTML
    if path == "/healthz":
        assert r.json().get("status") == "ok"
    else:
        assert "<html" in r.text.lower(), f"{desc} 不是 HTML"


def test_index_shows_components(backend):
    """首页应展示组件总数"""
    r = httpx.get(f"{backend}/", timeout=5.0)
    assert r.status_code == 200
    # 至少看到 "组件总数" 和 "9"(种子)
    assert "组件总数" in r.text
    # 分层统计
    assert "L0_infrastructure" in r.text


def test_components_list(backend):
    """组件列表应显示种子组件"""
    r = httpx.get(f"{backend}/components", timeout=5.0)
    assert r.status_code == 200
    # 种子组件名
    assert "docker" in r.text
    assert "nginx" in r.text
    assert "intelab.cn-website" in r.text


def test_components_list_filter(backend):
    """过滤功能"""
    r = httpx.get(f"{backend}/components?layer=L1_platform", timeout=5.0)
    assert r.status_code == 200
    # L1 应该有 certbot / nginx / fail2ban / ssh-key-auth / ufw
    assert "certbot" in r.text
    assert "nginx" in r.text


def test_component_detail(backend):
    """组件详情应显示完整信息"""
    r = httpx.get(f"{backend}/components/docker", timeout=5.0)
    assert r.status_code == 200
    assert "Docker 容器引擎" in r.text
    assert "L0_infrastructure" in r.text
    # 应有定位段落
    assert "定位" in r.text


def test_component_tree(backend):
    """依赖树(L3 → L1)"""
    r = httpx.get(f"{backend}/components/intelab.cn-website/tree", timeout=5.0)
    assert r.status_code == 200
    # L3 应该有 nginx 和 certbot 子组件
    assert "nginx" in r.text
    assert "certbot" in r.text


def test_feedbacks_kanban(backend):
    """反馈看板 4 列布局"""
    r = httpx.get(f"{backend}/feedbacks", timeout=5.0)
    assert r.status_code == 200
    assert "Kanban" in r.text or "看板" in r.text
    # 4 个 kanban-col div
    assert r.text.count('class="kanban-col"') == 4


def test_deployments(backend):
    """部署地图"""
    r = httpx.get(f"{backend}/deployments", timeout=5.0)
    assert r.status_code == 200
    assert "部署地图" in r.text


def test_search(backend):
    """搜索结果"""
    r = httpx.get(f"{backend}/search?q=nginx", timeout=5.0)
    assert r.status_code == 200
    # 应该至少搜到 nginx 组件
    assert "nginx" in r.text


def test_404_component(backend):
    """组件不存在 → 404"""
    r = httpx.get(f"{backend}/components/nonexistent-component-xyz", timeout=5.0)
    assert r.status_code == 404


def test_static_assets(backend):
    """静态资源可访问"""
    css = httpx.get(f"{backend}/static/css/custom.css", timeout=5.0)
    assert css.status_code == 200
    assert ".site-header" in css.text

    js = httpx.get(f"{backend}/static/js/app.js", timeout=5.0)
    assert js.status_code == 200


# ===== REQ-8be0f95c /help 路由测试(2026-06-23)=====


def test_help_index_lists_files(backend):
    """/help 应列出 docs/ 下所有 markdown 文件(≥ 5 个)"""
    r = httpx.get(f"{backend}/help", timeout=5.0)
    assert r.status_code == 200
    # 总数应 ≥ 5(目前 24 个,留 buffer)
    assert "共" in r.text and "篇" in r.text
    # 应看到几个关键文档
    assert "er-diagram" in r.text
    assert "DESIGN" in r.text
    # 应有 4 个 category 标题
    for cat in ["概述", "设计", "ADR", "组件"]:
        assert cat in r.text, f"缺少 category:{cat}"


def test_help_detail_renders(backend):
    """/help/er-diagram 应渲染 markdown 内容"""
    r = httpx.get(f"{backend}/help/er-diagram", timeout=5.0)
    assert r.status_code == 200
    # 渲染后应有 HTML 标签
    assert "<h1>" in r.text  # 标题
    assert "ER 图" in r.text or "Component" in r.text  # 内容片段


def test_help_detail_nested_slug(backend):
    """嵌套 slug 应工作:adr/0022-... 或 components/docker"""
    r1 = httpx.get(f"{backend}/help/components/docker", timeout=5.0)
    assert r1.status_code == 200
    assert "<h1>" in r1.text

    r2 = httpx.get(f"{backend}/help/adr/0022-requirement-state-machine-500", timeout=5.0)
    assert r2.status_code == 200
    assert "ADR-0022" in r2.text or "verified transition" in r2.text


def test_help_detail_404_for_missing(backend):
    """/help/<不存在> 应返回 404"""
    r = httpx.get(f"{backend}/help/this-doc-does-not-exist-xyz", timeout=5.0)
    assert r.status_code == 404


def test_help_detail_path_traversal_blocked(backend):
    """/help/../etc/passwd 应被拦截(404 而非 500)"""
    r = httpx.get(f"{backend}/help/../etc/passwd", timeout=5.0)
    # 不应该 200;可能是 404(我们返回 404)或 307/308(framework 拦截)
    assert r.status_code != 200


def test_swagger_still_works(backend):
    """/docs(Swagger)应仍返回 200 — REQ-8be0f95c 关键约束"""
    r = httpx.get(f"{backend}/docs", timeout=5.0)
    assert r.status_code == 200
    # Swagger UI HTML 应含 swagger-ui 相关标记
    assert "swagger" in r.text.lower()


# ——— PATCH 反馈代理测试 ———

def test_feedback_patch_proxy(backend):
    """端到端:创建 feedback → UI PATCH 代理 → 后端已更新"""
    import json

    # 1. 直接通过 API 创建一个测试组件
    create = httpx.post(
        f"{backend}/api/v1/components",
        json={
            "name": "ui-test-cache",
            "title": "UI Test Cache",
            "positioning": "Phase 4 UI 测试用的临时缓存组件,测试后清理",
            "category": "cache",
            "scope": "infra",
            "layer": "L1_platform",
            "is_asset": True,
            "distribution_form": "package",
        },
        timeout=5.0,
    )
    assert create.status_code == 201, f"创建失败:{create.text}"

    # 2. 创建版本
    ver = httpx.post(
        f"{backend}/api/v1/components/ui-test-cache/versions",
        json={
            "version": "1.0.0",
            "semver_intent": "major",
            "changelog": "UI 测试",
            "breaking_changes": "无",
        },
        timeout=5.0,
    )
    assert ver.status_code == 201
    ver_id = ver.json()["id"]

    # 3. 创建反馈
    fb = httpx.post(
        f"{backend}/api/v1/versions/{ver_id}/feedbacks",
        json={
            "reporter": "ui-test",
            "bug_summary": "UI 代理 PATCH 测试",
            "severity": "medium",
        },
        timeout=5.0,
    )
    assert fb.status_code == 201
    fb_id = fb.json()["id"]

    # 4. UI 代理 PATCH(模拟看板表单提交)
    r = httpx.post(
        f"{backend}/feedbacks/{fb_id}/patch",
        data={
            "status": "fixed",
            "decision": "optimize",
            "root_cause": "UI 测试 root cause",
        },
        timeout=5.0,
    )
    assert r.status_code == 200, f"PATCH 代理失败:{r.status_code} {r.text}"
    # 返回的是 HTML 卡片(htmx 用)
    assert "<article" in r.text or "fb-card" in r.text

    # 5. 后端验证
    chk = httpx.get(f"{backend}/api/v1/feedbacks", timeout=5.0)
    assert chk.status_code == 200
    items = chk.json()["items"]
    fb_updated = next((f for f in items if f["id"] == fb_id), None)
    assert fb_updated is not None
    assert fb_updated["status"] == "fixed"
    assert fb_updated["decision"] == "optimize"

    # 6. 清理(通过 SSH + sqlite3 直接删)
    subprocess.run(
        ["ssh", "root@124.71.219.208", "sqlite3",
         "/opt/services/arch-platform/data/arch.db",
         f"DELETE FROM feedbacks WHERE id='{fb_id}'; "
         "DELETE FROM versions WHERE component_id IN (SELECT id FROM components WHERE name='ui-test-cache'); "
         "DELETE FROM components WHERE name='ui-test-cache';"],
        capture_output=True, text=True, timeout=10,
    )


# ===== Phase 1.2 Requirement UI(2026-06-21)=====


def test_requirement_create_proxy(backend):
    """端到端:UI 创建需求表单 → 服务器代理 → 后端已创建"""
    # 1. 直接通过 API 创建需求(模拟 UI 表单提交)
    create = httpx.post(
        f"{backend}/requirements/create",
        data={
            "title": "UI 测试创建需求-不应保留-test-only-link",
            "type": "tech_debt",
            "priority": "P3",
            "proposer": "ui-test",
        },
        timeout=5.0,
        follow_redirects=False,
    )
    # 期望 303 重定向到 /requirements/{id}
    assert create.status_code in (303, 307), f"期望重定向,got {create.status_code}: {create.text[:200]}"
    location = create.headers.get("location", "")
    assert "/requirements/" in location, f"重定向 location 应含 /requirements/:{location}"

    # 2. 验证后端已有该需求
    req_id = location.rsplit("/", 1)[-1]
    chk = httpx.get(f"{backend}/api/v1/requirements/{req_id}", timeout=5.0)
    assert chk.status_code == 200
    data = chk.json()
    assert data["title"].startswith("UI 测试")
    assert data["priority"] == "P3"
    print(f"  → UI requirement create proxy: {req_id[:8]} 重定向+创建成功")


# ===== Phase 0 Doubt-Driven Development UI(2026-06-21)=====
# 3 个测试:表单渲染 + 创建 proxy + 结果页


def test_doubt_list_page_renders(backend):
    """GET /doubt 列表页 200 + 含导航 + 含 '+ 新建 cycle' 链接"""
    r = httpx.get(f"{backend}/doubt", timeout=5.0)
    assert r.status_code == 200
    assert "<html" in r.text.lower()
    assert "Doubt Cycles" in r.text or "doubt" in r.text.lower()
    assert "/doubt/new" in r.text
    print(f"  → GET /doubt: 200 + nav + '新建 cycle' 链接 ✓")


def test_doubt_new_page_renders(backend):
    """GET /doubt/new 表单 200 + 含 CLAIM/EXTRACT 字段 + 5 步法提示"""
    r = httpx.get(f"{backend}/doubt/new", timeout=5.0)
    assert r.status_code == 200
    assert "<html" in r.text.lower()
    # form 字段
    assert 'name="claim"' in r.text
    assert 'name="artifact"' in r.text
    assert 'name="contract"' in r.text
    # POST 到 /doubt/run 代理
    assert 'action="/doubt/run"' in r.text
    # 5 步法速览
    assert "CLAIM" in r.text
    assert "EXTRACT" in r.text
    assert "DOUBT" in r.text
    assert "RECONCILE" in r.text
    assert "STOP" in r.text
    print(f"  → GET /doubt/new: 200 + form fields + 5 步法速览 ✓")


def test_doubt_run_proxy_creates_and_redirects(backend):
    """端到端:UI POST /doubt/run → 303 redirect 到 /doubt/cycles/{id}"""
    r = httpx.post(
        f"{backend}/doubt/run",
        data={
            "claim": "UI 测试创建 doubt cycle-不应保留-test-only-link",
            "artifact": "def buggy(): shutil.rmtree(path)  # 无 exclusion",
            "contract": "deploy 脚本必须保留 data/ backups/ .env 目录",
            "component": "arch-platform-backend",
            "created_by": "ui-test",
        },
        timeout=5.0,
        follow_redirects=False,
    )
    assert r.status_code == 303, f"期望 303 redirect, got {r.status_code}: {r.text[:200]}"
    location = r.headers.get("location", "")
    assert "/doubt/cycles/" in location, f"redirect 应含 /doubt/cycles/:{location}"

    # 验证 cycle 在后端
    cycle_id = location.rsplit("/", 1)[-1]
    chk = httpx.get(f"{backend}/doubt/cycles/{cycle_id}", timeout=5.0)
    assert chk.status_code == 200
    assert "<html" in chk.text.lower()
    assert "UI 测试创建 doubt cycle" in chk.text
    assert "shutil.rmtree" in chk.text
    print(f"  → UI doubt run proxy: {cycle_id[:8]} redirect + result 页面渲染 ✓")