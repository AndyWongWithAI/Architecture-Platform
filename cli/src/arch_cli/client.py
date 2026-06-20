"""HTTP 客户端:封装 arch-platform API 调用

特性:
- 自动加 X-API-Key 头(如果配置了)
- 错误友好提示(404/409/422/500 分别处理)
- 超时配置
- 支持 CLI/容器/服务端调用
"""
from __future__ import annotations

import json
from typing import Any, Optional

import httpx

from .config import Config


# HTTP 状态码 → 友好错误信息
class APIError(Exception):
    """API 调用错误"""

    def __init__(self, status_code: int, message: str, details: Optional[Any] = None):
        self.status_code = status_code
        self.message = message
        self.details = details
        super().__init__(f"[{status_code}] {message}")


class ArchClient:
    """架构平台 API 客户端"""

    def __init__(self, config: Optional[Config] = None, timeout: float = 30.0):
        self.config = config or Config.load()
        self.timeout = timeout

    def _headers(self) -> dict:
        h = {"Accept": "application/json"}
        if self.config.api_key:
            h["X-API-Key"] = self.config.api_key
        return h

    def _handle(self, resp: httpx.Response) -> Any:
        """统一处理响应:成功 → JSON,失败 → APIError"""
        if resp.status_code == 204:
            return None
        if resp.is_success:
            return resp.json() if resp.content else None

        # 错误处理
        try:
            err = resp.json()
            detail = err.get("detail", err)
        except Exception:
            detail = resp.text

        msg = ""
        if isinstance(detail, list):
            # 422 Pydantic validation error:[{loc, msg, type}]
            msg = "; ".join(
                f"{'.'.join(str(x) for x in e.get('loc', [])[1:])}: {e.get('msg', '')}"
                for e in detail
            )
        elif isinstance(detail, dict):
            msg = detail.get("msg", str(detail))
        else:
            msg = str(detail)

        # 友好错误前缀
        if resp.status_code == 401:
            prefix = "鉴权失败(检查 API Key 或服务端是否开启开放模式)"
        elif resp.status_code == 404:
            prefix = "资源不存在"
        elif resp.status_code == 409:
            prefix = "冲突(可能重名)"
        elif resp.status_code == 422:
            prefix = "请求参数错误"
        elif resp.status_code >= 500:
            prefix = "服务端错误"
        else:
            prefix = "请求失败"

        raise APIError(resp.status_code, f"{prefix}:{msg}", detail)

    def request(
        self,
        method: str,
        path: str,
        params: Optional[dict] = None,
        json: Optional[dict] = None,
    ) -> Any:
        """统一 request 方法"""
        url = f"{self.config.server_url.rstrip('/')}{path}"
        with httpx.Client(timeout=self.timeout) as client:
            resp = client.request(
                method,
                url,
                params=params,
                json=json,
                headers=self._headers(),
            )
        return self._handle(resp)

    # ——— Component CRUD ———

    def list_components(self, **filters) -> dict:
        return self.request("GET", "/api/v1/components", params=filters)

    def get_component(self, name: str) -> dict:
        return self.request("GET", f"/api/v1/components/{name}")

    def create_component(self, data: dict) -> dict:
        return self.request("POST", "/api/v1/components", json=data)

    def update_component(self, name: str, data: dict) -> dict:
        return self.request("PATCH", f"/api/v1/components/{name}", json=data)

    # ——— Version ———

    def list_versions(self, component_name: str) -> dict:
        return self.request("GET", f"/api/v1/components/{component_name}/versions")

    def create_version(self, component_name: str, data: dict) -> dict:
        return self.request("POST", f"/api/v1/components/{component_name}/versions", json=data)

    def get_version(self, version_id: str) -> dict:
        return self.request("GET", f"/api/v1/versions/{version_id}")

    # ——— Deployment ———

    def create_deployment(self, version_id: str, data: dict) -> dict:
        return self.request("POST", f"/api/v1/versions/{version_id}/deployments", json=data)

    def list_deployments(self) -> dict:
        return self.request("GET", "/api/v1/deployments")

    # ——— Feedback ———

    def list_feedbacks(self, **filters) -> dict:
        return self.request("GET", "/api/v1/feedbacks", params=filters)

    def create_feedback(self, version_id: str, data: dict) -> dict:
        return self.request("POST", f"/api/v1/versions/{version_id}/feedbacks", json=data)

    def patch_feedback(self, feedback_id: str, data: dict) -> dict:
        return self.request("PATCH", f"/api/v1/feedbacks/{feedback_id}", json=data)

    # ——— Search / Tree / Use ———

    def search(self, q: str) -> dict:
        return self.request("GET", "/api/v1/search", params={"q": q})

    def get_tree(self, name: str) -> dict:
        return self.request("GET", f"/api/v1/components/{name}/tree")

    def get_usage(self, name: str) -> dict:
        return self.request("GET", f"/api/v1/components/{name}/usage")

    # ——— Health ———

    def healthz(self) -> dict:
        return self.request("GET", "/healthz")