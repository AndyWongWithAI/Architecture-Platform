"""HTTP 客户端:封装 arch-platform API 调用

特性:
- 自动加 X-API-Key 头(如果配置了)
- 错误友好提示(404/409/422/500 分别处理)
- 超时配置
- 支持 CLI/容器/服务端调用
"""
from __future__ import annotations

import json
import re
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

    def delete_component(self, name: str, reason: str) -> dict:
        """REQ-d1deda65:软删除组件(is_archived=true)"""
        return self.request("DELETE", f"/api/v1/components/{name}", params={"reason": reason})

    def restore_component(self, name: str) -> dict:
        """REQ-d1deda65:撤销软删除(is_archived=false)"""
        return self.request("POST", f"/api/v1/components/{name}/restore")

    def report_fcr(self, name: str, fcr: float) -> dict:
        """Q3 目标 1 / fcr metric(2026-06-27)— 上报 component 的 feedback coverage ratio
        由 audit --scope=skills --modules=principles_depth 跑完后调用
        """
        return self.request("PUT", f"/api/v1/components/{name}/fcr", json={"fcr": fcr})

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

    # ——— Requirement (Phase 1) ———

    # UUID v1-5 形如 xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx(36 字符,8-4-4-4-12)
    _UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)

    def _resolve_req_id(self, req_id: str) -> str:
        """短 ID 前缀 → 完整 UUID。list 表格只显示前 8 位,
        直接拼到 URL 会 404(参见 feedback 62634495)。
        - 完整 UUID:原样返回
        - 前缀:遍历 list_requirements 分页查找匹配;唯一返回,多匹配或 0 匹配抛错
        """
        if self._UUID_RE.match(req_id):
            return req_id
        prefix = req_id.lower()
        # 默认只看未归档,避免误命中已软删的同前缀记录
        matches: list[str] = []
        offset = 0
        page_size = 100
        max_pages = 20  # 上限 2000 条,够用
        for _ in range(max_pages):
            data = self.list_requirements(include_archived=False, limit=page_size, offset=offset)
            items = data.get("items", [])
            for it in items:
                rid = it.get("id", "")
                if rid.lower().startswith(prefix):
                    matches.append(rid)
                    if len(matches) > 1:
                        # 早退,不必继续翻页
                        break
            total = data.get("total", len(items))
            offset += page_size
            if offset >= total or len(items) == 0 or len(matches) > 1:
                break
        if not matches:
            raise APIError(
                404,
                f"未找到 ID 前缀 '{req_id}' 对应的需求(可能已归档,试试 --include-archived)",
            )
        if len(matches) > 1:
            short = ", ".join(m[:8] for m in matches[:5])
            raise APIError(
                409,
                f"前缀 '{req_id}' 匹配到 {len(matches)} 个需求,请用更长的前缀或完整 UUID。匹配: {short}",
            )
        return matches[0]

    def list_requirements(self, **filters) -> dict:
        return self.request("GET", "/api/v1/requirements", params=filters)

    def get_requirement(self, req_id: str) -> dict:
        full_id = self._resolve_req_id(req_id)
        return self.request("GET", f"/api/v1/requirements/{full_id}")

    def create_requirement(self, component_id: str, data: dict) -> dict:
        """嵌套入口:绑 component"""
        return self.request("POST", f"/api/v1/components/{component_id}/requirements", json=data)

    def create_requirement_flat(self, data: dict) -> dict:
        """平铺入口:不绑 component"""
        return self.request("POST", "/api/v1/requirements", json=data)

    def patch_requirement(self, req_id: str, data: dict) -> dict:
        full_id = self._resolve_req_id(req_id)
        return self.request("PATCH", f"/api/v1/requirements/{full_id}", json=data)

    def archive_requirement(self, req_id: str) -> dict:
        full_id = self._resolve_req_id(req_id)
        return self.request("DELETE", f"/api/v1/requirements/{full_id}")

    def restore_requirement(self, req_id: str) -> dict:
        full_id = self._resolve_req_id(req_id)
        return self.request("POST", f"/api/v1/requirements/{full_id}/restore")

    def link_feedback_requirement(self, fb_id: str, req_id: str) -> dict:
        full_id = self._resolve_req_id(req_id)
        return self.request(
            "POST", f"/api/v1/feedbacks/{fb_id}/link-requirement",
            json={"requirement_id": full_id},
        )

    # ——— Doubt-Driven Development(2026-06-21 新增)———
    def create_doubt_cycle(self, data: dict) -> dict:
        """开一个 doubt cycle(Step 1 CLAIM + Step 2 EXTRACT)"""
        return self.request("POST", "/api/v1/doubt/cycle", json=data)

    def get_doubt_cycle(self, cycle_id: str) -> dict:
        return self.request("GET", f"/api/v1/doubt/cycles/{cycle_id}")

    def add_doubt_finding(self, cycle_id: str, data: dict) -> dict:
        """RECONCILE:加 finding"""
        return self.request("POST", f"/api/v1/doubt/cycles/{cycle_id}/findings", json=data)

    def advance_doubt_cycle(self, cycle_id: str, params: dict) -> dict:
        """DOUBT:推进 cycle(写 verdict / score / next_step)"""
        return self.request("PATCH", f"/api/v1/doubt/cycles/{cycle_id}/advance", params=params)

    def stop_doubt_cycle(self, cycle_id: str, data: dict) -> dict:
        """STOP:用户主动 ship"""
        return self.request("POST", f"/api/v1/doubt/cycles/{cycle_id}/stop", json=data)

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

    # ——— CoreThought(REQ-968b1c99,第 6 大实体)———

    def list_core_thoughts(self, **filters) -> dict:
        return self.request("GET", "/api/v1/core-thoughts", params=filters)

    def get_core_thought(self, ct_id: str) -> dict:
        return self.request("GET", f"/api/v1/core-thoughts/{ct_id}")

    def create_core_thought(self, data: dict) -> dict:
        return self.request("POST", "/api/v1/core-thoughts", json=data)

    def update_core_thought(self, ct_id: str, data: dict) -> dict:
        return self.request("PATCH", f"/api/v1/core-thoughts/{ct_id}", json=data)

    def archive_core_thought(self, ct_id: str) -> dict:
        return self.request("DELETE", f"/api/v1/core-thoughts/{ct_id}")

    def restore_core_thought(self, ct_id: str) -> dict:
        return self.request("POST", f"/api/v1/core-thoughts/{ct_id}/restore")

    def list_core_thoughts_by_tag(self, tag: str) -> dict:
        return self.request("GET", f"/api/v1/core-thoughts/by-tag/{tag}")