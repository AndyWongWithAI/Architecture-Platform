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
    """MCP Server 应暴露 20 个 tools(12 原 + 4 requirement + 4 doubt)"""
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
        # Phase 0 新增 4(2026-06-21 doubt-driven-development)
        "run_doubt_cycle", "get_doubt_cycle",
        "add_doubt_finding", "stop_doubt_cycle",
    ]
    for t in expected:
        assert t in names, f"missing tool: {t}"
    assert len(names) == 20, f"expected 20 tools, got {len(names)}: {names}"


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


# ===== Phase 0 Doubt-Driven Development MCP(2026-06-21)====
# 4 个测试:run / get / add finding / stop 端到端

import httpx as _httpx
_base = os.environ.get("ARCH_MCP_TEST_URL", "https://arch.intelab.cn")
try:
    _probe = _httpx.get(f"{_base}/api/v1/components", timeout=3)
    _DOUBT_REACHABLE = _probe.status_code == 200
except Exception:
    _DOUBT_REACHABLE = False


@pytest.mark.asyncio
async def test_run_doubt_cycle():
    """run_doubt_cycle 创建 cycle,返回完整 dict"""
    if not _DOUBT_REACHABLE:
        pytest.skip("doubt endpoint 不可达,跳过")
    data = await _call_tool("run_doubt_cycle", {
        "claim": "MCP 测试创建 doubt cycle-不应保留-test-only-link",
        "artifact": "shutil.rmtree(path)",
        "contract": "deploy 必须保留 data/ backups/ .env 至少 10 字符",
        "component": "arch-platform-backend",
        "created_by": "mcp-test",
    })
    assert data.get("claim", "").startswith("MCP 测试")
    assert data["verdict"] is None
    assert data["cycle_count"] == 1
    assert data["max_cycles"] == 3
    assert data["stopped_at"] is None
    print(f"  → MCP run_doubt_cycle: {data['id'][:8]} cycle_count={data['cycle_count']}")


@pytest.mark.asyncio
async def test_get_doubt_cycle():
    """get_doubt_cycle 含 findings 列表"""
    if not _DOUBT_REACHABLE:
        pytest.skip("doubt endpoint 不可达,跳过")
    # 先建 cycle
    created = await _call_tool("run_doubt_cycle", {
        "claim": "MCP 测试 get_doubt_cycle-不应保留-test-only-link",
        "artifact": "code",
        "contract": "expected behavior per spec",
        "created_by": "mcp-test",
    })
    cycle_id = created["id"]
    # 加一个 finding
    await _call_tool("add_doubt_finding", {
        "cycle_id": cycle_id,
        "category": "actionable",
        "severity": "medium",
        "description": "MCP 测试 finding 描述至少 10 字符以上",
    })
    # get 应该能看到
    data = await _call_tool("get_doubt_cycle", {"cycle_id": cycle_id})
    assert data["id"] == cycle_id
    assert len(data["findings"]) >= 1
    assert data["findings"][0]["category"] == "actionable"
    print(f"  → MCP get_doubt_cycle: {cycle_id[:8]} 含 {len(data['findings'])} finding(s) ✓")


@pytest.mark.asyncio
async def test_add_doubt_finding():
    """add_doubt_finding 4 个 category 都可分类"""
    if not _DOUBT_REACHABLE:
        pytest.skip("doubt endpoint 不可达,跳过")
    created = await _call_tool("run_doubt_cycle", {
        "claim": "MCP 测试 add_doubt_finding-不应保留-test-only-link",
        "artifact": "code",
        "contract": "expected behavior per spec",
        "created_by": "mcp-test",
    })
    cycle_id = created["id"]
    cats = ["actionable", "trade_off", "noise", "contract_misread"]
    for cat in cats:
        data = await _call_tool("add_doubt_finding", {
            "cycle_id": cycle_id,
            "category": cat,
            "severity": "low",
            "description": f"MCP 4 类分类端到端测试 - {cat} 至少 10 字符",
        })
        assert data["category"] == cat
        assert data["severity"] == "low"
    # 验证 4 个都入库
    data = await _call_tool("get_doubt_cycle", {"cycle_id": cycle_id})
    assert len(data["findings"]) == 4
    print(f"  → MCP add_doubt_finding: 4 categories all classified ✓")


@pytest.mark.asyncio
async def test_stop_doubt_cycle():
    """stop_doubt_cycle 写 stopped_at + stopped_reason=user_stop: ..."""
    if not _DOUBT_REACHABLE:
        pytest.skip("doubt endpoint 不可达,跳过")
    created = await _call_tool("run_doubt_cycle", {
        "claim": "MCP 测试 stop_doubt_cycle-不应保留-test-only-link",
        "artifact": "code",
        "contract": "expected behavior per spec",
        "created_by": "mcp-test",
    })
    cycle_id = created["id"]
    data = await _call_tool("stop_doubt_cycle", {
        "cycle_id": cycle_id,
        "reason": "MCP test: evidence conclusive ship the fix",
    })
    assert data["id"] == cycle_id
    assert data["stopped_at"] is not None
    assert "user_stop" in data["stopped_reason"]
    assert "MCP test" in data["stopped_reason"]
    print(f"  → MCP stop_doubt_cycle: {cycle_id[:8]} stopped ✓")