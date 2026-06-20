"""arch-platform MCP Server — 让 AI 助手(Claude Code / Cursor 等)直接调架构平台 API

通过 Model Context Protocol(stdio)暴露 11 个 tools:
- 读:list_components / get_component / search_components / use_component /
     tree_component / list_versions / get_version / list_deployments /
     list_feedbacks
- 写(需要服务器持 API Key):create_component / register_deployment /
     create_feedback / update_feedback

启动:
  arch-mcp-server
  或:python -m arch_mcp

Claude Code 接入(在项目 .mcp.json):
  {
    "mcpServers": {
      "arch-platform": {
        "command": "arch-mcp-server",
        "env": {
          "ARCH_PLATFORM_URL": "https://arch.intelab.cn",
          "ARCH_PLATFORM_API_KEY": "sk-xxx"
        }
      }
    }
  }
"""