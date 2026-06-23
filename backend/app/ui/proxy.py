"""服务器代理:Web UI PATCH /feedbacks/{id} 转发到后端 API

为什么需要代理:
- Web UI 用户不持有 API Key
- PATCH feedback 是 Web UI 唯一的写操作
- 服务器用环境变量 ARCH_PLATFORM_API_KEY 转发请求

约定:
- API_KEY 未设置(开放模式)→ 不带 X-API-Key 头,后端允许 GET 和 PATCH(因为 PATCH 不强校验 Key?)

  实际:后端 PATCH /feedbacks/{id} 有 Depends(require_api_key),所以需要 Key
  解决方案:服务器端 env 注入 Key,客户端无感
"""
from __future__ import annotations

import os
from typing import Any, Optional

import httpx
from fastapi import HTTPException


# 后端 API 地址(同进程走 127.0.0.1)
API_BASE = os.environ.get("ARCH_API_BASE", "http://127.0.0.1:8088")
API_KEY = os.environ.get("ARCH_PLATFORM_API_KEY", "")


async def api_get(path: str, params: Optional[dict] = None) -> Any:
    """GET 后端 API"""
    headers = {}
    if API_KEY:
        headers["X-API-Key"] = API_KEY

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(f"{API_BASE}{path}", params=params, headers=headers)
    return _handle_response(resp)


async def api_post(path: str, json: dict) -> Any:
    """POST 后端 API"""
    headers = {}
    if API_KEY:
        headers["X-API-Key"] = API_KEY

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(f"{API_BASE}{path}", json=json, headers=headers)
    return _handle_response(resp)


async def api_patch(path: str, json: dict) -> Any:
    """PATCH 后端 API(主要用于 feedback)"""
    headers = {}
    if API_KEY:
        headers["X-API-Key"] = API_KEY

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.patch(f"{API_BASE}{path}", json=json, headers=headers)
    return _handle_response(resp)


async def api_delete(
    path: str,
    params: Optional[dict] = None,
    json: Any = None,
) -> Any:
    """DELETE 后端 API(支持 query params,例如 component 删除的 reason)

    REQ-f740a3be:组件 UI delete 按钮 → DELETE /api/v1/components/{id}?reason=...
    reason 是 query string(后端用 Query(min_length=10) 校验),不是 body。
    """
    headers = {}
    if API_KEY:
        headers["X-API-Key"] = API_KEY

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.delete(
            f"{API_BASE}{path}",
            params=params,
            json=json,
            headers=headers,
        )
    return _handle_response(resp)


def _handle_response(resp: httpx.Response) -> Any:
    """统一处理响应:错误抛 HTTPException(让前端看到状态码)"""
    if resp.is_success:
        if resp.status_code == 204 or not resp.content:
            return None
        return resp.json()

    # 错误:抛 HTTPException
    try:
        detail = resp.json().get("detail", resp.text)
    except Exception:
        detail = resp.text
    raise HTTPException(status_code=resp.status_code, detail=detail)