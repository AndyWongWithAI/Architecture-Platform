"""SQLAlchemy ORM models — 对应 OpenAPI spec 4 个核心实体"""
import enum
import uuid
from datetime import datetime
from sqlalchemy import (
    Column, String, Text, Boolean, DateTime, Enum, JSON, ForeignKey, Index,
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

    version = relationship("Version", back_populates="feedbacks")