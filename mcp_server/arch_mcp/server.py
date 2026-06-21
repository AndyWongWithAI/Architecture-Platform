"""MCP Server 入口 — 把 tools 注册给 AI 助手

使用 Model Context Protocol Python SDK:
  https://github.com/modelcontextprotocol/python-sdk

传输:stdio(Claude Code / Cursor 等本地 AI 助手默认)
"""
from __future__ import annotations

import os

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from . import tools
from .client import health as api_health


# ——— MCP Server 实例 ———

app = Server("arch-platform-mcp")


# ——— Tool 定义(给 AI 看 schema)———

TOOL_DEFINITIONS = [
    # —— Components ——
    Tool(
        name="list_components",
        description="列出架构平台登记的组件。支持按 layer(L0_infrastructure/L1_platform/L2_capability/L3_application)、category、is_asset(真资产/项目级)、q(关键字)过滤。",
        inputSchema={
            "type": "object",
            "properties": {
                "layer": {"type": "string", "description": "按层级过滤,如 L1_platform"},
                "category": {"type": "string", "description": "按分类过滤,如 auth/db/cache/deploy"},
                "is_asset": {"type": "boolean", "description": "是否真资产"},
                "q": {"type": "string", "description": "关键字搜索"},
                "limit": {"type": "integer", "description": "返回数量限制", "default": 50},
            },
        },
    ),
    Tool(
        name="get_component",
        description="按 name 取组件的完整详情,含版本列表和元数据(title/positioning/layer/install_command 等)。",
        inputSchema={
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "组件名,kebab-case,如 user-auth-jwt"},
            },
            "required": ["name"],
        },
    ),
    Tool(
        name="use_component",
        description="取组件的 install_command + usage_example + current_version。LLM 写代码时调用这个知道'怎么用这个组件'。",
        inputSchema={
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "组件名"},
            },
            "required": ["name"],
        },
    ),
    Tool(
        name="tree_component",
        description="展开组件的 composed_of 依赖树(递归到子组件)。",
        inputSchema={
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "组件名"},
                "max_depth": {"type": "integer", "description": "最大深度", "default": 5},
            },
            "required": ["name"],
        },
    ),
    Tool(
        name="create_component",
        description="登记新组件到架构平台(Phase 2 设计定稿)。is_asset=true 必须填 distribution_form。",
        inputSchema={
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "title": {"type": "string"},
                "positioning": {"type": "string", "description": "定位描述,必须稳定(10+ 字符)"},
                "category": {"type": "string", "enum": ["auth", "db", "cache", "queue", "log", "deploy", "monitor", "ui", "util", "other"]},
                "layer": {"type": "string", "enum": ["L0_infrastructure", "L1_platform", "L2_capability", "L3_application"]},
                "scope": {"type": "string", "enum": ["app", "infra", "lib", "tool"], "default": "lib"},
                "is_asset": {"type": "boolean", "default": True},
                "distribution_form": {"type": "string", "enum": ["package", "container", "binary", "source", "http_api", "schema", "dataset", "config_template", "iac", "skill", "tool"]},
                "interface_contract": {"type": "string"},
                "knowledge_artifact": {"type": "boolean", "default": False},
                "tags": {"type": "array", "items": {"type": "string"}},
                "repo_url": {"type": "string"},
                "package_name": {"type": "string"},
                "install_command": {"type": "string"},
                "usage_example": {"type": "string"},
            },
            "required": ["name", "title", "positioning", "category", "layer"],
        },
    ),

    # —— Search ——
    Tool(
        name="search_components",
        description="跨实体关键字搜索(components / versions / feedbacks)。用户问'有没有 X 相关的'时调用。",
        inputSchema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "搜索关键字"},
                "limit": {"type": "integer", "default": 20},
            },
            "required": ["query"],
        },
    ),

    # —— Versions + Deployments ——
    Tool(
        name="list_versions",
        description="列出组件的所有版本(Phase 2 设计定稿产物)。",
        inputSchema={
            "type": "object",
            "properties": {
                "component_name": {"type": "string"},
            },
            "required": ["component_name"],
        },
    ),
    Tool(
        name="list_deployments",
        description="列出部署历史(Phase 6 部署登记产物)。可按 host/env 过滤。",
        inputSchema={
            "type": "object",
            "properties": {
                "host": {"type": "string", "description": "主机标识,如 huawei-1"},
                "env": {"type": "string", "enum": ["dev", "staging", "prod"]},
                "limit": {"type": "integer", "default": 50},
            },
        },
    ),
    Tool(
        name="register_deployment",
        description="登记部署(Phase 6)。需要 version_id(通过 get_component → current_version_id 拿)。",
        inputSchema={
            "type": "object",
            "properties": {
                "version_id": {"type": "string"},
                "env": {"type": "string", "enum": ["dev", "staging", "prod"]},
                "host": {"type": "string"},
                "deploy_path": {"type": "string"},
                "config_hash": {"type": "string"},
                "lockfile_hash": {"type": "string"},
                "build_reproducible": {"type": "boolean", "default": True},
                "deployed_by": {"type": "string", "default": "mcp"},
                "resolved_versions": {"type": "object", "description": "{组件名: 版本号}"},
            },
            "required": ["version_id", "env", "host"],
        },
    ),

    # —— Feedbacks ——
    Tool(
        name="list_feedbacks",
        description="列出 Bug 反馈(Phase 8)。可按 status(open/triaged/fixing/fixed/wontfix)/severity 过滤。",
        inputSchema={
            "type": "object",
            "properties": {
                "status": {"type": "string"},
                "severity": {"type": "string"},
                "limit": {"type": "integer", "default": 50},
            },
        },
    ),
    Tool(
        name="create_feedback",
        description="登记新 Bug 反馈(Phase 8)。需要 version_id。",
        inputSchema={
            "type": "object",
            "properties": {
                "version_id": {"type": "string"},
                "summary": {"type": "string"},
                "severity": {"type": "string", "enum": ["low", "medium", "high", "critical"], "default": "medium"},
                "root_cause": {"type": "string"},
                "fix_plan": {"type": "string"},
                "reporter": {"type": "string", "default": "mcp"},
                "reused_in": {"type": "array", "items": {"type": "string"}, "description": "影响面项目名"},
            },
            "required": ["version_id", "summary"],
        },
    ),
    Tool(
        name="update_feedback",
        description="更新反馈状态/决策(Phase 8 闭环)。转 fixed/wontfix 前必须填 decision。",
        inputSchema={
            "type": "object",
            "properties": {
                "feedback_id": {"type": "string"},
                "status": {"type": "string", "enum": ["open", "triaged", "fixing", "fixed", "wontfix"]},
                "decision": {"type": "string", "enum": ["optimize", "fork_new", "keep_as_is", "reassess_form"]},
                "root_cause": {"type": "string"},
                "fix_plan": {"type": "string"},
            },
            "required": ["feedback_id"],
        },
    ),
    # —— Requirements (Phase 1.2 2026-06-21)——
    Tool(
        name="list_requirements",
        description="列出需求(Phase 1 需求登记)。可按 status/priority/type/component_id/assignee 过滤。",
        inputSchema={
            "type": "object",
            "properties": {
                "status": {"type": "string", "enum": ["draft", "triaged", "scheduled", "in_progress", "implemented", "verified", "rejected", "cancelled"]},
                "priority": {"type": "string", "enum": ["P0", "P1", "P2", "P3"]},
                "type": {"type": "string", "enum": ["new_feature", "bug_fix", "refactor", "optimization", "compliance", "tech_debt"]},
                "assignee": {"type": "string"},
                "component_id": {"type": "string"},
                "include_archived": {"type": "boolean", "default": False},
                "limit": {"type": "integer", "default": 50},
            },
        },
    ),
    Tool(
        name="create_requirement",
        description="登记新需求(Phase 1 需求登记)。component_id 可选——不传则创建无组件归口的需求(合规/流程类)。",
        inputSchema={
            "type": "object",
            "properties": {
                "component_id": {"type": "string", "description": "关联组件 id 或 name(嵌套入口)"},
                "title": {"type": "string", "description": "需求标题(20-200 字符)"},
                "type": {"type": "string", "enum": ["new_feature", "bug_fix", "refactor", "optimization", "compliance", "tech_debt"]},
                "priority": {"type": "string", "enum": ["P0", "P1", "P2", "P3"], "default": "P2"},
                "user_story": {"type": "string"},
                "acceptance_criteria": {"type": "array", "items": {"type": "object", "properties": {"given": {"type": "string"}, "when": {"type": "string"}, "then": {"type": "string"}}}},
                "nfr": {"type": "object", "additionalProperties": {"type": "string"}},
                "proposer": {"type": "string", "default": "mcp"},
                "assignee": {"type": "string"},
                "due_date": {"type": "string"},
                "tags": {"type": "array", "items": {"type": "string"}},
                "description": {"type": "string"},
            },
            "required": ["title", "type"],
        },
    ),
    Tool(
        name="get_requirement",
        description="按 id 取需求详情。",
        inputSchema={
            "type": "object",
            "properties": {
                "requirement_id": {"type": "string"},
            },
            "required": ["requirement_id"],
        },
    ),
    Tool(
        name="update_requirement",
        description="更新需求(状态 / 优先级 / 负责人)。注意状态机校验:draft→triaged 必填 assignee;implemented→verified 要求 component 有 version;终态必填 description。",
        inputSchema={
            "type": "object",
            "properties": {
                "requirement_id": {"type": "string"},
                "status": {"type": "string", "enum": ["draft", "triaged", "scheduled", "in_progress", "implemented", "verified", "rejected", "cancelled"]},
                "priority": {"type": "string", "enum": ["P0", "P1", "P2", "P3"]},
                "assignee": {"type": "string"},
                "description": {"type": "string"},
                "due_date": {"type": "string"},
                "tags": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["requirement_id"],
        },
    ),
]


# ——— Tool 分发 ———

@app.list_tools()
async def list_tools() -> list[Tool]:
    return TOOL_DEFINITIONS


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """统一 tool 分发 + JSON 输出"""
    import json

    try:
        if name == "list_components":
            result = tools.components.list_components(
                layer=arguments.get("layer"),
                category=arguments.get("category"),
                is_asset=arguments.get("is_asset"),
                q=arguments.get("q"),
                limit=arguments.get("limit", 50),
            )
        elif name == "get_component":
            result = tools.components.get_component(arguments["name"])
        elif name == "use_component":
            result = tools.components.use_component(arguments["name"])
        elif name == "tree_component":
            result = tools.components.tree_component(
                arguments["name"],
                max_depth=arguments.get("max_depth", 5),
            )
        elif name == "create_component":
            result = tools.components.create_component(**arguments)
        elif name == "search_components":
            result = tools.search.search_components(
                arguments["query"],
                limit=arguments.get("limit", 20),
            )
        elif name == "list_versions":
            result = tools.deployments.list_versions(arguments["component_name"])
        elif name == "list_deployments":
            result = tools.deployments.list_deployments(
                host=arguments.get("host"),
                env=arguments.get("env"),
                limit=arguments.get("limit", 50),
            )
        elif name == "register_deployment":
            result = tools.deployments.register_deployment(**arguments)
        elif name == "list_feedbacks":
            result = tools.feedbacks.list_feedbacks(
                status=arguments.get("status"),
                severity=arguments.get("severity"),
                limit=arguments.get("limit", 50),
            )
        elif name == "create_feedback":
            result = tools.feedbacks.create_feedback(**arguments)
        elif name == "update_feedback":
            result = tools.feedbacks.update_feedback(**arguments)
        elif name == "list_requirements":
            result = tools.requirements.list_requirements(
                status=arguments.get("status"),
                priority=arguments.get("priority"),
                type=arguments.get("type"),
                assignee=arguments.get("assignee"),
                component_id=arguments.get("component_id"),
                include_archived=arguments.get("include_archived", False),
                limit=arguments.get("limit", 50),
            )
        elif name == "create_requirement":
            result = tools.requirements.create_requirement(**arguments)
        elif name == "get_requirement":
            result = tools.requirements.get_requirement(arguments["requirement_id"])
        elif name == "update_requirement":
            result = tools.requirements.update_requirement(**arguments)
        else:
            return [TextContent(type="text", text=json.dumps({"error": f"unknown tool: {name}"}, ensure_ascii=False))]

        # 输出 JSON(ensure_ascii=False 让中文可读)
        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]
    except Exception as e:
        return [TextContent(type="text", text=json.dumps({"error": str(e)}, ensure_ascii=False))]


# ——— Resource(可选)———

@app.list_resources()
async def list_resources() -> list:
    """暴露架构平台 server info 作为一个 resource"""
    return []


# ——— Main ———

async def main():
    """stdio 传输主循环"""
    async with stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            app.create_initialization_options(),
        )


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())