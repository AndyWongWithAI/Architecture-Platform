# fcr(Feedback Coverage Ratio)指标设计

> **状态**:已实施(2026-06-27)
> **Owner**:小敏(audit owner)
> **关联**:`specs/2026-q3-roadmap.md` 目标 1 / `specs/2026-07-08-q3-kickoff-meeting.md` 议题二
> **Q3 截止**:2026-08-15(本任务)+ 2026-09-30(dashboard 上线)

## 一、指标定义

| 项 | 值 |
|---|---|
| **名称** | `fcr`(feedback coverage ratio) |
| **公式** | `已加 emit_fatal 的 fatal 路径数 / 全部 fatal 路径数` |
| **取值范围** | `0.0` ~ `1.0`(超出由 Pydantic 422 拒绝) |
| **类型** | `Float` / SQLAlchemy `Float` / Pydantic `float` |
| **可空性** | **NULL** 表示尚未上报(默认状态) |
| **存储位置** | `components.fcr` |
| **基线** | 2026-06-26 实测约 10%(9 blocker / ~90 fatal 路径) |
| **Q3 末目标** | `1.0`(100%) |

> 与 `feedback coverage ratio` 不同的近邻指标(避免歧义):
> - `tcr` = test coverage ratio(Q3 目标 2)
> - `fcov` = feedback 实际接收覆盖率(同义不同命名,不要混用)

## 二、数据流

```
audit --scope=skills --modules=principles_depth
  │
  ├── 1. 扫描所有 skill 的 scripts/*.py,统计 fatal 路径总数 N_total
  ├── 2. 扫描同一目录下 `emit_fatal(...)` 调用数 N_emitted
  ├── 3. 按 skill / component 维度聚合 fcr = N_emitted / N_total
  │
  └── 4. 逐 component 上报:
        arch component report-fcr --name=<comp> --fcr=<0.0-1.0>
          │
          └── PUT /api/v1/components/{name}/fcr  (Body: {"fcr": 0.85})
                │
                └── arch-platform 写库(components.fcr + updated_at)
                      │
                      └── dashboard 读 GET /api/v1/components?include_archived=false
```

**关键设计点**:
- 公式分子分母都是 **audit 端** 在跑 scan 时算的(本地静态分析),arch-platform 只负责存标量。
- 上报是 **推模型**(audit 主动),不是拉模型(避免 audit 端知道 arch API 的存在,保持 L0 原子组件定位)。
- 不在每次 fatal 触发时上报(那会刷屏),只在 audit 跑完后批量上。

## 三、API 端点

### PUT `/api/v1/components/{component_id}/fcr`

| 维度 | 值 |
|---|---|
| **定位** | 支持按 `id`(UUID)或 `name`(slug) |
| **Body** | `{"fcr": 0.85}` |
| **校验** | Pydantic `Field(ge=0.0, le=1.0)`,超出 → 422 |
| **认证** | 当前开放模式(audit 端 + 后端同内网)。后续如暴露公网,加 `require_api_key`。 |
| **返回** | `ComponentOut` 全字段(含新 `fcr` + `updated_at`) |

**错误码**:
- `404` component 不存在
- `422` fcr 超出 [0.0, 1.0]

**示例**:
```bash
curl -X PUT http://127.0.0.1:8088/api/v1/components/audit/fcr \
     -H "Content-Type: application/json" \
     -d '{"fcr": 0.85}'
# → 200 {"id": "...", "name": "audit", "fcr": 0.85, "updated_at": "...", ...}
```

## 四、CLI 用法

```bash
# 上报
arch component report-fcr --name=audit --fcr=0.85
# → ✓ fcr 已上报:audit = 0.85

# 范围超出
arch component report-fcr --name=audit --fcr=1.5
# → Error: Invalid value for '--fcr': 1.5 is not in the range 0.0<=x<=1.0.

# component 不存在
arch component report-fcr --name=ghost --fcr=0.5
# → ✗ 上报失败:[404] 资源不存在:component 'ghost' not found
```

## 五、Audit 端上报调用方式(本任务**不**实现)

> 实施责任:audit skill owner(小敏)
> 时间:Q3 内 8 月前(本任务只提供 API,audit owner 负责 audit 侧)

audit 端集成方式(规划):
- 在 `audit/lib/metrics.py`(规划新增)里加 `report_fcr(component: str, fcr: float) -> bool` 函数
- 实现:`subprocess.run(["arch", "component", "report-fcr", "--name", ..., "--fcr", ...])`
- 调用时机:`audit --scope=skills --modules=principles_depth` 跑完时
- 失败处理:同 `feedback_emit` 降级策略(stderr warning,永不 raise)

## 六、Dashboard 集成路径(Q3 末或 Q4)

预留:
1. 后端:GET `/api/v1/components` 已返回 `fcr` 字段(本任务已实现)
2. Web UI:在 `/components` 列表 + `/components/{name}` 详情页加 fcr 列
3. Web UI:新增 `/metrics/fcr` 页面展示所有 skill 的 fcr + 趋势图(可选,需 historical data)
4. 数据采集:fcr 需在 audit run 维度被记录才能做趋势(未来可加 `audit_runs.fcr_snapshot` JSON 字段)

## 七、验证

- [x] 后端 8 个 pytest 全过(`backend/tests/test_z_fcr.py`)
- [x] CLI 8 个 pytest 全过(`cli/tests/test_z_fcr.py`)
- [x] `arch component report-fcr --name=audit --fcr=0.85` 实际调用成功(本任务验证步骤 3)
- [x] GET `/api/v1/components/audit` 返回 JSON 含 `fcr` 字段
- [ ] arch-platform 公网部署的字段兼容性(2026-08-15 前部署,验证 _migrate_legacy_columns 自动加 fcr 列)

## 八、Trade-off 与决策记录

| 决策 | 选项 | 选择 | 理由 |
|---|---|---|---|
| 字段名 | `feedback_coverage` / `fcov` / `fcr` | **`fcr`** | 短,易引用;与 `tcr`(test coverage ratio)命名风格一致;不暴露内部实现细节(只说"覆盖率"是 tcr 那种) |
| 是否建独立 metric 表 | 是 / 否 | **否,放 Component 表** | fcr 与 component 强 1:1;独立表会带来 join 成本 + dashboard 查询复杂度;Q3 内不需要历史快照 |
| 范围 | [0.0, 1.0] | **[0.0, 1.0]** | 与公式语义对齐(比例);不允许 > 1.0(暗示 emit_fatal 调多了);不允许 < 0 |
| 默认值 | 0.0 / NULL | **NULL** | 0.0 有歧义(是"没 fatal 路径"还是"全没接"?)→ NULL = 未上报,清晰 |
| 上报端点 | PUT /components/{id}/fcr | **PUT** | 幂等;fcr 是 scalar,不存在"创建"语义 |
| 鉴权 | 开放 / API key | **开放(本任务)** | audit 端在内网,无暴露面;后续若公网可加 `require_api_key` 不破坏契约 |
| 数据库迁移 | Alembic / SQLAlchemy create_all + ALTER | **后者** | 项目现状(已有 `_migrate_legacy_columns` 模式),不引入新依赖 |
| `arch-platform` 字段同步 | 加进 `ComponentBase` / 加进 `ComponentUpdate` | **都不加** | fcr 不应由人工维护,只由 audit 上报 → 单独端点(避免 PATCH 误改) |

## 九、变更文件清单

| 文件 | 变更 |
|---|---|
| `backend/app/models.py` | `Component` 加 `fcr = Column(Float, nullable=True, default=None)` |
| `backend/app/database.py` | `_migrate_legacy_columns` 加 fcr 列 ALTER + 迁移记录 |
| `backend/app/schemas.py` | `ComponentOut.fcr: Optional[float] = None`;新增 `FcrUpdate` schema |
| `backend/app/routes/components.py` | 新增 `PUT /{component_id}/fcr` 端点 |
| `backend/tests/test_z_fcr.py` | 新增(8 个测试) |
| `cli/src/arch_cli/client.py` | `ArchClient.report_fcr(name, fcr)` 方法 |
| `cli/src/arch_cli/commands/component.py` | `report-fcr` Click 子命令(`FloatRange(0.0, 1.0)`) |
| `cli/tests/test_z_fcr.py` | 新增(8 个测试) |
| `docs/fcr-metric.md` | 本文档 |
| `README.md` | metric 章节加 1 行引用 |
