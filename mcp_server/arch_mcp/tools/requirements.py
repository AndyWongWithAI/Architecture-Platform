"""Requirements 相关 tools — Phase 1 需求登记

对齐 feedbacks.py 的风格(reuse)
"""
from typing import Optional, List

from ..client import api_get, api_post, api_patch


def list_requirements(
    status: Optional[str] = None,
    priority: Optional[str] = None,
    type: Optional[str] = None,
    assignee: Optional[str] = None,
    component_id: Optional[str] = None,
    include_archived: bool = False,
    limit: int = 50,
) -> dict:
    """列出需求(Phase 1)"""
    params = {"limit": limit}
    if status:
        params["status"] = status
    if priority:
        params["priority"] = priority
    if type:
        params["type"] = type
    if assignee:
        params["assignee"] = assignee
    if component_id:
        params["component_id"] = component_id
    if include_archived:
        params["include_archived"] = True
    return api_get("/api/v1/requirements", params)


def create_requirement(
    component_id: Optional[str] = None,
    title: str = "",
    type: str = "new_feature",
    priority: str = "P2",
    user_story: Optional[str] = None,
    acceptance_criteria: Optional[list] = None,
    nfr: Optional[dict] = None,
    proposer: str = "mcp",
    assignee: Optional[str] = None,
    due_date: Optional[str] = None,
    tags: Optional[List[str]] = None,
    description: Optional[str] = None,
) -> dict:
    """登记新需求(Phase 1)"""
    data = {
        "title": title,
        "type": type,
        "priority": priority,
        "proposer": proposer,
    }
    if description:
        data["description"] = description
    if user_story:
        data["user_story"] = user_story
    if acceptance_criteria:
        data["acceptance_criteria"] = acceptance_criteria
    if nfr:
        data["nfr"] = nfr
    if assignee:
        data["assignee"] = assignee
    if due_date:
        data["due_date"] = due_date
    if tags:
        data["tags"] = tags
    if component_id:
        return api_post(f"/api/v1/components/{component_id}/requirements", data)
    return api_post("/api/v1/requirements", data)


def get_requirement(requirement_id: str) -> dict:
    """需求详情"""
    return api_get(f"/api/v1/requirements/{requirement_id}")


def update_requirement(
    requirement_id: str,
    status: Optional[str] = None,
    priority: Optional[str] = None,
    assignee: Optional[str] = None,
    description: Optional[str] = None,
    due_date: Optional[str] = None,
    tags: Optional[List[str]] = None,
) -> dict:
    """更新需求(状态 / 优先级 / 负责人)"""
    data = {}
    if status:
        data["status"] = status
    if priority:
        data["priority"] = priority
    if assignee:
        data["assignee"] = assignee
    if description:
        data["description"] = description
    if due_date:
        data["due_date"] = due_date
    if tags:
        data["tags"] = tags
    return api_patch(f"/api/v1/requirements/{requirement_id}", data)