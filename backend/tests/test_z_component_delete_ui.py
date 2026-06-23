"""REQ-f740a3be 组件 UI delete/restore — 单元测试

4 个测试用例(直接调函数 + monkeypatch api_delete/api_post,免启动后端):
1. test_ui_delete_success_redirect_303 — mock api_delete 成功 → 303 到 /components
2. test_ui_delete_reason_too_short_422 — Form reason="short"(< 10)→ Pydantic 422
3. test_ui_restore_success_redirect_303 — mock api_post 成功 → 303 到 /components/{name}
4. test_ui_delete_api_409_returns_error_json — mock api_delete 抛 HTTPException(409)→ JSON {error:...}

约定:
- pytest test_z_ 前缀 → 字母序排最后
- 与 test_z_component_delete.py 配套(那是 API 层,本文件是 UI 代理层)
- 不依赖真后端,mock api_delete/api_post 即可
"""
import importlib
import sys
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from fastapi.responses import JSONResponse, RedirectResponse


@pytest.fixture(scope="module", autouse=True)
def _routes_module():
    """import routes 模块(monkeypatch 在每个 case 各自做)"""
    # 先确保 proxy 已加载(若已 import,reset)
    if "app.ui.proxy" in sys.modules:
        importlib.reload(sys.modules["app.ui.proxy"])
    if "app.ui.routes" in sys.modules:
        importlib.reload(sys.modules["app.ui.routes"])
    from app.ui import routes

    return routes


def _make_request():
    """构造完整 ASGI scope 的 Request 对象(让 query_params / form 解析都正常)"""
    from starlette.requests import Request

    scope = {
        "type": "http",
        "method": "GET",
        "headers": [(b"host", b"testserver")],
        "query_string": b"",
        "path": "/",
    }
    return Request(scope)


# ===== Case 1: delete 成功 → 303 redirect to /components =====

@pytest.mark.asyncio
async def test_ui_delete_success_redirect_303(_routes_module):
    """POST /components/{name}/delete + 合法 reason → api_delete 被调 → 303 to /components"""
    routes = _routes_module

    mock_api_delete = AsyncMock(return_value={"id": "fake-id", "is_archived": True})

    with patch.object(routes, "api_delete", mock_api_delete):
        resp = await routes.component_delete_from_ui(
            name="my-comp",
            request=_make_request(),
            reason="测试 UI delete 成功路径-不应保留-cleanup",
        )

    # 1. mock 被以正确参数调用
    mock_api_delete.assert_awaited_once()
    call_args = mock_api_delete.call_args
    assert call_args.args[0] == "/api/v1/components/my-comp", (
        f"path 应为 /api/v1/components/my-comp:got {call_args}"
    )
    assert call_args.kwargs.get("params") == {"reason": "测试 UI delete 成功路径-不应保留-cleanup"}, (
        f"params 应含 reason:got {call_args.kwargs}"
    )

    # 2. 返回 303 RedirectResponse
    assert isinstance(resp, RedirectResponse), f"期望 RedirectResponse,got {type(resp).__name__}"
    assert resp.status_code == 303, f"期望 303,got {resp.status_code}"
    assert str(resp.headers.get("location", "")) == "/components", (
        f"location 应为 /components:got {resp.headers.get('location')}"
    )
    print("  → case 1: UI delete 成功 → 303 → /components ✓")


# ===== Case 2: reason 太短(< 10)→ Pydantic Form 422 =====

def test_ui_delete_reason_too_short_422(_routes_module):
    """Form reason="short"(5 字符)→ HTTP 调用时 FastAPI 返 422(走真 ASGI 端点)

    业务说明:`min_length=10` 是 FastAPI Form() 的 Pydantic Field 约束,
    直接调 Python 函数不会触发(那是 FastAPI dependency injection 做的),
    走 HTTP 路径才会被校验。所以这里用 FastAPI TestClient 走真端点。
    """
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)
    resp = client.post(
        "/components/my-comp/delete",
        data={"reason": "short"},  # 5 字符,违反 min_length=10
        follow_redirects=False,
    )
    assert resp.status_code == 422, (
        f"期望 422,got {resp.status_code}:{resp.text[:200]}"
    )
    # 422 body 应提及 reason / min_length
    body = resp.text.lower()
    assert "reason" in body or "min_length" in body or "at least 10" in body or "string_too_short" in body, (
        f"422 body 应提及 reason/min_length:got {resp.text[:300]}"
    )
    print("  → case 2: reason 太短 → HTTP 422 ✓")


# ===== Case 3: restore 成功 → 303 redirect to /components/{name} =====

@pytest.mark.asyncio
async def test_ui_restore_success_redirect_303(_routes_module):
    """POST /components/{name}/restore → api_post 被调 → 303 to /components/{name}"""
    routes = _routes_module

    mock_api_post = AsyncMock(return_value={"id": "fake-id", "is_archived": False})

    with patch.object(routes, "api_post", mock_api_post):
        resp = await routes.component_restore_from_ui(
            name="my-comp",
            request=_make_request(),
        )

    # 1. mock 被以正确参数调用
    mock_api_post.assert_awaited_once()
    call_args = mock_api_post.call_args
    assert call_args.args[0] == "/api/v1/components/my-comp/restore", (
        f"path 应为 /api/v1/components/my-comp/restore:got {call_args}"
    )

    # 2. 返回 303 RedirectResponse → /components/my-comp
    assert isinstance(resp, RedirectResponse)
    assert resp.status_code == 303
    assert str(resp.headers.get("location", "")) == "/components/my-comp", (
        f"restore 后应跳到详情页 /components/my-comp:got {resp.headers.get('location')}"
    )
    print("  → case 3: UI restore 成功 → 303 → /components/{name} ✓")


# ===== Case 4: delete 失败(API 409 被引用)→ JSON {error:...} =====

@pytest.mark.asyncio
async def test_ui_delete_api_409_returns_error_json(_routes_module):
    """mock api_delete 抛 HTTPException(409, '被引用')→ UI 路由应返 JSON 409"""
    routes = _routes_module

    mock_api_delete = AsyncMock(
        side_effect=HTTPException(
            status_code=409,
            detail="组件被其他组件引用:compo-parent,需先解除依赖",
        )
    )

    with patch.object(routes, "api_delete", mock_api_delete):
        resp = await routes.component_delete_from_ui(
            name="my-comp",
            request=_make_request(),
            reason="测试 UI delete 失败路径-不应保留",
        )

    # 1. 返回 JSONResponse(非 RedirectResponse)
    assert isinstance(resp, JSONResponse), f"期望 JSONResponse,got {type(resp).__name__}"
    assert resp.status_code == 409, f"期望 409,got {resp.status_code}"

    # 2. body 应含 error 字段,文案透传 detail
    body = resp.body.decode("utf-8") if isinstance(resp.body, bytes) else resp.body
    import json as _json

    parsed = _json.loads(body)
    assert "error" in parsed, f"body 应含 error 字段:got {parsed}"
    assert "被引用" in parsed["error"] or "compo-parent" in parsed["error"], (
        f"error 文案应透传 detail:got {parsed['error']}"
    )
    print(f"  → case 4: API 409 → UI 返 JSON 409 + error 文案透传 ✓")


# ===== Bonus:include_archived 参数在 GET /components 路由中透传 =====

@pytest.mark.asyncio
async def test_ui_components_list_includes_archived_param(_routes_module):
    """GET /components?include_archived=true → api_get 被调时 params 含 include_archived=true

    实现说明:为避免 template 渲染依赖太多,这里直接调 components_list 函数体内部
    会先调 _safe_get 两次(list_query + params),只要其中任意一次含 include_archived 就算通过。
    """
    routes = _routes_module

    captured_params: list = []

    async def fake_safe_get(path, params=None, default=None):
        captured_params.append(dict(params or {}))
        return {"items": [], "total": 0}

    with patch.object(routes, "_safe_get", side_effect=fake_safe_get):
        # 直接 monkeypatch templates.TemplateResponse 避免真渲染
        from fastapi.responses import HTMLResponse
        with patch.object(
            routes, "templates", new=_FakeTemplate()
        ):
            await routes.components_list(
                request=_make_request(),
                include_archived="true",
            )

    # 验证:两次 _safe_get 调用里,至少有一次 params 含 include_archived=true
    seen_archived = any(
        p.get("include_archived") == "true" for p in captured_params
    )
    assert seen_archived, (
        f"include_archived=true 应至少被透传一次:got {captured_params}"
    )
    print(f"  → bonus: include_archived=true 透传到 API({len(captured_params)} 次调用)✓")


class _FakeTemplate:
    """最小 template mock,让 TemplateResponse 不真渲染直接返 HTMLResponse"""

    def TemplateResponse(self, request, name, context):
        from fastapi.responses import HTMLResponse
        return HTMLResponse(f"<html>mock:{name}</html>", status_code=200)
