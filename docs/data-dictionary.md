# 架构平台 数据字典

> Phase 0 产物 · 4 个核心实体的字段级定义 · 对应 ER 图 `docs/er-diagram.md` 和 OpenAPI spec `docs/openapi.yaml`

## 字段类型约定

| 缩写 | 含义 |
|------|------|
| UUID | UUID v4,字符串 |
| string | 字符串 |
| text | 长文本(无长度限制或 > 500) |
| enum | 枚举值,具体取值见 OpenAPI spec |
| boolean | 布尔 |
| int | 整数 |
| timestamp | ISO 8601 + UTC,如 `2026-06-20T07:00:00Z` |
| json | JSON 序列化的结构 |
| list\<T\> | T 类型数组 |
| dict | 键值对 |
| FK | 外键 |

---

## 1. Component(组件)

### 基础字段

| 字段 | 类型 | 必填 | 默认 | 含义 | 约束 | 例子 |
|------|------|------|------|------|------|------|
| `id` | UUID | ✅ | gen | 主键 | — | — |
| `name` | string | ✅ | — | 组件唯一标识 | kebab-case + 域名点号,`^[a-z][a-z0-9.-]*$`,2-64 字符,**全局唯一** | `user-auth-jwt` / `intelab.cn-website` |
| `title` | string | ✅ | — | 人类可读标题 | ≤ 128 字符 | `基于 JWT 的用户认证` |
| `positioning` | text | ✅ | — | 定位描述 | ≥ 10 字符,≤ 500,**CLAUDE.md 定位稳定性:不可变** | `面向 Web 项目的无状态用户认证,支持刷新令牌` |
| `status` | enum | ✅(读)/✅(写更新) | `draft` | 生命周期状态 | `draft` / `stable` / `deprecated` / `archived` | `stable` |
| `created_at` | timestamp | ✅(自动) | now | 创建时间 | ISO 8601 + UTC | — |
| `updated_at` | timestamp | ✅(自动) | now | 更新时间 | ISO 8601 + UTC,任何字段修改触发 | — |

### 分类字段

| 字段 | 类型 | 必填 | 默认 | 含义 | 约束 | 例子 |
|------|------|------|------|------|------|------|
| `category` | enum | ✅ | — | 功能分类 | `auth` / `db` / `cache` / `queue` / `log` / `deploy` / `monitor` / `ui` / `util` / `other` | `auth` |
| `scope` | enum | ✅ | — | 作用域 | `app` / `infra` / `lib` / `tool` | `lib` |
| `layer` | enum | ✅ | — | 分层(DESIGN.md §2.4) | `L0_infrastructure` / `L1_platform` / `L2_capability` / `L3_application` | `L2_capability` |

### 原子性与复合(§11)

| 字段 | 类型 | 必填 | 默认 | 含义 | 约束 |
|------|------|------|------|------|------|
| `atomic` | boolean | ✅ | `true` | 是否原子组件 | `atomic=true` ⇒ `composed_of` 必空;反之必非空 |
| `composed_of` | list\<ComposedOfEntry\> | 条件 | — | 复合组件的子组件清单 | 每项 = `{component_id, version_constraint}`;version_constraint 是 SemVer 约束(`^1.2.0` / `~0.8.0` / `>=2.0.0 <3.0.0` / `1.2.0`) |

### 资产判定(CLAUDE.md 资产原则)

| 字段 | 类型 | 必填 | 默认 | 含义 | 约束 | 例子 |
|------|------|------|------|------|------|------|
| `is_asset` | boolean | ✅ | `true` | 是否可复用资产 | `false` = 项目级代码,登记仅为追溯,不复用;搜索默认过滤、`arch use` 警告 | `true` |
| `distribution_form` | enum | 条件 | — | 资产分发形态(11 个 enum) | `is_asset=true` 时必填;`package` / `container` / `binary` / `source` / `http_api` / `schema` / `dataset` / `config_template` / `iac` / `skill` / `tool` | `package` |
| `interface_contract` | string | 条件 | null | 接口契约 | `distribution_form=http_api` 时必填(URL 指向 OpenAPI Spec);其他可填文本 | `https://.../openapi.yaml` |
| `knowledge_artifact` | boolean | ✅ | `false` | 是否 AI 上下文资产 | `true` = AI 上下文类资产(skill / tool / memory / agent 文档),跟传统代码资产是不同维度;跟 `distribution_form` 正交 | `false` |

### 复用元数据(§12)

| 字段 | 类型 | 必填 | 默认 | 含义 | 约束 |
|------|------|------|------|------|------|
| `language` | enum | ❌ | — | 主要语言 | `python` / `typescript` / `javascript` / `go` / `rust` / `shell` / `sql` / `other` |
| `package_name` | string | 条件 | — | 包名(发包用) | `distribution_form=package` 时必填 | `arch-component-user-auth-jwt` |
| `install_command` | text | 条件 | — | 一行安装命令 | `is_asset=true` 时必填 | `pip install arch-component-user-auth-jwt` |
| `usage_example` | text | ❌ | — | 一行代码示例 | — | `from arch_component_user_auth_jwt import AuthService` |
| `repo_url` | string | ❌ | — | GitHub repo URL | URL 格式 | `https://github.com/AndyWongWithAI/user-auth-jwt` |
| `tags` | list\<string\> | ❌ | `[]` | 标签 | ≤ 20 项 | `["jwt", "refresh-token"]` |

### 推荐版本指针

| 字段 | 类型 | 必填 | 默认 | 含义 |
|------|------|------|------|------|
| `current_version_id` | UUID (FK → Version.id) | ❌ | null | 推荐版本指针,可空(刚创建还没版本时) |

---

## 2. Version(版本)

| 字段 | 类型 | 必填 | 默认 | 含义 | 约束 | 例子 |
|------|------|------|------|------|------|------|
| `id` | UUID | ✅ | gen | 主键 | — | — |
| `component_id` | UUID (FK) | ✅ | — | 所属组件 | — | — |
| `version` | string | ✅ | — | SemVer 版本号 | `^\d+\.\d+\.\d+$`,**组件内唯一** | `1.2.0` |
| `semver_intent` | enum | ✅ | — | 发版意图 | `major` / `minor` / `patch` | `minor` |
| `design_doc` | text | ❌ | — | Phase 2 设计定稿(意图 + 影响面 + 替代方案) | 长文本 | — |
| `design_decided_at` | timestamp | ❌ | — | 设计定稿时间 | ISO 8601 + UTC | — |
| `replaces_version` | string | ❌ | null | 被替代的旧版本号 | SemVer 格式 | `1.1.0` |
| `changelog` | text | ✅ | — | 变更日志 | ≥ 1 字符 | `新增 refresh token 机制` |
| `breaking_changes` | text | 条件 | — | **major 必填**,破坏了什么 + 迁移方案 | `semver_intent=major` 时必填,否则 422 | `auth token 字段重命名 access_token → jwt` |
| `deprecates` | list\<DeprecateEntry\> | ❌ | `[]` | 弃用清单 | 每项 = `{api, replacement, remove_in}` | — |
| `compatibility_window` | string | ❌ | — | LTS 截止说明 | 自由文本 | `LTS until 2027-06` |
| `created_at` | timestamp | ✅(自动) | now | — | — | — |

### DeprecateEntry 子结构

| 字段 | 类型 | 必填 | 含义 | 例子 |
|------|------|------|------|------|
| `api` | string | ✅ | 弃用的 API / 功能名 | `POST /v1/login` |
| `replacement` | string | ✅ | 替代方案 | `POST /v2/auth/token` |
| `remove_in` | string | ✅ | 在哪个版本彻底移除 | `2.0.0` |

---

## 3. Deployment(部署)

| 字段 | 类型 | 必填 | 默认 | 含义 | 约束 | 例子 |
|------|------|------|------|------|------|------|
| `id` | UUID | ✅ | gen | 主键 | — | — |
| `version_id` | UUID (FK) | ✅ | — | 被部署的版本 | — | — |
| `env` | enum | ✅ | — | 环境 | `dev` / `staging` / `prod` | `prod` |
| `host` | string | ✅ | — | 主机标识 | 自定义字符串 | `alicloud-1` |
| `deploy_path` | string | ✅ | — | 部署路径 | — | `/opt/services/auth` |
| `config_hash` | string | ❌ | — | 配置文件 SHA256 | `sha256:` 前缀 | `sha256:abc123...` |
| `deployed_by` | string | ✅ | — | 部署者 | — | `github-actions` |
| `deployed_at` | timestamp | ✅(自动) | now | 部署时间 | ISO 8601 + UTC | — |
| `rollback_to` | string | ❌ | null | 回滚到的版本号 | SemVer | `1.1.0` |
| `resolved_versions` | dict\<string, string\> | ❌ | — | 实际安装的下层组件版本 | key=组件名, value=版本号 | `{"user-auth-jwt": "1.2.3"}` |
| `lockfile_hash` | string | ❌ | — | 整个 lockfile 的 SHA256 | `sha256:` 前缀 | `sha256:def456...` |
| `build_reproducible` | boolean | ❌ | `false` | 标记本次 build 是否 bit-by-bit 一致 | — | `true` |

---

## 4. Feedback(反馈)

| 字段 | 类型 | 必填 | 默认 | 含义 | 约束 | 例子 |
|------|------|------|------|------|------|------|
| `id` | UUID | ✅ | gen | 主键 | — | — |
| `version_id` | UUID (FK) | ✅ | — | 反馈关联的版本 | — | — |
| `reporter` | string | ✅ | — | 报告人 | — | `andy` |
| `bug_summary` | text | ✅ | — | 缺陷摘要 | 5-500 字符 | `高并发下 refresh token 偶发 500` |
| `root_cause` | text | ❌ | — | 根因分析 | 长文本 | `竞态条件,旧 token 撤销与新 token 颁发未加锁` |
| `fix_plan` | text | ❌ | — | 修复方案 | 长文本 | `改为 Redis 分布式锁` |
| `severity` | enum | ✅ | — | 严重度 | `low` / `medium` / `high` / `critical` | `high` |
| `status` | enum | ✅ | `open` | 处理状态 | `open` / `triaged` / `fixing` / `fixed` / `wontfix` | `open` |
| `decision` | enum | 条件 | null | 决策闭环 | 转 `fixed`/`wontfix` 前必填(否则 422);`optimize` / `fork_new` / `keep_as_is` / `reassess_form`(重新审视资产形态) | `optimize` |
| `reused_in_projects` | list\<string\> | ❌ | `[]` | 影响面(在哪些项目里被使用) | — | `["user-mgmt", "internal-admin"]` |
| `decided_at` | timestamp | 条件 | null | 决策时间 | 填 `decision` 时自动写入 | — |
| `created_at` | timestamp | ✅(自动) | now | 报告时间 | — | — |

---

## 索引策略

> 索引目标:让常见查询(列表 + 搜索 + 影响面分析)走索引,避免全表扫描。

### Component

| 索引 | 类型 | 字段 | 理由 |
|------|------|------|------|
| `idx_component_name` | **UNIQUE** | `name` | 全局唯一,也是 GET 详情常用 lookup |
| `idx_component_layer` | 普通 | `layer` | 按层级筛选(L2 atomic 列表) |
| `idx_component_category` | 普通 | `category` | 按功能分类筛选(auth 类所有组件) |
| `idx_component_layer_category` | 复合 | `(layer, category)` | 联合筛选(L2 + auth) |
| `idx_component_tags` | GIN / JSON 函数 | `tags` | 标签搜索(待 SQLite FTS5 或迁移 PG 后启用) |
| `idx_component_status` | 普通 | `status` | 排除 deprecated/archived |
| `idx_component_is_asset` | 部分 | `is_asset` WHERE `is_asset = true` | 资产清单(默认查询路径) |

### Version

| 索引 | 类型 | 字段 | 理由 |
|------|------|------|------|
| `idx_version_component_id` | 普通 | `component_id` | 按组件查所有版本 |
| `idx_version_component_version` | **UNIQUE** | `(component_id, version)` | 组件内版本号唯一 |
| `idx_version_semver_intent` | 普通 | `semver_intent` | 统计 major 发布频次 |

### Deployment

| 索引 | 类型 | 字段 | 理由 |
|------|------|------|------|
| `idx_deployment_version_id` | 普通 | `version_id` | 查某版本所有部署 |
| `idx_deployment_host_time` | 复合 | `(host, deployed_at DESC)` | 查某主机部署历史(按时间倒序) |
| `idx_deployment_env` | 普通 | `env` | 查 prod 环境所有部署 |

### Feedback

| 索引 | 类型 | 字段 | 理由 |
|------|------|------|------|
| `idx_feedback_version_id` | 普通 | `version_id` | 查某版本所有反馈 |
| `idx_feedback_status` | 普通 | `status` | 看板:open / triaged |
| `idx_feedback_severity` | 普通 | `severity` | 高严重度优先 |
| `idx_feedback_decision_open` | 部分 | `decision` WHERE `decision IS NULL` | 找未决策的反馈 |

---

## 命名约定

| 类型 | 命名 | 例子 |
|------|------|------|
| Component name | kebab-case,小写 | `user-auth-jwt`、`email-sender` |
| Version | SemVer | `1.2.0`、`2.0.0-rc.1`(可选 prerelease) |
| Host 标识 | `<provider>-<n>` | `alicloud-1`、`huawei-1`、`tencent-2` |
| Tag | kebab-case | `jwt`、`refresh-token`、`fastapi` |
| Position / 路径 | URL 风格 | `/opt/services/auth` |

---

## 不存什么(明确不做)

- ❌ 不存源码 —— 架构平台是元数据 + 索引,代码在 GitHub repo 或包仓库
- ❌ 不存运行时指标 —— Prometheus / Grafana 负责
- ❌ 不存用户/权限 —— MVP 无 RBAC,单 API Key
- ❌ 不存日志/审计 —— 待 Phase 3+ 评估
- ❌ 不存组件间通信消息 —— 服务网格层的事