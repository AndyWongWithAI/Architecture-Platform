"""SQLAlchemy ORM models — 对应 OpenAPI spec 4 个核心实体"""
import enum
import uuid
from datetime import datetime
from sqlalchemy import (
    Column, String, Text, Boolean, DateTime, Enum, JSON, ForeignKey, Index, Float, Integer,
)
from sqlalchemy.orm import relationship
from .database import Base


def gen_uuid():
    return str(uuid.uuid4())


def now_utc():
    return datetime.utcnow()


# ===== Enums(对应 OpenAPI spec)=====
class Layer(str, enum.Enum):
    L0_infrastructure = "L0_infrastructure"
    L1_platform = "L1_platform"
    L2_capability = "L2_capability"
    L3_application = "L3_application"


class Category(str, enum.Enum):
    auth = "auth"; db = "db"; cache = "cache"; queue = "queue"
    log = "log"; deploy = "deploy"; monitor = "monitor"
    ui = "ui"; util = "util"; other = "other"


class ComponentStatus(str, enum.Enum):
    draft = "draft"; stable = "stable"
    deprecated = "deprecated"; archived = "archived"


class Scope(str, enum.Enum):
    app = "app"; infra = "infra"; lib = "lib"; tool = "tool"


class Language(str, enum.Enum):
    python = "python"; typescript = "typescript"; javascript = "javascript"
    go = "go"; rust = "rust"; shell = "shell"; sql = "sql"; other = "other"


class DistributionForm(str, enum.Enum):
    package = "package"; container = "container"; binary = "binary"
    source = "source"; http_api = "http_api"; schema = "schema"
    dataset = "dataset"; config_template = "config_template"
    iac = "iac"; skill = "skill"; tool = "tool"


class SemverIntent(str, enum.Enum):
    major = "major"; minor = "minor"; patch = "patch"


class DeploymentEnv(str, enum.Enum):
    dev = "dev"; staging = "staging"; prod = "prod"


class FeedbackSeverity(str, enum.Enum):
    low = "low"; medium = "medium"; high = "high"; critical = "critical"


class FeedbackStatus(str, enum.Enum):
    open = "open"; triaged = "triaged"; fixing = "fixing"
    fixed = "fixed"; wontfix = "wontfix"


class FeedbackDecision(str, enum.Enum):
    optimize = "optimize"; fork_new = "fork_new"
    keep_as_is = "keep_as_is"; reassess_form = "reassess_form"


class RuntimeDependencyRelation(str, enum.Enum):
    """runtime_dependency 字段的 relation 取值(ADR-0001 决策 4)
    - orchestration: 上层编排下层(等价于跨层调用,LayeringCheck 仅校验「禁止向上」)
    - peer: 同层协作(仅 L2 编排型亚层 + cross_cutting 白名单允许)
    - deployment: 部署/物理依赖(L3 可直接引用 L1/L0,见 CLAUDE.md 分层原则)
    """
    orchestration = "orchestration"
    peer = "peer"
    deployment = "deployment"


# ===== Requirement (Phase 1 需求登记) =====
class RequirementType(str, enum.Enum):
    new_feature = "new_feature"
    bug_fix = "bug_fix"
    refactor = "refactor"
    optimization = "optimization"
    compliance = "compliance"
    tech_debt = "tech_debt"


class RequirementPriority(str, enum.Enum):
    P0 = "P0"; P1 = "P1"; P2 = "P2"; P3 = "P3"


class RequirementStatus(str, enum.Enum):
    draft = "draft"
    triaged = "triaged"
    scheduled = "scheduled"
    in_progress = "in_progress"
    implemented = "implemented"
    verified = "verified"
    rejected = "rejected"
    cancelled = "cancelled"


# ===== Component =====
class Component(Base):
    __tablename__ = "components"

    id = Column(String, primary_key=True, default=gen_uuid)
    name = Column(String, unique=True, nullable=False, index=True)
    title = Column(String, nullable=False)
    positioning = Column(Text, nullable=False)
    category = Column(Enum(Category), nullable=False)
    scope = Column(Enum(Scope), nullable=False)
    layer = Column(Enum(Layer), nullable=False, index=True)
    status = Column(Enum(ComponentStatus), default=ComponentStatus.draft, nullable=False, index=True)

    atomic = Column(Boolean, default=True, nullable=False)
    composed_of = Column(JSON, default=list)

    # ADR-0001 决策 2/3/4:sub_layer / cross_cutting / runtime_dependency 三字段
    sub_layer = Column(String)  # orchestration / normal / None
    cross_cutting = Column(Boolean, default=False, nullable=False, index=True)
    runtime_dependency = Column(JSON, default=list)

    tags = Column(JSON, default=list)
    repo_url = Column(String)
    language = Column(Enum(Language))
    package_name = Column(String)
    install_command = Column(Text)
    usage_example = Column(Text)

    # 资产判定(CLAUDE.md 资产原则)
    is_asset = Column(Boolean, default=True, nullable=False, index=True)
    distribution_form = Column(Enum(DistributionForm))
    interface_contract = Column(Text)
    knowledge_artifact = Column(Boolean, default=False, nullable=False)

    current_version_id = Column(String, ForeignKey("versions.id", use_alter=True, name="fk_component_current_version"))

    created_at = Column(DateTime, default=now_utc, nullable=False)
    updated_at = Column(DateTime, default=now_utc, onupdate=now_utc, nullable=False)

    versions = relationship("Version", back_populates="component",
                            foreign_keys="Version.component_id",
                            cascade="all, delete-orphan")
    current_version = relationship("Version", foreign_keys=[current_version_id],
                                   post_update=True)


# ===== Version =====
class Version(Base):
    __tablename__ = "versions"

    id = Column(String, primary_key=True, default=gen_uuid)
    component_id = Column(String, ForeignKey("components.id"), nullable=False, index=True)
    version = Column(String, nullable=False)
    semver_intent = Column(Enum(SemverIntent), nullable=False)
    design_doc = Column(Text)
    design_decided_at = Column(DateTime)
    replaces_version = Column(String)
    changelog = Column(Text, nullable=False)
    breaking_changes = Column(Text)
    deprecates = Column(JSON, default=list)
    compatibility_window = Column(String)
    created_at = Column(DateTime, default=now_utc, nullable=False)

    component = relationship("Component", back_populates="versions",
                             foreign_keys=[component_id])
    deployments = relationship("Deployment", back_populates="version",
                               cascade="all, delete-orphan")
    feedbacks = relationship("Feedback", back_populates="version",
                             cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_version_component_version", "component_id", "version", unique=True),
        Index("idx_version_semver_intent", "semver_intent"),
    )


# ===== Deployment =====
class Deployment(Base):
    __tablename__ = "deployments"

    id = Column(String, primary_key=True, default=gen_uuid)
    version_id = Column(String, ForeignKey("versions.id"), nullable=False, index=True)
    env = Column(Enum(DeploymentEnv), nullable=False, index=True)
    host = Column(String, nullable=False)
    deploy_path = Column(String, nullable=False)
    config_hash = Column(String)
    deployed_by = Column(String, nullable=False)
    deployed_at = Column(DateTime, default=now_utc, nullable=False)
    rollback_to = Column(String)
    resolved_versions = Column(JSON)
    lockfile_hash = Column(String)
    build_reproducible = Column(Boolean, default=False)

    version = relationship("Version", back_populates="deployments")

    __table_args__ = (
        Index("idx_deployment_host_time", "host", "deployed_at"),
    )


# ===== Feedback =====
class Feedback(Base):
    __tablename__ = "feedbacks"

    id = Column(String, primary_key=True, default=gen_uuid)
    version_id = Column(String, ForeignKey("versions.id"), nullable=False, index=True)
    reporter = Column(String, nullable=False)
    bug_summary = Column(Text, nullable=False)
    root_cause = Column(Text)
    fix_plan = Column(Text)
    severity = Column(Enum(FeedbackSeverity), nullable=False, index=True)
    status = Column(Enum(FeedbackStatus), default=FeedbackStatus.open, nullable=False, index=True)
    decision = Column(Enum(FeedbackDecision))
    reused_in_projects = Column(JSON, default=list)
    decided_at = Column(DateTime)
    created_at = Column(DateTime, default=now_utc, nullable=False)
    # 追溯链:反馈可显式回链到它触发的需求(nullable,不破坏现有数据)
    requirement_id = Column(String, ForeignKey("requirements.id"), index=True)

    version = relationship("Version", back_populates="feedbacks")


# ===== Requirement =====
class Requirement(Base):
    __tablename__ = "requirements"

    id = Column(String, primary_key=True, default=gen_uuid)
    component_id = Column(String, ForeignKey("components.id"), index=True)
    title = Column(String, nullable=False)
    description = Column(Text)
    user_story = Column(Text)
    acceptance_criteria = Column(JSON, default=list)
    nfr = Column(JSON, default=dict)
    type = Column(Enum(RequirementType), nullable=False, index=True)
    priority = Column(Enum(RequirementPriority), default=RequirementPriority.P2, nullable=False, index=True)
    status = Column(Enum(RequirementStatus), default=RequirementStatus.draft, nullable=False, index=True)
    proposer = Column(String, nullable=False, index=True)
    assignee = Column(String, index=True)
    due_date = Column(DateTime)
    tags = Column(JSON, default=list)
    decided_at = Column(DateTime)
    closed_at = Column(DateTime)
    # 软删除独立 bool,不污染状态机 enum(对齐 Component.archived 的隔离原则)
    is_archived = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=now_utc, nullable=False)
    updated_at = Column(DateTime, default=now_utc, onupdate=now_utc, nullable=False)

    component = relationship("Component")
    # 通过 backref 让 Feedback 反向访问 requirement_id

    __table_args__ = (
        Index("idx_req_status_priority", "status", "priority"),
        Index("idx_req_component_status", "component_id", "status"),
        Index("idx_req_assignee_status", "assignee", "status"),
    )

# ===== Doubt-Driven Development(2026-06-21 新增)=====

class DoubtVerdict(str, enum.Enum):
    """doubt cycle 终态判定"""
    pass_ = "pass"             # 证据支持决策,无需修改
    fail = "fail"              # 证据反驳决策,需要修改
    needs_more_evidence = "needs_more_evidence"  # 证据不足,需要更多信息


class DoubtFindingCategory(str, enum.Enum):
    """finding 4 类分类(对齐 doubt-driven-development RECONCILE 步骤)"""
    contract_misread = "contract_misread"  # reviewer 因为 contract 不清误报
    actionable = "actionable"              # 真问题 → 改 artifact
    trade_off = "trade_off"                # 真问题但修比不改贵 → 显式记录
    noise = "noise"                        # reviewer 缺上下文


class DoubtFindingSeverity(str, enum.Enum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class DoubtCycle(Base):
    """doubt cycle(CLAIM → EXTRACT → DOUBT → RECONCILE → STOP)"""
    __tablename__ = "doubt_cycles"

    id = Column(String, primary_key=True, default=gen_uuid)
    claim = Column(Text, nullable=False)         # 2-3 行声明
    artifact = Column(Text, nullable=False)      # 代码/决策/断言(可贴代码或文件路径)
    contract = Column(Text, nullable=False)      # 期望行为/验收标准
    verdict = Column(Enum(DoubtVerdict), index=True)
    score = Column(Float)                          # 0.0-1.0
    next_step = Column(Text)                       # 建议下一步动作
    cycle_count = Column(Integer, default=0, nullable=False)  # 当前 cycle 轮次
    max_cycles = Column(Integer, default=3, nullable=False)
    stopped_reason = Column(String)                # 用户主动 ship / 3 轮跑完 / trivial
    component_id = Column(String, ForeignKey("components.id"), index=True)  # 可选关联
    created_by = Column(String, nullable=False, index=True)  # 谁创建的(人 / agent)
    created_at = Column(DateTime, default=now_utc, nullable=False)
    stopped_at = Column(DateTime)

    findings = relationship("DoubtFinding", back_populates="cycle",
                            cascade="all, delete-orphan",
                            order_by="DoubtFinding.created_at")

    __table_args__ = (
        Index("idx_doubt_verdict_created", "verdict", "created_at"),
    )


class DoubtFinding(Base):
    """doubt cycle 内的 finding(RECONCILE 步骤分类)"""
    __tablename__ = "doubt_findings"

    id = Column(String, primary_key=True, default=gen_uuid)
    cycle_id = Column(String, ForeignKey("doubt_cycles.id"), nullable=False, index=True)
    category = Column(Enum(DoubtFindingCategory), nullable=False, index=True)
    severity = Column(Enum(DoubtFindingSeverity), nullable=False, default=DoubtFindingSeverity.medium, index=True)
    description = Column(Text, nullable=False)
    created_at = Column(DateTime, default=now_utc, nullable=False)

    cycle = relationship("DoubtCycle", back_populates="findings")
