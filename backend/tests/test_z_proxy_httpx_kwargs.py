"""FB-? 集成测试:proxy.py httpx 调用签名

2026-06-23 用户报告:删除组件时 UI 弹 "Unexpected token 'I', Internal S... is not valid JSON"。
根因:proxy.api_delete() 传 `json=json` 给 `httpx.AsyncClient.delete()`,
但 httpx 的 .delete() 方法**不支持** json kwarg(只有 POST/PATCH/PUT 支持),
每次调用都抛 TypeError。被 UI 路由 except HTTPException 漏掉,返回 500,
前端 JSON.parse 失败。

本测试用 httpx.MockTransport 拦截真实 httpx 调用,验证:
1. api_delete 不会抛 TypeError
2. api_delete 正确把 params 作为 query string 传出去
3. api_delete 正确处理 422 "already archived" 错误(抛 HTTPException)

历史教训:
- 单测 mock 了 api_delete 函数本身,没覆盖 httpx 调用层 → 漏报
- 这次必须测真实 httpx 路径,防止以后又出现类似签名错误

约定:
- pytest test_z_ 前缀 → 字母序排最后
- 不依赖真后端,用 httpx.MockTransport 拦截
"""
import sys
from typing import Any

import httpx
import pytest
from fastapi import HTTPException


@pytest.fixture
def patched_api_base(monkeypatch):
    """重定向 API_BASE 到一个 dummy host,实际请求被 MockTransport 拦截"""
    from app.ui import proxy

    # 让所有 httpx 请求都被 MockTransport 接管
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        # 捕获请求,供测试断言
        captured["request"] = request
        captured["method"] = request.method
        captured["url"] = str(request.url)
        captured["headers"] = dict(request.headers)
        captured["content"] = request.content

        # 模拟后端 422 already archived(组件场景)
        if "components/crawl" in str(request.url):
            return httpx.Response(
                422,
                json={"detail": "component already archived"},
            )
        # 默认 200 OK + 空 JSON
        return httpx.Response(200, json={"ok": True})

    transport = httpx.MockTransport(handler)
    # monkeypatch AsyncClient 用我们的 transport
    original_async_client = httpx.AsyncClient

    def patched_async_client(*args, **kwargs):
        kwargs["transport"] = transport
        return original_async_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", patched_async_client)
    return captured


@pytest.mark.asyncio
async def test_api_delete_does_not_pass_json_kwarg(patched_api_base):
    """FB-? 核心回归测试:api_delete 必须能成功调用 httpx 而不抛 TypeError

    历史:client.delete(json=json) → TypeError,因为 .delete() 不支持 json kwarg
    修复:改用 client.request("DELETE", ...) 替代 client.delete()
    """
    from app.ui.proxy import api_delete

    # 这条调用曾经会抛 TypeError: AsyncClient.delete() got an unexpected keyword argument 'json'
    # 修复后应该正常返回(后端返回 200 + {"ok": true})
    result = await api_delete("/api/v1/components/test-comp", params={"reason": "test-reason-12345"})

    assert result == {"ok": True}
    # 验证请求 method 是 DELETE
    assert patched_api_base["method"] == "DELETE"
    # 验证 reason 作为 query string 传出去(而不是 body)
    assert "reason=test-reason-12345" in patched_api_base["url"]


@pytest.mark.asyncio
async def test_api_delete_handles_422_already_archived(patched_api_base):
    """模拟组件已归档场景:api_delete 应该抛 HTTPException(422) 让 UI 路由捕获"""
    from app.ui.proxy import api_delete

    with pytest.raises(HTTPException) as exc_info:
        await api_delete(
            "/api/v1/components/crawl-manhua666",
            params={"reason": "test-reason-12345"},
        )

    assert exc_info.value.status_code == 422
    assert "already archived" in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_api_delete_preserves_query_params(patched_api_base):
    """验证 reason 等 query params 正确传递"""
    from app.ui.proxy import api_delete

    await api_delete(
        "/api/v1/components/some-component",
        params={"reason": "complex-reason-with-special=chars&symbols"},
    )

    # reason 应该作为 query string(URL-encoded)
    url = patched_api_base["url"]
    assert "reason=" in url
    # 验证 body 是空的(DELETE 不应有 body,只有 query)
    assert patched_api_base["content"] == b""