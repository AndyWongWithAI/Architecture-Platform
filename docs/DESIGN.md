# 架构平台设计方案

## Context

CLAUDE.md 提到"架构平台"作为核心概念,是 SDLC **资产/反馈/复用**三条原则的落点。用户在 2026-06-20 已决策**自建后端服务**(优先级低,等 SDLC 跑通 1 个项目后启动),GitHub 仓库 `AndyWongWithAI/Architecture-Platform` 已创建(空、public、Issues 已开)。

本任务:**给出完整、可落地的设计方案**,作为后续实施的依据。

---

## 1. 目标与边界

### 1.1 要解决什么(5 个痛点)

| 痛点 | 架构平台解法 |
|------|------------|
| 重复造轮子 | 集中登记组件 + 检索 + 复用评估 |
| 组件资产流失 | 按"定位"登记,跟项目解耦,长期可追溯 |
| 生产版本混乱 | 版本/部署位置/配置哈希强关联 |
| Bug 反馈分散 | 结构化反馈 → 决策闭环(优化/新建/保持) |
| 设计意图丢失 | 设计定稿阶段登记意图 + 替代方案 |

### 1.2 不做(避免范围蔓延)

- ❌ 不做企业级 RBAC / 多租户 / SSO
- ❌ 不做实时协作 / 评论 / @ 提及
- ❌ 不做自动代码分析 / AST 抽取
- ❌ 不做微服务拆分(MVP 不引入 K8s)
- ❌ 不做国际化 i18n
- ❌ 不做复杂工作流引擎

### 1.3 成功标准

- 新项目启动时,`arch search <keyword>` 30 秒内找到相关组件
- 部署上线后,5 分钟内完成登记
- Bug 反馈,2 分钟内完成登记 + 形成决策记录

---

## 2. 数据模型

### 2.1 4 个核心实体

#### Component(组件)
```yaml
id: UUID (主键)
name: string (唯一, kebab-case,如 "user-auth-jwt")
title: string (人类可读)
category: enum [auth, db, cache, queue, log, deploy, monitor, ui, util, other]
status: enum [draft, stable, deprecated, archived]
positioning: text (定位描述,稳定不轻易变)
scope: enum [app, infra, lib, tool]
layer: enum [L0_infrastructure, L1_platform, L2_capability, L3_application]  # 分层(详见 2.4)
tags: string[]
repo_url: string
# —— 原子性与复用(详见 Section 11 / Section 12)——
atomic: boolean (默认 true;false = 由其他组件组合而成)
composed_of: list[{component_id: UUID, version_constraint: string}]  # SemVer 约束;仅 atomic=false 时填
language: enum [python, typescript, javascript, go, rust, shell, sql, other]
package_name: string (如 "arch-component-user-auth-jwt" / "@andywong/auth-jwt")
install_command: text (一行安装/拉取/调用命令,如 "pip install arch-component-user-auth-jwt")
usage_example: text (一行代码或配置示例)
current_version_id: UUID (FK → Version.id, 推荐版本指针,见 2.3 约束)
created_at / updated_at: timestamp
```

#### Version(版本)
```yaml
id: UUID
component_id: FK → Component.id
version: string (SemVer, 如 "1.2.0")
design_doc: text (Phase 2 设计定稿:意图 + 影响面 + 替代方案)
design_decided_at: timestamp
replaces_version: string | null
changelog: text
created_at: timestamp
```

#### Deployment(部署 — 原"依赖"实体升级版)
```yaml
id: UUID
version_id: FK → Version.id
env: enum [dev, staging, prod]
host: string (主机标识, 如 "alicloud-1")
deploy_path: string
config_hash: string (SHA256)
deployed_at: timestamp
deployed_by: string
rollback_to: string | null
```
> 说明:原"依赖"实体在 MVP 阶段合并到 Deployment(部署位置 + 配置哈希已隐含环境依赖)。如未来需要独立依赖图谱,再独立出来。

#### Feedback(反馈)
```yaml
id: UUID
version_id: FK → Version.id
reporter: string
bug_summary: text
root_cause: text (根因分析)
fix_plan: text (修复方案)
severity: enum [low, medium, high, critical]
status: enum [open, triaged, fixing, fixed, wontfix]
decision: enum [optimize, fork_new, keep_as_is] (反馈原则闭环)
reused_in_projects: list[string]  # 影响面:本反馈涉及哪些项目在使用(详见 Section 12.5 / Section 13.7)
decided_at: timestamp | null
created_at: timestamp
```

### 2.2 ER 关系

```
Component (1) ──< (N) Version (1) ──< (N) Deployment
   │                                │
   │ 自引用(composed_of)             └──< (N) Feedback
   │  复合组件引原子组件
   └────< (N) Component (composition 边,见 2.4 / Section 11)
```

### 2.3 7 个关键约束

| 约束 | 说明 |
|------|------|
| **定位稳定性** | Component.positioning 不可变,改定位 = 新组件 |
| **版本不可变** | Version 记录创建后字段不可改(只能新增下一版本) |
| **一组件一当前版本** | Component 用 `current_version_id` 指针指向推荐版本 |
| **反馈必决策** | Feedback.decision 在 status 流转到 fixed/wontfix 前必须填写 |
| **删除软化** | Component.status = archived 而非 DELETE |
| **原子性自洽** | `atomic=true` ⇒ `composed_of` 必空;`atomic=false` ⇒ `composed_of` 必非空且每个引用必须存在 |
| **复合无环 + 分层一致** | `composed_of` 形成的图必须无环;复合组件的子组件层号 ≤ 自己层号(L3 应用不能包含 L3 应用;L2 复合不能直接含 L3) |

### 2.4 组件分层(4 层架构,业界通用)

参考 DDD + Clean Architecture + Hexagonal 共识,采用 **L0-L3 四层架构**:

| 层级 | 名称 | 含义 | 例子 |
|------|------|------|------|
| **L0** | Infrastructure | 基础设施 | Docker / Linux / K8s / 网络 / DNS / 镜像仓库 |
| **L1** | Platform | 平台/中间件 | MySQL / Redis / Kafka / Nginx / Prometheus / GitHub Actions |
| **L2** | Capability | 可复用业务能力 | user-auth-jwt / payment-svc / order-mgmt / notification |
| **L3** | Application | 面向用户的应用 | 电商网站 / CRM / 内部工具 / CLI / API 服务 |

**为什么这 4 层**:
- ✅ **业界共识** — DDD、Clean Architecture、Hexagonal Architecture 都基于类似分层
- ✅ **相对稳定** — 不被具体技术栈影响(写"平台"不写"Redis",Redis 升级不影响层定义)
- ✅ **可表达复用关系** — L2 是核心复用层,新项目优先从这里找组件
- ✅ **可表达依赖方向** — 上层依赖下层,清晰可追溯

### 2.5 分层依赖关系

```
        L3 Application
              │ 依赖
        L2 Capability
              │ 依赖
        L1 Platform
              │ 依赖
        L0 Infrastructure
```

**依赖规则**(CLAUDE.md 高内聚低耦合 + 分层原则):
- ✅ **上层可依赖下层**(L3 → L2 → L1 → L0)
- ❌ **下层不可依赖上层**(L0 不能用 L3 的代码)
- ✅ **同层组件可互不依赖**(高内聚)
- ❌ **不允许跨层依赖**(L3 不能跳过 L2 直接用 L1,除非定义适配器接口)
- ❌ **不允许循环依赖**(CLAUDE.md 原则)

### 2.6 各层组件的特征

| 层 | 变更频率 | 复用度 | 运维负担 | 例子 |
|----|---------|--------|---------|------|
| **L0** | 极低(月/年级) | 跨业务 | 高(底层出问题影响大) | OS 镜像、Docker 引擎、内核 |
| **L1** | 低(季度级) | 跨业务 | 中(需要 HA / 监控) | 数据库、缓存、消息队列 |
| **L2** | 中(周/月级) | 跨项目 | 低(随项目部署) | 认证库、支付抽象层、通知 |
| **L3** | 高(天/周级) | 单项目 | 低 | 业务功能、UI 页面、CLI |

**CLAUDE.md 复用原则映射**:
- L0/L1 → 全局复用,变更慎重(影响所有上层)
- L2 → **跨项目复用,新项目优先从这里找组件**(架构平台核心价值)
- L3 → 项目内,不跨项目复用(登记主要是为了版本追溯)

### 2.7 索引策略

- `Component.name`(唯一索引)
- `Component.tags`(GIN 索引,PostgreSQL JSONB 数组搜索)
- `Component.category`(普通索引,分类筛选)
- `Component.layer`(普通索引,层级筛选) — **新增**
- `Component.layer + category`(复合索引,层级 + 分类联合筛选) — **新增**
- `Version.component_id`(普通索引)
- `Deployment.version_id`(普通索引)
- `Deployment.host + deployed_at DESC`(复合索引,查某主机部署历史)

---

## 3. 技术栈选型

**推荐:FastAPI + SQLite + Python**

理由(按权重):
1. **个人开发者 + 低优先级** → SQLite 单文件,零运维,备份 = `cp`
2. **Python 生态契合 SDLC** → GitHub Action / CLI 工具用同语言
3. **FastAPI 文档免费** → 自动 OpenAPI + Swagger UI
4. **AI 协作友好** → Pydantic 模型清晰,Claude 写代码类型提示明确
5. **演进路径清晰** → SQLite 撑不住时一行连接串切 PostgreSQL(SQLAlchemy 2.0 抽象)
6. **学习成本最低** → 启动最快

**版本**:Python 3.12+ / FastAPI 0.110+ / SQLAlchemy 2.0 async / Pydantic v2 / uvicorn / pytest

---

## 4. API 设计

### 4.1 REST 端点(15 个)

| 方法 | 路径 | 用途 | SDLC 节点 |
|------|------|------|----------|
| POST | `/api/v1/components` | 创建组件 | Phase 2 / 6 |
| GET | `/api/v1/components` | 列出/搜索组件 | 任意 |
| GET | `/api/v1/components/{id}` | 组件详情(含版本列表) | 任意 |
| PATCH | `/api/v1/components/{id}` | 更新元数据 | 任意 |
| POST | `/api/v1/components/{id}/versions` | 创建新版本 | Phase 2 |
| GET | `/api/v1/versions/{id}` | 版本详情 | 任意 |
| POST | `/api/v1/versions/{id}/deployments` | 登记部署 | Phase 6 |
| GET | `/api/v1/deployments` | 查询部署历史 | 任意 |
| POST | `/api/v1/versions/{id}/feedbacks` | 登记 Bug 反馈 | Phase 8 |
| PATCH | `/api/v1/feedbacks/{id}` | 更新反馈状态/决策 | Phase 8 |
| GET | `/api/v1/feedbacks?status=open` | 待处理反馈 | 任意 |
| GET | `/api/v1/search?q=...` | 全文搜索 | 任意 |
| GET | `/api/v1/components/{id}/tree` | 展开 composed_of 依赖树(含环/分层校验) | 任意 |
| GET | `/api/v1/components/{id}/usage` | 取出 install_command + usage_example + 当前版本 | 任意 |
| GET | `/healthz` | 健康检查 | 运维 |

### 4.2 核心 JSON 示例

**创建组件**:
```json
{
  "name": "user-auth-jwt",
  "title": "基于 JWT 的用户认证",
  "category": "auth",
  "scope": "lib",
  "positioning": "面向 Web 项目的无状态用户认证,支持刷新令牌",
  "tags": ["jwt", "refresh-token", "fastapi", "pydantic"],
  "repo_url": "https://github.com/AndyWongWithAI/user-auth-jwt"
}
```

**登记部署**:
```json
{
  "env": "prod",
  "host": "alicloud-1",
  "deploy_path": "/opt/services/auth",
  "config_hash": "sha256:abc123...",
  "deployed_by": "github-actions"
}
```

**登记反馈**:
```json
{
  "reporter": "andy",
  "bug_summary": "高并发下 refresh token 偶发 500",
  "root_cause": "竞态条件,旧 token 撤销与新 token 颁发未加锁",
  "fix_plan": "改为 Redis 分布式锁",
  "severity": "high"
}
```

### 4.3 认证

**MVP**:**静态 API Key**(`X-API-Key` 请求头)
- 写入类(POST/PATCH)需要 API Key
- 读取类(GET)可匿名(可对外暴露只读视图)
- Key 存服务器 `ARCH_PLATFORM_API_KEY` 环境变量 + 本地 `~/.config/arch-platform/credentials.toml`

**Web UI 鉴权策略**(单独约定):
- Web UI **只做只读**:浏览、搜索、查看依赖树、查看反馈看板
- 所有**写操作**(创建组件 / 版本 / 部署 / 反馈)**强制走 CLI**(自带 API Key)
- 内部部署(仅 `#1 localhost` 或内网):Web UI 不需要鉴权
- 公网暴露时:Web UI 加简单的 Cookie/Session 登录页(单密码 + Server-side Cookie);API Key 仍只用于 CLI

**演进**:GitHub OAuth(读权限) + API Key(写权限)

---

## 5. 前端 / UI

### 5.1 是否需要 Web UI

**需要 MVP 级 Web UI**。理由:
- 搜索/浏览是核心场景,CLI 体验差
- 反馈决策需要看上下文(版本历史、关联反馈),终端痛苦
- 数据可视化(分类树、版本时间线、部署地图)Web 表达比 CLI 强

**不做**:组件创建表单(CLI 写更顺)、实时通知、富文本编辑器

### 5.2 推荐技术栈:**HTMX + Jinja2 + FastAPI 模板**

- 服务端渲染,无前端构建
- 跟 FastAPI 同语言,无 JS 框架
- PicoCSS / Tailwind CDN 美化

### 5.3 关键页面(6 个)

| 页面 | 路径 |
|------|------|
| 首页 | `/` |
| 搜索 | `/search?q=...` |
| 组件详情 | `/components/{id}` |
| 反馈看板 | `/feedbacks` (Kanban) |
| 部署地图 | `/deployments` (主机 × 组件矩阵) |
| 健康检查 | `/healthz` |

---

## 6. 部署方案

### 6.1 部署位置:#1(生产主,推荐)

**关键问题**:候选 #3 定位"开发测试",架构平台是**生产级数据服务**,定位冲突。

**推荐方案**:**#1 跟其他生产服务并列部署**
- 路径:`/opt/services/arch-platform/`
- 端口:`127.0.0.1:8088`(Nginx 反代)
- 进程:`arch-platform.service`(systemd)
- 数据:`/opt/services/arch-platform/data/arch.db`(SQLite)
- 备份:`/opt/services/arch-platform/backups/` + rsync 到 #2

### 6.2 域名 / 访问

**MVP**:内部 `arch.local`(hosts / 内网 DNS),不暴露公网
**演进**:`platform.yourdomain.com` 子域 + Let's Encrypt + Cloudflare 代理

### 6.3 数据备份策略

| 类型 | 频率 | 保留 | 方式 |
|------|------|------|------|
| 全量备份 | 每日 03:00 | 30 天 | `sqlite3 arch.db ".backup backups/arch-YYYYMMDD.db"` (用 SQLite 原生 backup 命令,避免活跃写入事务损坏文件) |
| 异地备份 | 每日 04:00 | 永久 | rsync 到 #2(生产灾备) |
| 季度快照 | 每季度末 | 永久 | tar 打包,存 OSS |

每季度测试一次从 #2 恢复,验证可启动 + 数据完整。

---

## 7. 跟 GitHub 集成(迁移路径)

### 7.1 当前状态

- 仓库空 / Issues 已开 / Discussions 未开
- **暂代方案纸面上,执行尚未开始**

### 7.2 推荐:不启用 GitHub Issues,架构平台完全替代

理由:
- 架构平台字段更多(版本/部署/反馈/决策),Issues 装不下
- 双写易不一致,单数据源更可靠
- 社区参与用 Discussions,Issues 不是必需

### 7.3 迁移路径

| 阶段 | 架构平台 | GitHub |
|------|---------|--------|
| 当前(2026.06) | 未启动 | Issues 已开,未启用 |
| Phase 1-2(2026 Q3) | MVP 上线 | 关闭 Issues,启用 Discussions |
| 公开只读视图(2027 Q1) | 增加公开 API | 同步发布到 GitHub Pages |

### 7.4 Webhook

**MVP 不做**。Phase 3 可选:
- Release Webhook → 自动创建 Version 记录(从 `git tag` 读 SemVer)
- 不做 PR 触发自动登记(架构平台登记是设计/部署/反馈节点)

---

## 8. SDLC 集成点

### 8.1 3 个登记节点的具体实现

#### Phase 2 设计定稿(创建 Component + Version)

```bash
# WSL CLI
arch component create \
  --name "user-auth-jwt" \
  --title "基于 JWT 的用户认证" \
  --category "auth" \
  --positioning "面向 Web 项目的无状态用户认证,支持刷新令牌"

arch version create \
  --component "user-auth-jwt" \
  --version "1.2.0" \
  --design-doc-file ./docs/design/auth-1.2.0.md \
  --replaces "1.1.0"
```

#### Phase 6 部署上线(GitHub Actions 自动)

```yaml
- name: Register deployment
  uses: AndyWongWithAI/arch-platform-register@v1
  with:
    arch-platform-url: ${{ secrets.ARCH_PLATFORM_URL }}
    api-key: ${{ secrets.ARCH_PLATFORM_API_KEY }}
    component: ${{ env.SERVICE_NAME }}
    version: ${{ github.ref_name }}
    host: "alicloud-1"
    deploy-path: "/opt/services/${{ env.SERVICE_NAME }}"
    config-path: "./config.yaml"
```

#### Phase 8 Bug 反馈(CLI + Web UI 决策)

```bash
arch feedback create \
  --version "1.2.0" \
  --bug-summary "高并发下 refresh token 偶发 500" \
  --root-cause "竞态条件..." \
  --fix-plan "Redis 分布式锁..." \
  --severity high
# Web UI 看板填 decision: optimize / fork_new / keep_as_is
```

### 8.2 工具优先级

| 工具 | 优先级 |
|------|-------|
| **CLI 基础命令**(`arch component/version/feedback create` 等 CRUD) | P0(MVP 必做) |
| **CLI 高级命令**(`arch use` / `tree` / `outdated` / `upgrade` / `init` / `lock`) | P1(详见 Section 12.4 / Section 13.5) |
| **GitHub Action** | P0(跟 deploy 强绑定) |
| **Web UI** | P1(MVP 后期,只读 + 反馈看板) |
| **MCP Server**(可选) | P2(让 AI 助手代登记) |

### 8.3 `aip.json` 规范(可选)

每个组件仓库根目录放 `aip.json`,CLI `arch detect` 自动读取预填参数:

```json
{
  "name": "user-auth-jwt",
  "title": "基于 JWT 的用户认证",
  "category": "auth",
  "current_version": "1.2.0",
  "arch_platform_url": "https://arch.local/api/v1/components/abc-123"
}
```

---

## 9. 实施阶段(5 Phases,共 6.5 周)

| Phase | 周 | 目标 | 产出 |
|-------|----|----|------|
| **0** | 0.5 | 数据建模 + API 规范 | OpenAPI 3.1 spec + ER 图 + 数据字典 |
| **1** | 2 | MVP 后端 | FastAPI + SQLite + 13 端点 + 集成测试 + systemd |
| **2** | 1 | CLI 工具 | `arch` 命令行 + `aip.json` detect |
| **3** | 0.5 | GitHub Action | `arch-platform-register@v1` composite action |
| **4** | 2 | Web UI | HTMX + Jinja2 + 6 个关键页面 |
| **5** | 0.5 | 数据导入 + 启用 | 5-10 个真实组件批量入库 + 关闭 Issues |

**触发时机**:等 SDLC 至少跑通 1 个完整项目后再启动 Phase 0(目前先放着设计,不动手)。

---

## 10. 关键决策清单(等你拍板)

### 决策 1:技术栈最终选什么?

- ✅ **推荐**:FastAPI + SQLite + Python
- 备选:NestJS + PostgreSQL(若想长期演进、企业级)
- 备选:Go + SQLite(若想 CLI 单二进制极致简化)
- 🟢 **2026-06-20 决策:选择推荐项 — FastAPI + SQLite + Python**

### 决策 2:是否需要 MVP 级 Web UI?

- ✅ **推荐**:要(HTMX + Jinja2 轻量)
- 备选:只做 CLI + API(省事,但反馈决策体验差)
- 🟢 **2026-06-20 决策:选择推荐项 — 要(HTMX + Jinja2 轻量)**

### 决策 3:是否启用 GitHub Issues?

- ✅ **推荐**:不启用(架构平台完全替代)
- 备选:Issues 做公开反馈入口,架构平台只读导出一份
- 🟢 **2026-06-20 决策:选择推荐项 — 不启用(架构平台完全替代)**

### 决策 4:部署位置?

- ✅ **推荐**:#1(生产主,跟其他服务并列)
- 备选:新建最小 VPS(隔离干净)
- 备选:#3 改定位为"生产/开发两用"
- 🟢 **2026-06-20 决策:选择推荐项 — #1 华为云 跟其他生产服务并列**

### 决策 5:CLI 工具分发形式?

- ✅ **推荐**:`pip install arch-platform-cli`
- 备选:PyInstaller 单二进制
- 备选:Go 重写(语言统一 CLI + 后端)
- 🟢 **2026-06-20 决策:选择推荐项 — `pip install arch-platform-cli`**

### 决策 6:原子性如何建模?

- ✅ **推荐 A**:Boolean `atomic` + 自引用 `composed_of` 列表(扁平、查询简单,见 Section 11)
- 备选 B:独立 `Composition` 实体(`component_a is part of component_b, version_constraint`)——更规范化,支持复杂图查询
- 备选 C:不显式建模,从 `composed_of` 是否为空推断(入口处强制选填,默认 true)
- 🟢 **2026-06-20 决策:选择 A — Boolean `atomic` + `composed_of` 自引用列表**

### 决策 7:代码复用的核心载体是什么?

- ✅ **推荐 A**:**包仓库**(GitHub Packages 起步,L2 atomic 组件发 pip/npm/Go 包)
- 备选 B:Monorepo + workspace(所有原子组件在同一个仓库,跨项目引用靠相对路径)——上手快,演进难
- 备选 C:仅记录 `repo_url` + `git tag`,使用者手动 clone——最轻,但摩擦最大
- 备选 D:混合——L2 atomic 用包仓库;L2 composite service 用容器镜像;L0/L1 用 apt/docker run
- 🟢 **2026-06-20 决策:选择 A — 包仓库,GitHub Packages 起步**

### 决策 8:包命名规范?

- ✅ **推荐**:`arch-component-<kebab-name>`(Python)/ `@andywong/<kebab-name>`(Node)/ 仓库路径(Go)
- 备选:`@intelab/<kebab-name>`(用机构名,跨人复用更稳)
- 备选:不加 prefix,直接 `<kebab-name>`(简洁,但易跟公共包重名)
- 🟢 **2026-06-20 决策:选择推荐项 — `arch-component-<kebab>` / `@andywong/<kebab>` / repo path**

### 决策 9:默认版本约束策略?

- ✅ **推荐 A**:**caret `^1.2.0`**(允许 minor + patch 自动升级,但 major 不自动)——平衡安全与便利
- 备选 B:`~1.2.0`(只允许 patch)——更保守,但经常落后
- 备选 C:exact pin(完全不自动)——最稳,但需要主动管理升级
- 备选 D:每项目自配(`composed_of` 显式声明,不设默认值)
- 🟢 **2026-06-20 决策:选择 A — caret `^1.2.0`(minor+patch 自动,major 不自动)**

### 决策 10:升级是否自动化?

- ✅ **推荐 A**:**patch 自动 + minor 需 review + major 必须人工决策**
- 备选 B:全部需要人工 review(最保守,适合金融/医疗)
- 备选 C:全部自动(最便利,适合快速迭代)
- 备选 D:按环境分(dev 自动, prod 全 review)
- 🟢 **2026-06-20 决策:选择 A — patch 自动 + minor 需 review + major 必须人工决策**

---

## 11. 原子组件(Atomic Component)

CLAUDE.md 原则:**"原子组件:无法再继续拆分的功能模块"**。本节把"原子性"落到数据模型和登记流程里。

### 11.1 原子 vs 复合

| 类型 | 特征 | composed_of | 例子 |
|------|------|-------------|------|
| **原子组件** | 单一职责,不能再拆 | 空 | user-auth-jwt / email-sender / redis-client |
| **复合组件** | 由多个原子/复合组件组合 | 非空 | user-management-service(auth + email + db) |

**判断准则**(给登记人用的可操作规则):
- ✅ 拆掉任何子模块,组件就无法独立工作 → 原子
- ❌ 子模块各自可独立工作 → 还能拆,继续往下走
- ✅ 单语言、单仓库、单包 → 通常是原子
- ❌ 跨多仓库/多语言、需要协调多个进程 → 通常是复合

> ⚠️ **原子性是相对的**:同一个组件,对某项目是原子,对另一个项目可能可拆。登记时按"当前最细粒度"标记,后续可拆 = 重新登记为复合组件(原组件标 deprecated)。

### 11.2 各层原子性倾向

| 层 | 倾向 | 理由 |
|----|------|------|
| L0 Infrastructure | 几乎都是原子 | "Docker" 不可能拆成更小的"基础组件" |
| L1 Platform | 几乎都是原子 | MySQL / Redis / Nginx 各自完整 |
| L2 Capability | **混合** | lib 型通常是原子;service 型通常是复合 |
| L3 Application | 几乎都是复合 | 一个应用 = 多个 L2 能力 + UI 的组合 |

> **L2 是架构平台最活跃的一层**,原子性的价值在 L2 体现最明显——L2 决定了"哪些是可独立搬运的能力"。

### 11.3 复合组件的"定位"写法

CLAUDE.md 定位稳定性原则 → 复合组件的定位描述**必须引用其原子子组件**:

```yaml
name: user-management-service
atomic: false
composed_of:
  - { component: user-auth-jwt, version_constraint: "^1.2.0" }
  - { component: email-sender,    version_constraint: "~0.8.0" }
  - { component: postgresql-client, version_constraint: ">=2.0.0" }
positioning: |
  用户全生命周期管理服务,基于 user-auth-jwt (认证) + email-sender (邮件通知) +
  postgresql-client (持久化) 提供注册/登录/资料维护/密码重置等能力
```

### 11.4 图遍历验证(架构平台职责)

登记 / 更新复合组件时,平台必须验证:
1. **无环**:DFS 检查 `composed_of` 图,发现环 → 拒绝保存
2. **存在性**:每个 `component_id` 必须存在
3. **分层一致性**:复合组件的子组件层号 ≤ 自己层号
4. **可达性**:展示 `arch tree <comp>` 时递归展开,直到全部原子
5. **应用层缓存**(性能):服务进程内维护 `dict[component_id, set[component_id]]` 反向依赖图,登记 / 删除 / composed_of 变更时**增量更新**,避免每次查询都做全图遍历
6. **Phase 1 预留**:SQLite 表 `composition_edges(component_id, child_id, version_constraint)`,初始可空,JSON 字段保留;当复合层级深度 > 5 层 或组件总数 > 100 时,从 JSON 迁移到 edges 表以彻底解决图查询性能问题(MVP 阶段 JSON 够用,预留表 = 演进路径清晰)

---

## 12. 代码复用机制

光登记元数据不够——**真正复用需要拿到代码/包/容器**。本节定义"登记 → 复用"的链路。

### 12.1 各层对应的复用形态

| 层 | 典型形态 | install_command 示例 |
|----|---------|---------|
| **L0 Infrastructure** | 主机级安装 | `apt install docker.io` / `docker run -d portainer/portainer` |
| **L1 Platform** | 主机级安装 + 配置 | 同 L0 + Ansible/Shell 配置模板 |
| **L2 atomic(lib 型)** | **包安装 + 代码 import** | `pip install arch-component-user-auth-jwt` |
| **L2 composite(service 型)** | **服务调用**或**容器拉取** | `docker pull andywong/user-mgmt:1.0.0` / `curl https://api.user-mgmt.intelab.cn/v1` |
| **L3 Application** | 通常不复用(leaf) | — |

### 12.2 Component.install_command 必填规则

| `scope` + `atomic` | install_command 必填? | 含义 |
|---------------------|-------------------------|------|
| `infra` + * | ✅ | 主机级命令 |
| `lib` + atomic=true | ✅ | pip/npm/cargo 等包命令 |
| `app` + atomic=false | ✅ | 容器拉取或 API 端点 |
| `app` + atomic=true | 选填 | 单文件工具,放 GitHub Release 即可 |
| 其他 | 选填 | — |

### 12.3 推荐实施路线

**Phase B(L0/L1)**:主机级安装,`install_command` 写 `apt` / `docker run` + 必要的配置脚本 URL。

**Phase C(L2 atomic)**:发包到 **GitHub Packages**(免费、内置、与代码仓库同源)
- Python:`pip install --index-url https://pypi.pkg.github.com/AndyWongWithAI/simple/ arch-component-user-auth-jwt`
- Node:`npm install @andywongWithAI/user-auth-jwt`(GitHub npm registry)
- Go:`go install github.com/AndyWongWithAI/email-sender@latest`
- **命名规范**:`arch-component-<kebab>`(Py) / `@andywong/<kebab>`(npm) / 直接 repo path(Go)
- **CLI `arch init` 自动配置 GitHub Packages 索引**(零摩擦):生成 `~/.pip/pip.conf` 或项目级 `pip.conf` 写入 `index-url`,或者 `requirements.txt` 顶部加 `# --index-url https://pypi.pkg.github.com/AndyWongWithAI/simple/` 注释行;`arch use <comp>` 输出可直接 `pip install -r` 的 requirements 片段;**降低新项目首次复用 L2 atomic 组件的门槛**

**Phase D(L2 composite)**:两条路并存
- **库形态**:同样发包,但包里是胶水代码,调用其他 atomic
- **服务形态**:打 Docker 镜像,推 GHCR(`ghcr.io/AndyWongWithAI/user-mgmt:1.0.0`),调用方 `docker pull` + run,或直接调 REST API

### 12.4 CLI 命令(新增到 `arch` 工具)

```bash
# 看完整使用指引
arch use user-auth-jwt
# 输:
#   Install:  pip install arch-component-user-auth-jwt
#   Import:   from arch_component_user_auth_jwt import AuthService
#   Example:  https://github.com/AndyWongWithAI/user-auth-jwt#example
#   Latest:   1.2.0 (stable)

# 展开依赖树(atomic 和 composite 都展开)
arch tree user-management-service
# 输:
#   user-management-service (L2 composite, 1.0.0)
#   ├── user-auth-jwt (L2 atomic, 1.2.0)
#   ├── email-sender (L2 atomic, 0.8.0)
#   └── postgresql-client (L1, deployed on huawei-1)
#
#   ✓ 无环 / ✓ 分层一致

# 扫本地项目,找有新版本的组件
arch outdated /path/to/project

# 用现有组件搭新项目骨架(交互式)
arch init --use user-auth-jwt,email-sender my-new-svc
# → 生成 requirements.txt / package.json / 入口文件 + 一个 hello world
```

### 12.5 与 SDLC 集成

- **Phase 2 设计定稿**:设计复合组件时,**必须列出 composed_of**(否则登记被拒);每个原子组件必须确定 install_command
- **Phase 6 部署**:
  - L0/L1:登记到 `Deployment.host`(哪个机器、哪个版本)
  - L2 atomic lib:登记 `package_name` + 实际 import 路径
  - L2 composite service:登记容器镜像 + 端口 + 健康检查 URL
  - L3 应用:登记完整栈(从上到下所有组件)
- **Phase 8 反馈**:Feedback 新增 `reused_in_projects: list[string]`,便于评估 bug 影响面(对应 CLAUDE.md 反馈原则的"考虑存量引用关系")

---

## 13. 版本演进与兼容性管理

CLAUDE.md **复用原则 + 一致性 + 反馈原则**的延伸——**下层组件改了,上层组件怎么不挂;上层组件想升,怎么升得可控**。

### 13.1 影响传播规则(下层 → 上层)

按层级:
```
L0 变更 → L1/L2/L3 全部可能受影响
L1 变更 → L2/L3 引用它的组件
L2 变更 → L3 引用它的应用
L3 变更 → 几乎只影响最终用户
```

按**分发形态**(决定"改了下层 → 存量 build 受不受影响"):

| 复用形态 | 改了下层 → 重新 build 必要? | 存量 build 是否受影响? | 风险 |
|---------|---------------------------|---------------------|------|
| 包(pip/npm)+ lockfile | 必须 rebuild | ✅ **不受影响**(lockfile 锁版) | 低 |
| 包(pip/npm) 无 lockfile | 重 install 即变 | ❌ **不可预期** | 高 |
| 容器镜像(版本 tag 如 `:1.2.0`) | 必须 rebuild image | ✅ **不受影响**(镜像层不可变) | 低 |
| 容器镜像(`latest` tag) | 不 rebuild 也变 | ❌ **不可预期** | 高 |
| 源码引用(git tag) | 必须重新 clone | ✅ **不受影响** | 低 |
| **HTTP API 调用** | **完全无法控制** | ❌ **服务端改 → 客户端挂** | **极高** |

> ⚠️ **HTTP API 是最危险的形态**——服务端代码改完,客户端自动受影响。service 型组件必须:
> - 走容器化(版本固定)
> - 或严格的 API 版本管理(`/v1/` `/v2/` 路径版本化,旧版保持兼容直到明确下线)
> - **架构平台登记时,API 类组件强制要求填 `api_version_path`(如 `/v1/`)**
>
> **架构平台对 API 类组件的强制治理**:
> 1. **登记时**:强制填 `api_version_path`(`/v1/`)
> 2. **部署时**:强制登记 `openapi_spec_url`(OpenAPI Spec 文件地址,通常在 `repo_url` 下的 `/openapi.yaml`)
> 3. **CI 监控**:架构平台每日定时(凌晨 04:30)拉每个 API 类组件的 OpenAPI Spec + 算 SHA256 hash,跟上一次对比
> 4. **hash 变了但 Version 未升** → 自动创建 Feedback:`severity=high`、`status=open`、`bug_summary="API spec drift detected: <comp> <ver> spec changed without version bump"`、`reused_in_projects=[所有引用此组件的项目]`
> 5. **架构平台职责**:**发现 → 告警 → 触发决策**(优化/新建/保持),不直接 block 生产,但强制人工 ack

### 13.2 SemVer 强制约束

CLAUDE.md 一致性 + 定位稳定性原则的延伸:
- **L1/L2 组件必须严格遵守 SemVer** —— 定位稳定 = 不能悄悄破坏 API
- 每次发版必须声明 `semver_intent`:major / minor / patch
- **架构平台强制**:major 版本必须填写 `breaking_changes` 字段(列出破坏了什么 + 替代方案),否则不允许登记

### 13.3 数据模型补充

```yaml
Version:
  # ... 原有字段
  semver_intent: enum [major, minor, patch]    # 发版时声明
  breaking_changes: text                       # major 必填
  deprecates: list[{ api: string, replacement: string, remove_in: string }]  # 弃用清单
  compatibility_window: string                 # 如 "LTS until 2027-06"

Deployment:
  # ... 原有字段
  resolved_versions: dict[component_name, version]   # 实际安装的版本(从 lockfile 读)
  lockfile_hash: string                               # SHA256 of requirements.lock / package-lock.json / Dockerfile 基镜像
  build_reproducible: boolean                         # 是否能 bit-by-bit 重现
```

### 13.4 上层组件如何"声明可接受的下层版本范围"

`composed_of` 的 `version_constraint` 字段起作用:

```yaml
composed_of:
  - { component: user-auth-jwt,     version_constraint: "^1.2.0" }            # 允许 1.x 升级,2.0 必须人工
  - { component: email-sender,      version_constraint: "~0.8.0" }            # 只接 0.8.x
  - { component: postgresql-client, version_constraint: ">=2.0.0 <3.0.0" }    # 显式范围
```

### 13.5 升级行为策略(项目级配置)

每个项目根目录放 `.aip-upgrade.yml`:

```yaml
upgrade_strategy:
  default: caret                    # 默认 caret,可被 per_component 覆盖
  per_component:
    - { name: postgresql-client, strategy: exact }  # DB 客户端锁死
    - { name: email-sender,      strategy: tilde }   # 只升 patch
  auto_upgrade_minor: false         # minor 升级需要人工 review
  auto_upgrade_patch: true          # patch 升级自动
  block_on_major_bump: true         # major 升级阻塞 PR,要求显式确认
```

CLI 行为:

```bash
# 看哪些可升级
arch outdated
# 输:
#   user-auth-jwt         1.2.0  →  1.5.3   (minor, 兼容)
#   email-sender          0.8.0  →  0.9.0   (minor, BREAKING,需 review)
#   postgresql-client     2.1.0  =  2.1.0   (up-to-date, 锁定)
#
#   ✓ patch 自动可升级 / ⚠ 1 个 minor 需 review / ❌ 0 个 major

# 按策略升级并生成新 lockfile
arch upgrade --all                # 按 .aip-upgrade.yml 走
arch upgrade --interactive        # 逐个确认
arch upgrade --no-major           # 不动 major
arch upgrade --pin postgresql-client=2.1.0  # 显式锁定到指定版本

# 解锁 + 重选
arch upgrade --unlock email-sender --to "^0.9.0"
```

### 13.6 Build 流水线集成(GitHub Action)

```yaml
- name: Resolve and lock dependencies
  run: arch lock --output requirements.lock

- name: Check for breaking changes
  run: arch outdated --fail-on-major  # 有 major 升级就 fail PR

- name: Build (reproducible)
  run: docker build -t myapp:${{ github.sha }} .

- name: Record deployment
  uses: AndyWongWithAI/arch-platform-register@v1
  with:
    lockfile: ./requirements.lock
    image-tag: ${{ github.sha }}
```

构建产物(lockfile + 镜像基版本 + config)写进 `Deployment.lockfile_hash`,**确保 bit-by-bit 可重现**。

### 13.7 反馈闭环:大版本升级触发架构平台决策

CLAUDE.md 反馈原则在版本演进场景的落点:

```
下层组件发 major 版(破坏性变更)
  ↓
架构平台:从 composed_of 反查所有受影响的直接上层
  ↓
递归:从上层 composed_of 继续反查 → 受影响的间接上层
  ↓
决策生成:每个受影响上层标 "需要决策"
  ↓
决策选项:优化(改上层适配)/ 新建(上层 fork 一份独立组件)/ 保持(上层不升级,固定旧版)
  ↓
登记决策 → 各上层组件 owner 收到通知 → 实施 → 登记新 Version
```

**这就是 CLAUDE.md "由架构平台考虑存量引用关系后进行决策"的字面实现**。

### 13.8 三种"暂不升级"模式

有时候上层组件**故意**不升级到下层最新版,这是合理的:

| 模式 | 场景 | 数据模型标记 |
|------|------|-------------|
| **LTS 锁定** | 上层生产环境要求稳定,不跟下层频繁升级 | 下层 Version 写 `compatibility_window: "LTS until 2027-06"`,上层声明"支持到该日期" |
| **EOL 等待** | 下层宣布 EOL,但上层还在用,架构平台标记"待迁移" | Feedback 关联 Version,status = open,decision 待填 |
| **故意分叉** | 上层 fork 了一份下层,不再同步 | `composed_of` 引用 fork 后的新 Component(原 Component 标 deprecated,新 Component 是 fork 出来的独立资产) |

### 13.9 三道防线(综合防御)

把上面所有点串起来,**防御下层变更影响上层**,按成本从低到高:

1. **第一道:版本约束 + lockfile**(架构平台 + 包管理器)
   - 代价最低,默认开启
   - 上层用 caret/tilde 显式声明兼容范围 → patch/minor 自动升,major 阻塞

2. **第二道:容器化 + 镜像 tag 固定**(CI/CD)
   - 代价中,生产部署必备
   - 镜像 tag 永远不用 `latest`,永远用 SHA / 版本号 → 存量 build 不变

3. **第三道:API 版本管理**(架构平台强制)
   - 代价高,只对 service 型组件
   - 路径版本化(`/v1/` `/v2/`) → 旧版显式声明保留期,客户端可固定走旧版

---

## 不做的(总览)

- ❌ 企业级 RBAC / 多租户 / SSO
- ❌ 实时协作 / 评论 / @ 提及
- ❌ 自动代码分析 / AST 抽取
- ❌ 微服务拆分 / K8s
- ❌ i18n
- ❌ 复杂工作流引擎
- ❌ GitHub Issues 启用(架构平台替代)
- ❌ Webhook MVP(Phase 3 可选)
- ❌ 架构平台部署到 #3(定位冲突,放 #1)

---

## 验证

### Phase 1 后端验证

- [ ] 13 个 API 端点都能响应
- [ ] pytest 10 个集成测试全部通过
- [ ] SQLite 文件创建在 `/opt/services/arch-platform/data/arch.db`
- [ ] systemd `arch-platform.service` active (running)
- [ ] `curl http://127.0.0.1:8088/healthz` → 200 OK

### Phase 2 CLI 验证

- [ ] `arch component create` 创建组件成功
- [ ] `arch search <keyword>` 返回结果
- [ ] `arch detect` 读 `aip.json` 预填参数

### Phase 3 GitHub Action 验证

- [ ] Action 发布到 `AndyWongWithAI/arch-platform-register`
- [ ] 真实 deploy job 末尾 step 自动登记成功

### Phase 4 Web UI 验证

- [ ] 6 个页面都能渲染
- [ ] 搜索过滤能用
- [ ] 反馈 Kanban 可拖拽 / 填 decision

### Phase 5 数据导入验证

- [ ] 5-10 个真实组件入库
- [ ] GitHub Issues 关闭
- [ ] sdlc.md 三个登记节点都在用

---

## 关键文件

**修改 memory**(立即):
- `/home/hq/.claude/projects/-home-hq/memory/architecture-platform.md` — 加设计方案摘要 + 5 个决策项

**未来创建**(Phase 0-5 实施时):
- `/home/hq/.claude/projects/-home-hq/memory/architecture-platform-decisions.md` — 5 个决策的最终选择记录
- GitHub 仓库 `AndyWongWithAI/Architecture-Platform`:
  - `openapi.yaml`(Phase 0)
  - `app/main.py` + `app/models.py` + `app/routes/`(Phase 1)
  - `cli/arch.py`(Phase 2)
  - `.github/actions/arch-platform-register/action.yml`(Phase 3)
  - `templates/` + `static/`(Phase 4)

---

## 关联

- [[server-1]] — 架构平台部署位置(#1)
- [[server-2]] — 异地备份目标
- [[server-3]] — 开发测试 + 监控(架构平台的 dev 实例候选)
- [[local-machine]] — WSL 是 CLI 工具主战场
- [[sdlc]] — 3 个登记节点在 Phase 2 / 6 / 8
- [[domain-intelab]] — 未来可能用子域 `platform.intelab.cn`