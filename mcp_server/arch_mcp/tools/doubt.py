"""MCP tools: doubt-driven-development 4 个工具(2026-06-21 新增)

对齐 feedbacks.py 的实现风格:Tool 定义在 server.py,
实现函数在本文件。
"""
from __future__ import annotations

from ..client import api_get, api_post, api_patch


async def run_doubt_cycle(
    claim: str,
    artifact: str,
    contract: str,
    component: str = "",
    created_by: str = "mcp",
) -> dict:
    """开一个 doubt cycle(Step 1 CLAIM + Step 2 EXTRACT)

    Returns: cycle dict(id, verdict, findings[], etc.)
    """
    payload = {
        "claim": claim,
        "artifact": artifact,
        "contract": contract,
        "created_by": created_by,
    }
    if component:
        payload["component_id"] = component
    return api_post("/api/v1/doubt/cycle", payload)


async def get_doubt_cycle(cycle_id: str) -> dict:
    """查 cycle(含 findings)"""
    return api_get(f"/api/v1/doubt/cycles/{cycle_id}")


async def add_doubt_finding(
    cycle_id: str,
    category: str,
    severity: str,
    description: str,
) -> dict:
    """RECONCILE:加 finding(classify: actionable / trade-off / noise / contract-misread)"""
    return api_post(
        f"/api/v1/doubt/cycles/{cycle_id}/findings",
        {"category": category, "severity": severity, "description": description},
    )


async def stop_doubt_cycle(cycle_id: str, reason: str) -> dict:
    """STOP:用户主动 ship"""
    return api_post(f"/api/v1/doubt/cycles/{cycle_id}/stop", {"reason": reason})
