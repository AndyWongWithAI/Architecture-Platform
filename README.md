# Architecture Platform

CLAUDE.md 提到的"架构平台"——独立组件登记 / 复用 / 反馈系统。

**Status**: ✅ **Phase 0-5 全部完成** / 14 个组件已登记 / 公网 HTTPS 已部署
**公网**: https://arch.intelab.cn
**Owner**: AndyWongWithAI

## 🎯 一句话价值

**让"是否复用现有组件"成为开发前默认动作**——CLAUDE.md 复用原则的工具载体。

## ✨ 已完成 Phase(2026-06-20)

| Phase | 状态 | 产物 |
|-------|------|------|
| **Phase 0** | ✅ | OpenAPI 3.1 spec + ER 图 + 数据字典 |
| **Phase 1** | ✅ | FastAPI + SQLite 后端,15 个 endpoints,40 个 pytest 全过 |
| **Phase 2** | ✅ | `arch-platform-cli 0.2.0`,12 个子命令 |
| **Phase 3** | ✅ | 3 个 GitHub Action(`@v1.0.0`) |
| **Phase 4** | ✅ | 8 页面 Web UI + 反馈看板 PATCH 代理 |
| **Phase 5** | ✅ | 数据导入(14 组件) + GitHub Issues 关闭 + SDLC 端到端验证 |

## 🚀 快速使用

### Web UI(浏览器)
打开 https://arch.intelab.cn:
- 🏛️ **总览** `/` — 组件/反馈/部署统计 + 分层 + 最近活动
- 🔧 **组件列表** `/components` — 14 个组件,过滤 layer/category/asset
- 📄 **组件详情** `/components/{name}` — 元数据 + 版本历史 + 反馈
- 🌲 **依赖树** `/components/{name}/tree` — 递归展开
- 📋 **反馈看板** `/feedbacks` — Kanban + PATCH(无需登录)
- 🖥️ **部署地图** `/deployments`
- 🔍 **搜索** 顶栏搜索框

### CLI(开发者本地)

```bash
pip install arch-platform-cli

arch config set-url https://arch.intelab.cn
arch health
arch search redis
arch use docker
arch tree intelab.cn-website
arch component list --layer L1_platform
```

### GitHub Action(CI/CD)

```yaml
- uses: AndyWongWithAI/Architecture-Platform/.github/actions/arch-platform-register@v1
  with:
    arch-platform-url: ${{ secrets.ARCH_PLATFORM_URL }}
    api-key: ${{ secrets.ARCH_PLATFORM_API_KEY }}
    component: my-service
    host: huawei-1
    env: prod
```

## 📊 当前数据(2026-06-20)

| 指标 | 数量 |
|------|------|
| 总组件 | 14(L0×2 + L1×9 + L2×2 + L3×1) |
| 真资产 | 12 |
| 项目级 | 2(minimax-proxy + intelab.cn-website) |
| 反馈 | 3(已闭环 1 + 待处理 2) |
| 部署 | 3 条(prod + dev on huawei-1) |
| 测试 | 40 个 pytest(原 21 + 新 19) |

## 三个核心原则(对应 CLAUDE.md)

| 原则 | 落点 |
|------|------|
| **资产原则** | `is_asset` + `distribution_form`(11 个 enum)+ `interface_contract` + `knowledge_artifact` 四维判定 |
| **反馈原则** | Feedback + `decision` 字段(optimize / fork_new / keep_as_is / reassess_form)形成闭环 |
| **复用原则** | L0-L3 分层 + 原子/复合 + `arch search/use/tree/outdated` 命令 + GitHub Packages 发包 |

## 11 个核心决策(2026-06-20)

| # | 决策 | 选择 |
|---|------|------|
| 1 | 技术栈 | FastAPI + SQLite + Python |
| 2 | Web UI | HTMX + Jinja2(轻量) |
| 3 | GitHub Issues | 不启用,架构平台完全替代(✅ 已关) |
| 4 | 部署位置 | #1 华为云 跟其他生产服务并列 |
| 5 | CLI 分发 | `pip install arch-platform-cli` |
| 6 | 原子性建模 | Boolean `atomic` + `composed_of` 自引用 |
| 7 | 复用核心载体 | GitHub Packages 包仓库 |
| 8 | 包命名规范 | `arch-component-<kebab>` / `@andywong/<kebab>` |
| 9 | 默认版本约束 | caret `^1.2.0`(minor+patch 自动,major 不自动) |
| 10 | 升级自动化 | patch 自动 + minor 需 review + major 必人工 |
| 11 | 开发模式 | L0/L1/L2 **资产驱动**(登记后才动手),L3 项目驱动 |

## 触发启动准则(2026-06-20 修订)

- ✅ **Phase 0 立刻启动**:纯文档(OpenAPI spec + ER 图 + 数据字典),0.5 周,投入产出比最高
- ⏳ **Phase 1+ 等需求**:有真实组件要登记时启动,避免空数据库

启动顺序:Phase 0(0.5 周,纯文档)→ Phase 1(2 周 MVP 后端,等需求)→ Phase 2(1 周 CLI)→ Phase 3(0.5 周 GitHub Action)→ Phase 4(2 周 Web UI)→ Phase 5(0.5 周数据导入)。

## 关联

- 设计依据:CLAUDE.md(架构 / 复用 / 资产 / 反馈 / 一致性 / 定位稳定性 6 原则)
- 依赖基础设施:[[local-machine]] / [[server]] / [[server-2]] / [[server-3]]
- SDLC 集成:3 个登记节点(Phase 2 设计定稿 / Phase 6 部署上线 / Phase 8 Bug 反馈)