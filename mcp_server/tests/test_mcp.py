"""MCP Server 端到端测试 — 用 MCP Python SDK 起 client 连接 stdio server

每个测试独立起 server(慢但稳定,避免 fixture 跨测试 scope 问题)
"""
import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

# MCP SDK
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


MCP_SERVER_BIN = "/home/hq/.local/bin/arch-mcp-server"
API_BASE = os.environ.get("ARCH_MCP_TEST_URL", "https://arch.intelab.cn")
_REQ_LOCAL = "127.0.0.1" in API_BASE or "localhost" in API_BASE


async def _call_tool(tool_name: str, arguments: dict):
    """独立启 server + 调一个 tool,返回 dict"""
    env = os.environ.copy()
    env["ARCH_PLATFORM_URL"] = API_BASE
    env["ARCH_PLATFORM_API_KEY"] = ""  # 开放模式

    params = StdioServerParameters(command=MCP_SERVER_BIN, env=env, args=[])
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(tool_name, arguments)
    return json.loads(result.content[0].text)


async def _list_tools():
    """独立启 server + 列出 tools,返回 names 列表"""
    env = os.environ.copy()
    env["ARCH_PLATFORM_URL"] = API_BASE
    env["ARCH_PLATFORM_API_KEY"] = ""

    params = StdioServerParameters(command=MCP_SERVER_BIN, env=env, args=[])
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
    return [t.name for t in tools.tools]


# ——— Tests ———

@pytest.mark.asyncio
async def test_list_tools():
    """MCP Server 应暴露 16 个 tools(12 原 + 4 requirement Phase 1.2)"""
    names = sorted(await _list_tools())
    print(f"\n  注册的 tools: {names}")

    expected = [
        # 原 12
        "create_component", "create_feedback",
        "get_component", "list_components",
        "list_deployments", "list_feedbacks",
        "list_versions", "register_deployment",
        "search_components", "tree_component",
        "update_feedback", "use_component",
        # Phase 1.2 新增 4
        "create_requirement", "get_requirement",
        "list_requirements", "update_requirement",
    ]
    for t in expected:
        assert t in names, f"missing tool: {t}"
    assert len(names) == 16, f"expected 16 tools, got {len(names)}: {names}"


@pytest.mark.asyncio
async def test_list_components():
    """list_components 应返回 14 个组件"""
    data = await _call_tool("list_components", {"limit": 50})
    assert "items" in data
    assert data["total"] >= 14, f"expected ≥14, got {data['total']}"


@pytest.mark.asyncio
async def test_get_component():
    """get_component docker 应返回完整详情"""
    data = await _call_tool("get_component", {"name": "docker"})
    assert data["name"] == "docker"
    assert data["layer"] == "L0_infrastructure"


@pytest.mark.asyncio
async def test_use_component():
    """use_component 应返回 install_command"""
    data = await _call_tool("use_component", {"name": "docker"})
    assert "install_command" in data


@pytest.mark.asyncio
async def test_search_components():
    """search_components 跨实体"""
    data = await _call_tool("search_components", {"query": "docker"})
    comp_names = [c["name"] for c in data.get("components", [])]
    assert "docker" in comp_names


@pytest.mark.asyncio
async def test_tree_component():
    """tree_component 递归展开"""
    data = await _call_tool("tree_component", {"name": "intelab.cn-website"})
    assert "children" in data
    child_names = [c["component"]["name"] for c in data["children"]]
    assert "nginx" in child_names
    assert "certbot" in child_names


@pytest.mark.asyncio
async def test_list_deployments():
    """list_deployments"""
    data = await _call_tool("list_deployments", {"limit": 20})
    assert "items" in data


@pytest.mark.asyncio
async def test_list_feedbacks():
    """list_feedbacks"""
    data = await _call_tool("list_feedbacks", {"limit": 20})
    assert "items" in data


@pytest.mark.asyncio
async def test_create_component_e2e():
    """端到端:create_component via MCP"""
    # FB-5 修复:用时间戳生成唯一 name,避免跨测试运行累积
    import time
    unique_name = f"mcp-test-cache-{int(time.time())}"

    data = await _call_tool("create_component", {
        "name": unique_name,
        "title": "MCP Test Cache",
        "positioning": "MCP Server 端到端测试用的临时缓存组件,测试后清理",
        "category": "cache",
        "scope": "infra",
        "layer": "L1_platform",
        "is_asset": True,
        "distribution_form": "package",
    })
    assert data.get("name") == unique_name, f"创建失败:{data}"
    print(f"\n  ✓ MCP create_component 成功:{data['name']}")

    # FB-5 修复:清理走 API 闭环(原 SSH+sqlite3 被自动模式拦)
    # PATCH status=archived(架构平台软删除模式)
    import httpx
    PATCH_URL = f"{API_BASE}/api/v1/components/{unique_name}"
    resp = httpx.patch(
        PATCH_URL,
        json={"status": "archived"},
        headers={"X-API-Key": ""},  # 开放模式
        timeout=10.0,
    )
    if resp.status_code == 200:
        print(f"  ✓ 清理成功:status=archived (HTTP {resp.status_code})")
    else:
        print(f"  ✗ 清理失败:HTTP {resp.status_code} {resp.text[:80]}")


@pytest.mark.asyncio
async def test_unknown_tool():
    """调用不存在的 tool 应返回 error,不抛异常"""
    data = await _call_tool("nonexistent_tool_xyz", {})
    assert "error" in data


# ===== Phase 1.2 Requirement 模块(2026-06-21)=====


@pytest.mark.asyncio
async def test_list_requirements():
    """list_requirements 端到端"""
    if not _REQ_LOCAL:
        pytest.skip("requirement endpoint 未部署到生产,跳过")
    data = await _call_tool("list_requirements", {"limit": 20})
    assert "items" in data
    assert "total" in data
    print(f"  → MCP list_requirements: total={data['total']}")


@pytest.mark.asyncio
async def test_create_requirement():
    """create_requirement 端到端(平铺)"""
    if not _REQ_LOCAL:
        pytest.skip("requirement endpoint 未部署到生产,跳过")
    data = await _call_tool("create_requirement", {
        "title": "MCP 测试创建需求-不应保留-test-only-link",
        "type": "tech_debt",
        "priority": "P3",
        "proposer": "mcp-test",
    })
    assert data.get("title", "").startswith("MCP 测试")
    assert data["status"] == "draft"
    assert data["priority"] == "P3"
    print(f"  → MCP create_requirement: {data['id'][:8]}")


@pytest.mark.asyncio
async def test_get_requirement():
    """get_requirement 端到端"""
    if not _REQ_LOCAL:
        pytest.skip("requirement endpoint 未部署到生产,跳过")
    created = await _call_tool("create_requirement", {
        "title": "MCP 测试 get-不应保留-test-only-link",
        "type": "new_feature",
        "priority": "P2",
    })
    req_id = created["id"]
    data = await _call_tool("get_requirement", {"requirement_id": req_id})
    assert data["id"] == req_id
    assert data["priority"] == "P2"
    print(f"  → MCP get_requirement: {data['id'][:8]}")


@pytest.mark.asyncio
async def test_update_requirement_status():
    """update_requirement 状态流转"""
    if not _REQ_LOCAL:
        pytest.skip("requirement endpoint 未部署到生产,跳过")
    created = await _call_tool("create_requirement", {
        "title": "MCP 测试 update-status-不应保留-test-only-link",
        "type": "new_feature",
        "priority": "P2",
    })
    req_id = created["id"]
    data = await _call_tool("update_requirement", {
        "requirement_id": req_id,
        "status": "triaged",
        "assignee": "andy",
    })
    assert data["status"] == "triaged"
    assert data["assignee"] == "andy"
    assert data["decided_at"] is not None
    print(f"  → MCP update_requirement: status=triaged, decided_at 自动设置 ✓")