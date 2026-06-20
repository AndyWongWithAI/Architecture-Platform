# Architecture Platform — Backend

CLAUDE.md 提到的"架构平台"MVP 后端。FastAPI + SQLAlchemy + SQLite。

## 快速开始

```bash
# 1. 安装依赖(系统已装则跳过)
pip3 install --break-system-packages fastapi uvicorn[standard] sqlalchemy pydantic pyyaml python-frontmatter pytest httpx

# 2. 导入 docs/components/*.md 到 SQLite
./run.sh import

# 3. 启动 dev server(auto-reload)
./run.sh dev
# → http://127.0.0.1:8088
# → http://127.0.0.1:8088/docs (Swagger UI)
# → http://127.0.0.1:8088/healthz

# 4. 跑测试
./run.sh test
```

## 当前实现范围(Phase 1.0 MVP + Phase 1.1 写操作)

| 功能 | 状态 | 备注 |
|------|------|------|
| 4 实体 ORM models | ✅ | 对应 OpenAPI spec |
| Markdown importer | ✅ | 读 `docs/components/*.md` → SQLite |
| **GET endpoints(8 个)** | ✅ | 列表/详情/tree/usage/versions/deployments/feedbacks/healthz |
| **POST /components** | ✅ Phase 1.1 | API Key 鉴权 + 业务规则校验 |
| **PATCH /components/{id}** | ✅ Phase 1.1 | 部分字段更新 + 完整重新校验 |
| **API Key 鉴权中间件** | ✅ Phase 1.1 | `X-API-Key` 头;`ARCH_PLATFORM_API_KEY` 环境变量;未设置 = 开放模式(开发用) |
| **业务规则校验** | ✅ | is_asset 一致性、atomic/composed_of 自洽、子组件存在性 |
| GET `/search` | ⏳ Phase 1.1 后续 | FTS5 或 PG 迁移后启用 |
| POST `/versions` / `/deployments` / `/feedbacks` | ⏳ Phase 1.1 后续 | API 框架就位,业务逻辑待补 |
| Web UI(HTMX) | ⏳ Phase 4 | 只读 + 反馈看板 |
| CLI(`arch`) | ⏳ Phase 2 | 写操作入口 |
| GitHub Action | ⏳ Phase 3 | 自动登记 deployment |
| **部署到 #1** | ⏳ Phase 1.2 | **Dockerfile + compose + systemd + nginx** |

## 数据模型(2026-06-20 修订版)

跟 OpenAPI spec `docs/openapi.yaml` 一致,关键字段:

- **Component**:`is_asset` / `distribution_form`(11 个 enum)/ `interface_contract` / `knowledge_artifact`
- **Feedback**:`decision` 含 `reassess_form`(重新审视资产形态)
- **Version**:`semver_intent` + `breaking_changes`(major 必填)
- **Deployment**:`lockfile_hash` / `resolved_versions` / `build_reproducible`

## 验证脚本输出

跑 `./run.sh import` 应该输出:
```
ImportResult(created=9, updated=0, skipped=0, errors=0)
```

跑 `./run.sh test` 应该 8 个测试全部通过。

## 跟 AI-Assets 仓库的关系

`knowledge_artifact=true` 的 Component(待 Phase 5 数据导入登记),`repo_url` 指向 `AndyWongWithAI/AI-Assets` 仓库。

详见 `Architecture-Platform/docs/ai-assets-integration.md`。