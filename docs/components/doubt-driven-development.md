---
name: doubt-driven-development
title: Doubt-Driven Development 验证模式
positioning: "AI 可执行的对抗式审查模式:每个非平凡决策先 CLAIM,再 EXTRACT,再 DOUBT,再 RECONCILE,STOP。架构平台原生支持,完整 SOP 存 Version.design_doc。"
layer: L2_capability
category: util
scope: lib
atomic: true
composed_of: []
tags: [verification, ai-skill, methodology, claim-artifact-contract, review, doubt]
language: markdown
package_name: ""
install_command: ""
usage_example: "mcp__arch-platform__run_doubt_cycle(claim, artifact, contract)"
repo_url: "https://github.com/addyosmani/agent-skills"
is_asset: true
distribution_form: skill
interface_contract: |
  Inputs:
    claim:    string (2-3 行声明)
    artifact: string (代码/决策/断言,贴代码或文件路径)
    contract: string (期望行为/验收标准)
  Outputs:
    verdict:    string (pass | fail | needs_more_evidence)
    score:      float  (0.0-1.0)
    findings:   list   (分类: actionable | trade-off | noise | contract-misread)
    next_step:  string (建议下一步动作)
  Cycle: 5 步(CLAIM → EXTRACT → DOUBT → RECONCILE → STOP),最多 3 轮
knowledge_artifact: true
status: stable
---

# Doubt-Driven Development(架构平台沉淀版)

> 完整 243 行 SOP 存 Version.design_doc,本地备份在
> `~/.claude/skills/doubt-driven-development/SKILL.md`(Claude Code 自动加载)。
>
> 来源:addyosmani/agent-skills 公开仓库(2026-06-21 引入 arch-platform)

## 为什么需要

LLM 在长会话中会累积 context pollution,让"假设"变成"事实"而无人察觉。
对抗式审查是显式化的防御机制——把"决策 + 证据"分离,让 fresh-context reviewer 找茬。

## 5 步法概览

| Step | 动作 |
|---|---|
| 1. CLAIM | 2-3 行写清楚"决策 + 为什么重要" |
| 2. EXTRACT | 抽出 artifact + contract,剥离自己的推理 |
| 3. DOUBT | 召唤 fresh-context reviewer,只传 artifact + contract(不传 CLAIM)|
| 4. RECONCILE | 分类 finding: actionable / trade-off / noise / contract-misread |
| 5. STOP | 3 条件:trivial finding / 3 轮 / 用户 ship it |

## 触发条件(满足任一)

- 引入/修改分支逻辑
- 跨模块/跨服务边界
- 正确性依赖未来读者看不到的上下文
- **不可逆影响**(生产部署、数据迁移、公网 API 变更)
- 跨云架构决策

## 不触发条件(避免过度)

- 纯机械操作(rename / format / 文件移动)
- 清晰的、无歧义的用户指令
- 一行修改且正确性明显
- 用户明确说"快速做"

## 4 入口

- **API**:`POST /api/v1/doubt/cycle`(返回 verdict + cycle_id)
- **CLI**:`arch doubt cycle --claim <text> --artifact <file> --contract <file>`
- **MCP**:`mcp__arch-platform__run_doubt_cycle(claim, artifact, contract)`
- **Web**:`https://arch.intelab.cn/doubt/new`

## 与 CLAUDE.md 的对应

- 高内聚低耦合:每个 cycle 独立,不与其他 review 流程耦合
- 分层原则:DoubtCycle(数据层) / routes(API 层) / MCP(协议层)
- 资产原则:完整 SOP 存 Version.design_doc,version 化更新
- 反馈原则:verdict=fail 的 cycle 自动建议 `arch feedback create`
- 质量>效率:并行 3 个 reviewer persona review 同一个 artifact
- 定位稳定性:本组件定位"对抗式审查 SOP 引擎",不变成万能验证器
