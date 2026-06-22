# ADR-0022: Requirement 状态机 verified transition 注入 db session

- **状态**: accepted
- **日期**: 2026-06-22
- **触发事件**: `FB-98bc3a4c` (severity=high, status=fixed)
- **作者**: Claude
- **关联**: commit `21b7643` / CI run `27953928705` / arch-platform-backend v0.3.1

---

## 背景(Background)

架构平台 `Requirement` 状态机有 8 个状态(draft → triaged → scheduled → in_progress → implemented → verified / rejected / cancelled),其中 `implemented → verified` 路径有业务规则:**要求 component 有 current_version_id**。

实现该业务规则的代码在 `backend/app/routes/requirements.py` 的 `_validate_transition()` 函数中,需要查询 `component` 表。但该函数**未通过 FastAPI Depends 注入 db session**,直接引用了未定义的 `db` 变量。

### 触发事件(2026-06-21 ~ 22)

`FB-d3f61888`(2026-06-21 数据丢失事件)的后续 follow-up 需求 `REQ-fd7011ae`(seed 行为可见性,P1)落地时,被 AI 助手(本会话)推进到 verified 时**连续 5 次返回 500 Internal Server Error**。根因诊断发现 `_validate_transition()` 函数体内 `db.query(Component)` 引用了未注入的 `db` 局部变量,触发 `NameError`。

### 影响面

- 任何 `component_id` 非空 + `current_version_id` 存在的 requirement 推进到 verified 都会 500
- 任何 `component_id` 非空 + `current_version_id` 不存在的 requirement 推进到 verified **也无法**返回正确的 422(因为 db.query 先 500)
- `component_id` 为 null 的需求不受影响(走另一条路径,跳过 db.query)
- 直接影响:阻塞 `REQ-fd7011ae` 推进到终态 verified
- 间接影响:Phase 8 反馈闭环流程断链(bug 不能被记录为 fixed)

---

## 决策(Decision)

**修复方案**:`_validate_transition()` 函数签名加 `db: Session` 参数(沿用同文件内 `_resolve_component` 的模式),路由函数 `patch_requirement` 调用点传入 `db`。

```python
# 修复后(before: db 未声明)
def _validate_transition(
    req: Requirement,
    new_status: RequirementStatus,
    payload: RequirementUpdate,
    db: Session,  # 新增
) -> None:
    ...
    if new_status == RequirementStatus.verified and req.component_id:
        comp = db.query(Component).filter(Component.id == req.component_id).first()
        ...
```

**为什么选这个方案**:
- 跟同文件 `_resolve_component(db: Session, identifier: str)` 模式一致,代码风格统一
- 改动面最小(1 个函数签名 + 1 个调用点)
- 不引入新的 `Depends` 注入层级(辅助函数保持纯函数语义)

**为什么不选其他方案**:
- ~~用 `Depends(get_db)` 注入~~ — 辅助函数不是路由 handler,FastAPI 不会调用 Depends,会引入隐性错误
- ~~改成在外层预查 component 字典传入~~ — 增加调用方复杂度,且不利于未来加新的 component 字段
- ~~try/except 包住 db.query~~ — 治标不治本,隐藏了真正的问题

---

## 影响(Consequences)

### 正面
- 任何带 `component_id` 的 requirement 都能正常推进到 verified(200)
- 业务规则正确执行:有 version → 200,无 version → 422(都返回正确语义)
- 阻塞的 `REQ-fd7011ae` 可推进到终态
- 状态机 8 个转换路径全部可用,看板语义恢复

### 负面
- 无运行时性能影响(db query 计数不变)
- 无 API 兼容性影响(签名对外不变)

### 中性
- 函数签名变宽(多一个参数),后续需要 db 上下文的校验逻辑可以在此函数内继续添加

---

## 替代方案(Alternatives Considered)

### 方案 B:把 db.query 移到外层
在 `patch_requirement` 路由函数中先 `db.query` 查到 component 字典,传给 `_validate_transition`。**放弃原因**:增加调用方代码复杂度,跟同文件 `_resolve_component` 模式不一致。

### 方案 C:在辅助函数内部用 sessionmaker 直接开 session
```python
from ..database import SessionLocal
def _validate_transition(...):
    db = SessionLocal()
    ...
```
**放弃原因**:脱离 FastAPI 请求生命周期,事务边界不清晰,容易出现 session 泄漏。

### 方案 D:删除 `verified requires component to have a registered version` 业务规则
**放弃原因**:这条规则是 2026-06-20 设计有意为之 — verified 意味着该 component 真有版本上线,否则就成了"空 verified",污染看板语义。

---

## 复盘(Lessons Learned)

1. **FastAPI Depends 不会注入到辅助函数**:写辅助函数时,如果需要 db 访问,要**显式把 db 作为参数**,而不是假设外层注入了。这是 FastAPI + SQLAlchemy 项目常见的反模式。
2. **CI 没覆盖到带 component 的 verified 路径**:原 transition 测试 `test_patch_requirement_transition_success` 走的是 `draft → triaged`,跳过了 `implemented → verified`。**生产事故暴露了测试覆盖盲区**。
3. **Type hint 没有标 `db: Session`** — 如果用 mypy 静态检查,这个错误会在编译期发现。**未来改进**:为 `requirements.py` 路由层加 mypy strict 模式。
4. **AI 助手诊断时直接对生产 PATCH 5 次试图复现 bug** — 这违反了 SDLC 流程(数据修改类操作规范 2026-06-22 新增)。**已登记为 `FB-efcf7b44`,并写入 SOP 章节作为永久防护**。

---

## 关联(References)

- **代码**: `backend/app/routes/requirements.py:62, 218`
- **测试**: `backend/tests/test_smoke.py::test_patch_requirement_transition_verified_with_component_200`
- **Bug 反馈**: arch-platform feedback `FB-98bc3a4c` (severity=high, status=fixed)
- **Process 反馈**: arch-platform feedback `FB-efcf7b44` (severity=medium, status=fixed) — 数据修改流程违规
- **触发需求**: arch-platform requirement `REQ-fd7010ae` (seed 可见性, P1) — 阻塞方
- **新需求**: arch-platform requirement `REQ-290f0450` (SDLC 自动推进 status, P1, triaged)
- **SDLC 规范补充**: `~/.claude/specs/sdlc/SOP.md` §「数据修改类操作规范」(2026-06-22 新增)
- **相关 ADR**: 无(首个状态机相关 ADR)
