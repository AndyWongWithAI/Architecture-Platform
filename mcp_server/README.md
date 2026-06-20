# arch-platform MCP Server

> Architecture Platform MCP Server — 让 AI 助手(Claude Code / Cursor / 其他 MCP 客户端)直接调架构平台 API

通过 [Model Context Protocol](https://modelcontextprotocol.io/)(MCP)stdIO 通信,暴露 12 个 tools。
AI 助手无需知道 API Key(由 MCP Server 进程自己持 Key)。

## 安装

```bash
cd mcp_server/
pip install -e .

# 验证
arch-mcp-server
```

## 接入 Claude Code

在项目根目录创建 `.mcp.json`:

```json
{
  "mcpServers": {
    "arch-platform": {
      "command": "arch-mcp-server",
      "env": {
        "ARCH_PLATFORM_URL": "https://arch.intelab.cn",
        "ARCH_PLATFORM_API_KEY": "sk-xxx..."
      }
    }
  }
}
```

启动 Claude Code 时,会自动连接 MCP Server,AI 助手就能用 `arch_*` 工具。

## 暴露的 12 个 Tools

### 读工具(读操作,任何 AI 助手可用)

| Tool | 用途 |
|------|------|
| `list_components` | 列出组件,支持 layer/category/is_asset/q 过滤 |
| `get_component` | 按 name 取组件完整详情(含版本列表) |
| `use_component` | 取 install_command + usage_example(LLM 写代码时调用) |
| `tree_component` | 展开 composed_of 依赖树 |
| `search_components` | 跨实体搜索(components/versions/feedbacks) |
| `list_versions` | 列出组件的所有版本 |
| `list_deployments` | 列出部署历史 |
| `list_feedbacks` | 列出反馈 |

### 写工具(需要服务器持 API Key)

| Tool | 用途 | SDLC 节点 |
|------|------|----------|
| `create_component` | 登记新组件 | Phase 2 |
| `register_deployment` | 登记部署 | Phase 6 |
| `create_feedback` | 登记 Bug 反馈 | Phase 8 |
| `update_feedback` | 更新反馈状态/决策 | Phase 8 |

## 鉴权模式

```
┌─────────────────┐
│  AI 助手        │ 调用 list_components
│  (Claude Code)  │
└────────┬────────┘
         │ MCP(stdio)
         ▼
┌─────────────────┐
│  MCP Server     │ 转发请求
│  (本地进程)     │ + 加 X-API-Key(从 env 读)
└────────┬────────┘
         │ HTTPS
         ▼
┌─────────────────┐
│  arch-platform  │ 验证 API Key + 处理
│  (FastAPI)      │
└─────────────────┘
```

**AI 助手完全不需要知道 API Key**——MCP Server 进程从 env 注入。

## 使用场景示例

### 1. LLM 写代码前查"有没有现成的"

> 用户: 我要给新项目加个 redis 缓存
> Claude: 调用 `search_components("redis")` → 找到 redis-cache 组件
> Claude: 调用 `use_component("redis-cache")` → 拿到 install_command
> Claude: 给用户的方案:`pip install arch-component-redis-cache`

### 2. LLM 自动登记部署后的反馈

> 用户: (部署后)Loki 没抓到日志
> Claude: 调用 `get_component("loki")` → 拿到 current_version_id
> Claude: 调用 `create_feedback(version_id, summary="Loki 没抓到日志", severity=high)`
> Claude: 告诉用户反馈已登记,反馈 ID 是 xxx

### 3. LLM 帮用户做反馈决策

> 用户: (打开 Web UI 看板,反馈堆积在 Open 列)
> 用户在 chat 里问: "arch-platform 上 open 的高严重度反馈有哪些?"
> Claude: 调用 `list_feedbacks(status="open", severity="high")`
> Claude: 列出来 → 帮用户填决策 → 调用 `update_feedback(id, decision="optimize", status="triaged")`

## 手动测试(stdio JSON-RPC)

```bash
# 启动 server(从 stdin 读 JSON-RPC,stdout 输出)
cat > /tmp/mcp-session.json <<'EOF'
{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"0.1"}}}
{"jsonrpc":"2.0","method":"notifications/initialized","params":{}}
{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}
{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"list_components","arguments":{"limit":3}}}
EOF
ARCH_PLATFORM_URL="https://arch.intelab.cn" arch-mcp-server < /tmp/mcp-session.json
```

应看到:
- initialize 响应(serverInfo: arch-platform-mcp)
- tools/list 12 个 tools
- tools/call 返回 14 个组件的 JSON

## 测试

```bash
cd mcp_server/
pytest tests/ -v
```

10 个测试覆盖:
- list_tools(确认 12 个 tools 都注册)
- list_components / get_component / use_component / tree_component
- search_components / list_versions / list_deployments / list_feedbacks
- create_component 端到端(创建 + 清理)
- unknown_tool 错误处理

## 设计原则

| 原则 | 体现 |
|------|------|
| **薄封装** | MCP Server 是 thin wrapper,业务逻辑都在后端 API |
| **服务器代理** | AI 助手不需要知道 API Key,由 MCP Server 进程持有 |
| **fail-soft** | API 错误返回 dict 含 `error` 字段,不抛异常中断对话 |
| **JSON 输出** | 所有 tool 返回 JSON(ensure_ascii=False 中文可读) |
| **stdio** | 默认 stdio 传输,Claude Code 无需额外配置 |

## 关联

- 主项目:[Architecture-Platform](../README.md)
- CLI:[arch-platform-cli](../cli/)(开发者手敲命令用)
- 后端:[FastAPI 15 endpoints](../backend/)
- Web UI:[Phase 4 8 页面](../backend/app/templates/)
- GitHub Action:[Phase 3 3 actions](../.github/actions/)