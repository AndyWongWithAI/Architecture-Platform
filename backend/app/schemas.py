"""Pydantic schemas — API 契约(对应 OpenAPI spec)"""
from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, ConfigDict

from .models import (
    Layer, Category, ComponentStatus, Scope, Language,
    DistributionForm, SemverIntent, DeploymentEnv,
    FeedbackSeverity, FeedbackStatus, FeedbackDecision,
)


# ===== 通用 =====
class ORMBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ===== Component =====
class ComposedOfEntry(BaseModel):
    component_id: str
    version_constraint: str


class ComponentBase(BaseModel):
    name: str = Field(..., pattern=r"^[a-z][a-z0-9.-]*$", min_length=2, max_length=64)
    title: str = Field(..., max_length=128)
    positioning: str = Field(..., min_length=10, max_length=500)
    category: Category
    scope: Scope
    layer: Layer
    atomic: bool = True
    composed_of: List[ComposedOfEntry] = []
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


class VersionOut(VersionCreate, ORMBase):
    id: str
    component_id: str
    created_at: datetime


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


class FeedbackList(BaseModel):
    items: List[FeedbackOut]
    total: int


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