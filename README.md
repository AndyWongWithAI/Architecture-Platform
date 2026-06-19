# Architecture Platform

CLAUDE.md 提到的"架构平台"——独立组件登记 / 复用 / 反馈系统。

**Status**: 🚧 设计阶段,代码未启动
**Priority**: 低 —— 等 SDLC 跑通 1 个完整项目后再启动 Phase 0
**Owner**: AndyWongWithAI

## 文档

- **[docs/DESIGN.md](docs/DESIGN.md)** — 完整设计方案(13 章节 + 10 决策 + 评审响应)

## 三个核心原则(对应 CLAUDE.md)

| 原则 | 落点 |
|------|------|
| **资产原则** | Component + Version + Deployment 三表关联,生产部署必登记 |
| **反馈原则** | Feedback 表 + decision 字段(optimize / fork_new / keep_as_is)形成闭环 |
| **复用原则** | L0-L3 分层 + 原子/复合组件 + GitHub Packages 发包 + `arch use/tree/outdated` 命令 |

## 10 个核心决策(2026-06-20)

| # | 决策 | 选择 |
|---|------|------|
| 1 | 技术栈 | FastAPI + SQLite + Python |
| 2 | Web UI | HTMX + Jinja2(轻量) |
| 3 | GitHub Issues | 不启用,架构平台完全替代 |
| 4 | 部署位置 | #1 华为云 跟其他生产服务并列 |
| 5 | CLI 分发 | `pip install arch-platform-cli` |
| 6 | 原子性建模 | Boolean `atomic` + `composed_of` 自引用 |
| 7 | 复用核心载体 | GitHub Packages 包仓库 |
| 8 | 包命名规范 | `arch-component-<kebab>` / `@andywong/<kebab>` |
| 9 | 默认版本约束 | caret `^1.2.0`(minor+patch 自动,major 不自动) |
| 10 | 升级自动化 | patch 自动 + minor 需 review + major 必人工 |

## 触发启动条件

✅ 等 SDLC 至少跑通 1 个完整项目后启动 Phase 0
🚫 当前不动手

## 关联

- 设计依据:CLAUDE.md(架构 / 复用 / 资产 / 反馈 / 一致性 / 定位稳定性 6 原则)
- 依赖基础设施:[[local-machine]] / [[server]] / [[server-2]] / [[server-3]]
- SDLC 集成:3 个登记节点(Phase 2 设计定稿 / Phase 6 部署上线 / Phase 8 Bug 反馈)