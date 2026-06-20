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

## 当前实现范围(Phase 1.0 MVP)

| 功能 | 状态 | 备注 |
|------|------|------|
| 4 实体 ORM models(Component / Version / Deployment / Feedback) | ✅ 完成 | 对应 OpenAPI spec |
| Markdown importer | ✅ 完成 | 读 `docs/components/*.md` → SQLite |
| GET `/api/v1/components` | ✅ 完成 | 支持 `q` / `layer` / `category` / `is_asset` 过滤 |
| GET `/api/v1/components/{id}` | ✅ 完成 | 支持 id 或 name 查询 |
| GET `/api/v1/components/{id}/tree` | ✅ 完成 | 展开 composed_of(最大深度 5,防环) |
| GET `/api/v1/components/{id}/usage` | ✅ 完成 | `arch use` 的输出 |
| GET `/api/v1/versions/{id}` | ✅ 完成 | 版本详情 |
| GET `/api/v1/deployments` | ✅ 完成 | 按 version_id / host / env 过滤 |
| GET `/api/v1/feedbacks` | ✅ 完成 | 按 status / version_id 过滤 |
| GET `/healthz` | ✅ 完成 | 健康检查 |
| **POST / PATCH endpoints** | ⏳ Phase 1.1 | 需要 API Key 鉴权,本会话不实现 |
| **GET `/search`** | ⏳ Phase 1.1 | 全文搜索,FTS5 或 PG 迁移后启用 |
| **API Key 鉴权** | ⏳ Phase 1.1 | 写操作必须有 Key |
| **Web UI(HTMX)** | ⏳ Phase 4 | 只读 + 反馈看板 |
| **CLI(`arch`)** | ⏳ Phase 2 | 写操作入口 |
| **GitHub Action** | ⏳ Phase 3 | 自动登记 deployment |
| **部署到 #1** | ⏳ Phase 1.2 | systemd + nginx 反代 |

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