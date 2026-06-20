"""Deployments + Versions 相关 tools"""
from typing import Optional

from ..client import api_get, api_post


def list_deployments(
    host: Optional[str] = None,
    env: Optional[str] = None,
    limit: int = 50,
) -> dict:
    """列出部署历史"""
    params = {"limit": limit}
    if host:
        params["host"] = host
    if env:
        params["env"] = env
    return api_get("/api/v1/deployments", params)


def register_deployment(
    version_id: str,
    env: str,
    host: str,
    deploy_path: Optional[str] = None,
    config_hash: Optional[str] = None,
    lockfile_hash: Optional[str] = None,
    build_reproducible: bool = True,
    deployed_by: str = "mcp",
    resolved_versions: Optional[dict] = None,
) -> dict:
    """登记部署(Phase 6)— 通常由 GitHub Action 调用,但 MCP 也支持"""
    data = {
        "env": env,
        "host": host,
        "deployed_by": deployed_by,
        "build_reproducible": build_reproducible,
    }
    if deploy_path:
        data["deploy_path"] = deploy_path
    if config_hash:
        data["config_hash"] = config_hash
    if lockfile_hash:
        data["lockfile_hash"] = lockfile_hash
    if resolved_versions:
        data["resolved_versions"] = resolved_versions
    return api_post(f"/api/v1/versions/{version_id}/deployments", data)


def list_versions(component_name: str) -> dict:
    """列出组件的所有版本"""
    return api_get(f"/api/v1/components/{component_name}/versions")


def get_version(version_id: str) -> dict:
    """按 version_id 取版本详情"""
    return api_get(f"/api/v1/versions/{version_id}")