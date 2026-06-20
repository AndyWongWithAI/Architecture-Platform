"""HTTP 客户端:MCP Server → 后端 API

跟 arch_cli/client.py 类似,但同步 + 简化(不需要 JSON 输出 / 重试 / 错误友好化)。
MCP 工具的返回值直接给 AI 看,所以保持原始结构。
"""
from __future__ import annotations

import os
from typing import Any, Optional

import httpx


API_BASE = os.environ.get("ARCH_PLATFORM_URL", "http://127.0.0.1:8088")
API_KEY = os.environ.get("ARCH_PLATFORM_API_KEY", "")


def _headers() -> dict:
    h = {"Accept": "application/json"}
    if API_KEY:
        h["X-API-Key"] = API_KEY
    return h


def _handle(resp: httpx.Response) -> dict:
    """统一处理响应:返回 dict(成功)或抛出包含状态码的错误(失败)"""
    if resp.is_success:
        if resp.status_code == 204 or not resp.content:
            return {"success": True}
        return resp.json()

    # 错误:返回 dict 含 error 信息(避免抛异常让 MCP 中断)
    try:
        detail = resp.json().get("detail", resp.text)
    except Exception:
        detail = resp.text
    return {
        "error": True,
        "status_code": resp.status_code,
        "message": str(detail),
    }


def api_get(path: str, params: Optional[dict] = None) -> dict:
    with httpx.Client(timeout=30.0) as client:
        resp = client.get(f"{API_BASE}{path}", params=params, headers=_headers())
    return _handle(resp)


def api_post(path: str, json: dict) -> dict:
    with httpx.Client(timeout=30.0) as client:
        resp = client.post(f"{API_BASE}{path}", json=json, headers=_headers())
    return _handle(resp)


def api_patch(path: str, json: dict) -> dict:
    with httpx.Client(timeout=30.0) as client:
        resp = client.patch(f"{API_BASE}{path}", json=json, headers=_headers())
    return _handle(resp)


def health() -> dict:
    """健康检查"""
    try:
        with httpx.Client(timeout=5.0) as client:
            resp = client.get(f"{API_BASE}/healthz")
        return _handle(resp)
    except Exception as e:
        return {"error": True, "message": str(e)}