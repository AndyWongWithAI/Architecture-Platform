"""Components 相关 tools"""
from typing import Optional

from ..client import api_get, api_post


# ——— 读 ———

def list_components(
    layer: Optional[str] = None,
    category: Optional[str] = None,
    is_asset: Optional[bool] = None,
    q: Optional[str] = None,
    limit: int = 50,
) -> dict:
    """列出组件,支持 layer/category/is_asset/q 过滤"""
    params = {"limit": limit}
    if layer:
        params["layer"] = layer
    if category:
        params["category"] = category
    if is_asset is not None:
        params["is_asset"] = "true" if is_asset else "false"
    if q:
        params["q"] = q
    return api_get("/api/v1/components", params)


def get_component(name: str) -> dict:
    """按 name 取组件详情(含版本列表)"""
    return api_get(f"/api/v1/components/{name}")


def use_component(name: str) -> dict:
    """取组件的 install_command + usage_example(给 LLM 写代码用)"""
    return api_get(f"/api/v1/components/{name}/usage")


def tree_component(name: str, max_depth: int = 5) -> dict:
    """展开组件的 composed_of 依赖树"""
    return api_get(f"/api/v1/components/{name}/tree", {"max_depth": max_depth})


# ——— 写(需要服务器持 API Key)———

def create_component(
    name: str,
    title: str,
    positioning: str,
    category: str,
    layer: str,
    scope: str = "lib",
    is_asset: bool = True,
    distribution_form: Optional[str] = None,
    interface_contract: Optional[str] = None,
    knowledge_artifact: bool = False,
    tags: Optional[list[str]] = None,
    repo_url: Optional[str] = None,
    package_name: Optional[str] = None,
    install_command: Optional[str] = None,
    usage_example: Optional[str] = None,
) -> dict:
    """登记新组件(Phase 2 设计定稿)

    注意:
    - is_asset=true 必须填 distribution_form
    - distribution_form=http_api 必须填 interface_contract
    """
    data = {
        "name": name,
        "title": title,
        "positioning": positioning,
        "category": category,
        "layer": layer,
        "scope": scope,
        "is_asset": is_asset,
        "knowledge_artifact": knowledge_artifact,
    }
    if distribution_form:
        data["distribution_form"] = distribution_form
    if interface_contract:
        data["interface_contract"] = interface_contract
    if tags:
        data["tags"] = tags
    if repo_url:
        data["repo_url"] = repo_url
    if package_name:
        data["package_name"] = package_name
    if install_command:
        data["install_command"] = install_command
    if usage_example:
        data["usage_example"] = usage_example

    return api_post("/api/v1/components", data)