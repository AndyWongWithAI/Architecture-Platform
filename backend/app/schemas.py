"""Pydantic schemas — API 契约(对应 OpenAPI spec)"""
from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, ConfigDict

from .models import (
    Layer, Category, ComponentStatus, Scope, Language,
    DistributionForm, SemverIntent, DeploymentEnv,
    FeedbackSeverity, FeedbackStatus, FeedbackDecision,
    RuntimeDependencyRelation,
    RequirementType, RequirementPriority, RequirementStatus,
)


# ===== 通用 =====
class ORMBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ===== Component =====
class ComposedOfEntry(BaseModel):
    component_id: str
    version_constraint: str
    # ADR-0001 决策 4:runtime_dependency 复用 ComposedOfEntry 结构 + relation 字段
    # composed_of 留 None(代码层 import 隐含 relation=code_import);
    # runtime_dependency 必填 relation(orchestration/peer/deployment)
    relation: Optional[RuntimeDependencyRelation] = None


class ComponentBase(BaseModel):
    name: str = Field(..., pattern=r"^[a-z][a-z0-9.-]*$", min_length=2, max_length=64)
    title: str = Field(..., max_length=128)
    positioning: str = Field(..., min_length=10, max_length=500)
    category: Category
    scope: Scope
    layer: Layer
    atomic: bool = True
    composed_of: List[ComposedOfEntry] = []
    # ADR-0001 决策 2:sub_layer 标记 orchestration/normal,不改 Layer 枚举
    sub_layer: Optional[str] = Field(None, pattern=r"^(orchestration|normal)$")
    # ADR-0001 决策 3:cross_cutting 白名单豁免(audit/consolidate-claude 等横切关注点)
    cross_cutting: bool = False
    # ADR-0001 决策 4:runtime_dependency 追踪 skill 间运行时/编排依赖,与 composed_of 正交
    runtime_dependency: List[ComposedOfEntry] = []
    tags: List[str] = []
    repo_url: Optional[str] = None
    language: Optional[Language] = None
    package_name: Optional[str] = None
    install_command: Optional[str] = None
    usage_example: Optional[str] = None
    is_asset: bool = True
    distribution_form: Optional[DistributionForm] = None
    interface_contract: Optional[str] = None
    knowledge_artifact: bool = False


class ComponentCreate(ComponentBase):
    pass


class ComponentUpdate(BaseModel):
    title: Optional[str] = None
    category: Optional[Category] = None
    status: Optional[ComponentStatus] = None
    tags: Optional[List[str]] = None
    repo_url: Optional[str] = None
    language: Optional[Language] = None
    package_name: Optional[str] = None
    install_command: Optional[str] = None
    usage_example: Optional[str] = None
    is_asset: Optional[bool] = None
    distribution_form: Optional[DistributionForm] = None
    interface_contract: Optional[str] = None
    knowledge_artifact: Optional[bool] = None
    # FB-38f2024f + REQ-f8fa2992:补 composed_of 字段,使 PATCH 能与 Create/Out 对齐
    composed_of: Optional[List[ComposedOfEntry]] = None
    # ADR-0001:同步 PATCH 支持新字段(向后兼容,Optional)
    sub_layer: Optional[str] = Field(None, pattern=r"^(orchestration|normal)$")
    cross_cutting: Optional[bool] = None
    runtime_dependency: Optional[List[ComposedOfEntry]] = None
    # FB-38f2024f 续:补 atomic 字段(否则 PATCH composed_of 时业务规则
    # 永远看到旧 atomic=True → "atomic=true requires composed_of to be empty" 422)
    atomic: Optional[bool] = None


class ComponentOut(ComponentBase, ORMBase):
    id: str
    status: ComponentStatus
    current_version_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class ComponentDetail(ComponentOut):
    versions: List["VersionOut"] = []


class ComponentList(BaseModel):
    items: List[ComponentOut]
    total: int


class ComponentTreeNode(BaseModel):
    component: ComponentOut
    children: List["ComponentTreeNode"] = []


ComponentTreeNode.model_rebuild()


class ComponentUsage(BaseModel):
    component: ComponentOut
    install_command: Optional[str] = None
    usage_example: Optional[str] = None
    current_version: Optional[str] = None


# ===== Version =====
class DeprecateEntry(BaseModel):
    api: str
    replacement: str
    remove_in: str


class VersionCreate(BaseModel):
    version: str = Field(..., pattern=r"^\d+\.\d+\.\d+")
    semver_intent: SemverIntent
    design_doc: Optional[str] = None
    replaces_version: Optional[str] = None
    changelog: str
    breaking_changes: Optional[str] = None
    deprecates: List[DeprecateEntry] = []
    compatibility_window: Optional[str] = None


class VersionUpdate(BaseModel):
    """版本 PATCH 字段(2026-06-21 新增)"""
    design_doc: Optional[str] = None
    changelog: Optional[str] = None
    compatibility_window: Optional[str] = None
    deprecates: Optional[List[DeprecateEntry]] = None


class VersionOut(VersionCreate, ORMBase):
    id: str
    component_id: str
    created_at: datetime


class VersionList(BaseModel):
    items: List["VersionOut"]
    total: int


# ===== Deployment =====
class DeploymentCreate(BaseModel):
    env: DeploymentEnv
    host: str
    deploy_path: str
    config_hash: Optional[str] = None
    deployed_by: str
    rollback_to: Optional[str] = None
    resolved_versions: Dict[str, str] = {}
    lockfile_hash: Optional[str] = None
    build_reproducible: bool = False


class DeploymentOut(DeploymentCreate, ORMBase):
    id: str
    version_id: str
    deployed_at: datetime


class DeploymentList(BaseModel):
    items: List[DeploymentOut]
    total: int


# ===== Feedback =====
class FeedbackCreate(BaseModel):
    reporter: str
    bug_summary: str = Field(..., min_length=5, max_length=500)
    root_cause: Optional[str] = None
    fix_plan: Optional[str] = None
    severity: FeedbackSeverity
    reused_in_projects: List[str] = []


class FeedbackUpdate(BaseModel):
    status: Optional[FeedbackStatus] = None
    decision: Optional[FeedbackDecision] = None
    root_cause: Optional[str] = None
    fix_plan: Optional[str] = None


class FeedbackOut(ORMBase):
    id: str
    version_id: str
    reporter: str
    bug_summary: str
    root_cause: Optional[str] = None
    fix_plan: Optional[str] = None
    severity: FeedbackSeverity
    status: FeedbackStatus
    decision: Optional[FeedbackDecision] = None
    reused_in_projects: List[str] = []
    decided_at: Optional[datetime] = None
    created_at: datetime
    # 追溯链:反馈可显式回链到触发的需求(nullable,2026-06-21 Phase 1 需求模块上线)
    requirement_id: Optional[str] = None


class FeedbackList(BaseModel):
    items: List[FeedbackOut]
    total: int


# ===== Requirement (Phase 1 需求登记) =====
class AcceptanceCriterion(BaseModel):
    given: str
    when: str
    then: str


class RequirementCreate(BaseModel):
    component_id: Optional[str] = None
    title: str = Field(..., min_length=20, max_length=200)
    description: Optional[str] = None
    user_story: Optional[str] = None
    acceptance_criteria: List[AcceptanceCriterion] = []
    nfr: Dict[str, str] = {}
    type: RequirementType
    priority: RequirementPriority = RequirementPriority.P2
    assignee: Optional[str] = None
    due_date: Optional[datetime] = None
    tags: List[str] = []


class RequirementUpdate(BaseModel):
    # title 业务规则校验:仅 status=draft 时可改(对齐 Component.positioning 不可变原则)
    title: Optional[str] = Field(None, min_length=20, max_length=200)
    description: Optional[str] = None
    # 2026-06-22 扩展:对齐 RequirementCreate,允许 PATCH 时补 user_story / AC / nfr
    # (此前 create 时一次性写入,但 update 锁住会导致 draft→triaged 流程无法完善 AC)
    user_story: Optional[str] = None
    acceptance_criteria: Optional[List[AcceptanceCriterion]] = None
    nfr: Optional[Dict[str, str]] = None
    priority: Optional[RequirementPriority] = None
    status: Optional[RequirementStatus] = None
    assignee: Optional[str] = None
    due_date: Optional[datetime] = None
    tags: Optional[List[str]] = None


class RequirementOut(ORMBase):
    id: str
    component_id: Optional[str] = None
    title: str
    description: Optional[str] = None
    user_story: Optional[str] = None
    acceptance_criteria: List[AcceptanceCriterion] = []
    nfr: Dict[str, str] = {}
    type: RequirementType
    priority: RequirementPriority
    status: RequirementStatus
    proposer: str
    assignee: Optional[str] = None
    due_date: Optional[datetime] = None
    tags: List[str] = []
    decided_at: Optional[datetime] = None
    closed_at: Optional[datetime] = None
    is_archived: bool = False
    created_at: datetime
    updated_at: datetime


class RequirementList(BaseModel):
    items: List[RequirementOut]
    total: int


class RequirementLinkFeedback(BaseModel):
    """显式回链 feedback(避免 FeedbackCreate schema 变更)"""
    requirement_id: str


# ===== 状态机错误响应 =====
# FB-b6311cf6 修复方案第 2 层:422 body 增强,帮 subagent 自我修正
# - allowed_transitions:从 ALLOWED_TRANSITIONS 表查出的合法下一态
# - state_machine_doc:SOP 链接(Phase 1.1 Requirement 状态机参考)
# - suggestion:针对当前 + 尝试态的明确路径建议(单步/多步/终止)
class StateMachineErrorDetail(BaseModel):
    """422 状态机错误的 detail schema — 嵌入 HTTPException(detail=...) 即可"""
    current_status: str
    attempted_status: str
    allowed_transitions: List[str] = []
    state_machine_doc: str = (
        "file:///home/hq/.claude/specs/sdlc/SOP.md#phase-11-requirement-状态机参考"
    )
    suggestion: str


# ===== Search =====
class SearchResponse(BaseModel):
    components: List[ComponentOut]
    versions: List[VersionOut]
    feedbacks: List[FeedbackOut]
    total: int


# ===== Error =====
class Error(BaseModel):
    code: str
    message: str
    detail: Optional[Any] = None


ComponentDetail.model_rebuild()

# ===== Doubt-Driven Development(2026-06-21 新增)=====

class DoubtFindingCreate(BaseModel):
    category: str = Field(..., pattern=r"^(contract_misread|actionable|trade_off|noise)$")
    severity: str = Field(default="medium", pattern=r"^(low|medium|high|critical)$")
    description: str = Field(..., min_length=10, max_length=5000)


class DoubtFindingOut(DoubtFindingCreate, ORMBase):
    id: str
    cycle_id: str
    created_at: datetime


class DoubtCycleCreate(BaseModel):
    claim: str = Field(..., min_length=10, max_length=1000)
    artifact: str = Field(..., min_length=1, max_length=50000)
    contract: str = Field(..., min_length=10, max_length=5000)
    component_id: Optional[str] = None
    created_by: str = Field(default="web-ui", max_length=200)


class DoubtCycleStop(BaseModel):
    """STOP 步骤 payload"""
    reason: str = Field(..., min_length=3, max_length=500)


class DoubtCycleOut(DoubtCycleCreate, ORMBase):
    id: str
    verdict: Optional[str] = None
    score: Optional[float] = None
    next_step: Optional[str] = None
    cycle_count: int = 0
    max_cycles: int = 3
    stopped_reason: Optional[str] = None
    created_at: datetime
    stopped_at: Optional[datetime] = None
    findings: List[DoubtFindingOut] = []


# ===== Literature 知识资产(REQ-7c4bcb32,2026-06-23)=====

class LiteratureBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=500)
    authors: Optional[str] = Field(None, max_length=500)
    url: str = Field(..., min_length=1, max_length=2000)
    tags: List[str] = []
    summary: Optional[str] = None
    source: Optional[str] = Field(None, max_length=200)
    added_by: Optional[str] = Field(None, max_length=100)


class LiteratureCreate(LiteratureBase):
    pass


class LiteratureUpdate(BaseModel):
    """部分更新(对齐 FeedbackUpdate 风格)"""
    title: Optional[str] = Field(None, min_length=1, max_length=500)
    authors: Optional[str] = Field(None, max_length=500)
    url: Optional[str] = Field(None, min_length=1, max_length=2000)
    tags: Optional[List[str]] = None
    summary: Optional[str] = None
    source: Optional[str] = Field(None, max_length=200)


class LiteratureOut(LiteratureBase, ORMBase):
    id: str
    added_at: datetime
    is_archived: bool = False


class LiteratureList(BaseModel):
    items: List[LiteratureOut]
    total: int


# ===== Audit Module(REQ-7328c640, 2026-06-23)=====
# 数据契约对齐 scan.py --json 输出:
#   { ts, scope, gate, severity_min, summary: {total, blocker, warn, info}, findings: [...] }
# scan.py 输出里 findings 元素字段:
#   { principle, check, severity, scope, target, detail, fingerprint }


class AuditFindingCreate(BaseModel):
    """单条 finding(POST body 用)"""
    principle: str = Field(..., max_length=50)
    check: str = Field(..., max_length=100)
    severity: str = Field(..., pattern=r"^(info|warn|blocker)$")
    scope: Optional[str] = Field(None, max_length=50)
    target: Optional[str] = Field(None, max_length=500)
    detail: Optional[str] = None
    fingerprint: Optional[str] = Field(None, max_length=64)


class AuditFindingOut(AuditFindingCreate, ORMBase):
    id: str
    run_id: str


class AuditRunSummary(BaseModel):
    """scan.py --json 的 summary 字段"""
    total: int = 0
    blocker: int = 0
    warn: int = 0
    info: int = 0


class AuditRunCreate(BaseModel):
    """POST /api/v1/audit/runs 的请求体(直接对齐 scan.py --json 顶层)"""
    ts: Optional[str] = None
    scope: str = Field(..., max_length=50)
    gate: str = Field(..., pattern=r"^(soft|hard)$")
    severity_min: str = Field(..., pattern=r"^(info|warn|blocker)$")
    summary: AuditRunSummary = Field(default_factory=AuditRunSummary)
    findings: List[AuditFindingCreate] = []


class AuditRunOut(ORMBase):
    """单条 audit run 详情(不含 findings,避免大 payload)"""
    id: str
    started_at: datetime
    finished_at: Optional[datetime] = None
    scope: str
    gate: str
    severity_min: str
    status: str
    total: int = 0
    blocker_count: int = 0
    warn_count: int = 0
    info_count: int = 0
    error_message: Optional[str] = None
    scanner_ts: Optional[str] = None


class AuditRunDetail(AuditRunOut):
    """含 findings[] 的完整 payload"""
    findings: List[AuditFindingOut] = []


class AuditRunList(BaseModel):
    items: List[AuditRunOut]
    total: int


class AuditFindingList(BaseModel):
    items: List[AuditFindingOut]
    total: int
