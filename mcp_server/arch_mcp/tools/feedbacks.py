"""Feedbacks 相关 tools"""
from typing import Optional

from ..client import api_get, api_patch, api_post


def list_feedbacks(
    status: Optional[str] = None,
    severity: Optional[str] = None,
    limit: int = 50,
) -> dict:
    """列出反馈"""
    params = {"limit": limit}
    if status:
        params["status"] = status
    if severity:
        params["severity"] = severity
    return api_get("/api/v1/feedbacks", params)


def create_feedback(
    version_id: str,
    summary: str,
    severity: str = "medium",
    root_cause: Optional[str] = None,
    fix_plan: Optional[str] = None,
    reporter: str = "mcp",
    reused_in: Optional[list[str]] = None,
) -> dict:
    """登记 Bug 反馈(Phase 8)"""
    data = {
        "version_id": version_id,
        "bug_summary": summary,
        "severity": severity,
        "reporter": reporter,
    }
    if root_cause:
        data["root_cause"] = root_cause
    if fix_plan:
        data["fix_plan"] = fix_plan
    if reused_in:
        data["reused_in_projects"] = reused_in
    return api_post("/api/v1/versions/{}/feedbacks".format(version_id), data)


def update_feedback(
    feedback_id: str,
    status: Optional[str] = None,
    decision: Optional[str] = None,
    root_cause: Optional[str] = None,
    fix_plan: Optional[str] = None,
) -> dict:
    """更新反馈(状态 / 决策 / 根因)— Phase 8 决策闭环"""
    data = {}
    if status:
        data["status"] = status
    if decision:
        data["decision"] = decision
    if root_cause:
        data["root_cause"] = root_cause
    if fix_plan:
        data["fix_plan"] = fix_plan
    return api_patch(f"/api/v1/feedbacks/{feedback_id}", data)