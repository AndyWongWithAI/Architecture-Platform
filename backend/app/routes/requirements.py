"""Requirement routes — Phase 1 需求登记 + 状态流转

业务规则(对齐 CLAUDE.md 反馈原则的代码硬编码模式):
- 8 状态机:draft → triaged → scheduled → in_progress → implemented → verified | rejected | cancelled
- 转换矩阵 ALLOWED_TRANSITIONS 集中定义,违反 → 422
- draft → triaged 必填 assignee
- implemented → verified 要求 component 有 current_version_id
- 任意 → rejected/cancelled 必填 description
- 进入终态自动写 closed_at;离开 draft 自动写 decided_at
- 软删除走独立 is_archived 字段(不污染状态机)
"""
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import (
    Requirement, RequirementStatus, Component, Feedback, Version,
)
from ..schemas import (
    RequirementList, RequirementOut, RequirementCreate, RequirementUpdate,
    FeedbackList, StateMachineErrorDetail,
)
from ..auth import require_api_key

router = APIRouter()


# 状态机转换矩阵(集中定义,违反 → 422)
ALLOWED_TRANSITIONS = {
    RequirementStatus.draft: {RequirementStatus.triaged, RequirementStatus.cancelled},
    RequirementStatus.triaged: {RequirementStatus.scheduled, RequirementStatus.rejected, RequirementStatus.draft},
    RequirementStatus.scheduled: {RequirementStatus.in_progress, RequirementStatus.rejected, RequirementStatus.cancelled},
    RequirementStatus.in_progress: {RequirementStatus.implemented, RequirementStatus.cancelled},
    RequirementStatus.implemented: {RequirementStatus.verified, RequirementStatus.in_progress},
    RequirementStatus.verified: {RequirementStatus.complete, RequirementStatus.triaged, RequirementStatus.rejected},
    RequirementStatus.complete: set(),
    RequirementStatus.rejected: set(),
    RequirementStatus.cancelled: set(),
}

TERMINAL_STATUSES = {
    RequirementStatus.verified,
    RequirementStatus.complete,
    RequirementStatus.rejected,
    RequirementStatus.cancelled,
}


def _build_transition_suggestion(
    current: RequirementStatus,
    attempted: RequirementStatus,
    allowed: set,
) -> str:
    """生成 422 错误的 suggestion 文案 — 让 subagent 知道下一步该走哪个状态

    策略:
    - 终止态 (verified/rejected/cancelled) 且 attempted 仍在 set 外 → 建议 reopen(超出 API 范围,人工)
    - 单步可达 (attempted 在 ALLOWED_TRANSITIONS 之外的合法下一态路径上) → 给出最近中间态
    - 多步路径 → 列出从头到尾的链路
    """
    cur = current.value
    att = attempted.value

    # 终止态直接拒(verified 是中间态→complete,不算终态)
    if current in TERMINAL_STATUSES and current != RequirementStatus.verified:
        return (
            f"需求已处于终止态 '{cur}',无法流转。"
            f"如需 reopen,请走管理员通道(API 当前不支持)。"
        )

    # allowed 里有当前尝试态的中间态 → 提示先到中间态
    if allowed:
        # 按状态机主推进顺序排序,优先提示主路径上的下一态
        MAIN_PATH = [
            RequirementStatus.draft,
            RequirementStatus.triaged,
            RequirementStatus.scheduled,
            RequirementStatus.in_progress,
            RequirementStatus.implemented,
            RequirementStatus.verified,
            RequirementStatus.complete,
        ]
        sorted_allowed = sorted(
            allowed,
            key=lambda s: MAIN_PATH.index(s) if s in MAIN_PATH else 99,
        )
        next_step = sorted_allowed[0]
        if len(sorted_allowed) == 1:
            return (
                f"状态机不允许 '{cur}' → '{att}' 的直跳。"
                f"请先将状态置为 '{next_step.value}',再推进到 '{att}'。"
            )
        else:
            allowed_list = " / ".join(s.value for s in sorted_allowed)
            return (
                f"状态机不允许 '{cur}' → '{att}' 的直跳。"
                f"允许的下一态:{allowed_list}。"
                f"建议先置为 '{next_step.value}',再继续推进。"
            )

    # 走到这里:current 不是终止态但 allowed 为空(理论上不应发生,兜底)
    return f"状态 '{cur}' 当前无可用下一态,无法流转。"


def _raise_transition_error(
    req: Requirement,
    new_status: RequirementStatus,
    allowed: set,
):
    """统一的 422 状态机错误抛出器 — FB-b6311cf6 增强版

    body 包含:
    - detail: 人类可读的总结(向后兼容旧 detail 字段)
    - current_status / attempted_status: 当前与尝试状态
    - allowed_transitions: 合法下一态列表(空 = terminal)
    - state_machine_doc: SOP 链接
    - suggestion: 具体路径建议
    """
    allowed_list = sorted(s.value for s in allowed)
    suggestion = _build_transition_suggestion(req.status, new_status, allowed)
    detail = StateMachineErrorDetail(
        current_status=req.status.value,
        attempted_status=new_status.value,
        allowed_transitions=allowed_list,
        suggestion=suggestion,
    )
    # FastAPI 的 HTTPException(detail=...) 会把 dict 序列化成 JSON
    # 但这里我们用 Pydantic model,需要先 model_dump
    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail=detail.model_dump(),
    )


def _gen_uuid() -> str:
    return str(uuid.uuid4())


def _resolve_component(db: Session, identifier: str) -> Optional[Component]:
    """支持 id 或 name 解析 component"""
    return db.query(Component).filter(
        (Component.id == identifier) | (Component.name == identifier)
    ).first()


def _validate_transition(
    req: Requirement,
    new_status: RequirementStatus,
    payload: RequirementUpdate,
    db: Session,  # fix FB-98bc3a4c:db 之前未注入导致 verified transition 500
):
    """校验状态流转 + 必填字段"""
    allowed = ALLOWED_TRANSITIONS.get(req.status, set())
    if new_status not in allowed:
        _raise_transition_error(req, new_status, allowed)
    # draft → triaged 必填 assignee
    if new_status == RequirementStatus.triaged:
        new_assignee = payload.assignee if payload.assignee is not None else req.assignee
        if not new_assignee:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "assignee is required to transition to 'triaged'",
            )
    # implemented → verified 要求 component 有 current_version_id
    if new_status == RequirementStatus.verified and req.component_id:
        comp = db.query(Component).filter(Component.id == req.component_id).first()
        if not comp or not comp.current_version_id:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "verified requires component to have a registered version",
            )
    # 任意 → rejected/cancelled 必填 description
    if new_status in (RequirementStatus.rejected, RequirementStatus.cancelled):
        new_desc = payload.description if payload.description is not None else req.description
        if not new_desc:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                f"description is required to transition to '{new_status.value}'",
            )
    # verified → triaged/rejected 必填 reason(REQ-69212ee4:打回重新评估)
    if req.status == RequirementStatus.verified and new_status in (
        RequirementStatus.triaged,
        RequirementStatus.rejected,
    ):
        new_reason = payload.reason
        if not new_reason or len(new_reason.strip()) < 10:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                f"reason (>=10 chars) is required to transition from 'verified' to '{new_status.value}'",
            )


# ===== 读操作 =====

@router.get("", response_model=RequirementList)
def list_requirements(
    status: Optional[RequirementStatus] = Query(None),
    priority: Optional[str] = Query(None),
    type: Optional[str] = Query(None, alias="type"),
    assignee: Optional[str] = Query(None),
    component_id: Optional[str] = Query(None),
    proposer: Optional[str] = Query(None),
    q: Optional[str] = Query(None, description="title LIKE 模糊搜索"),
    include_archived: bool = Query(False),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """列出需求(支持多维过滤)"""
    query = db.query(Requirement)
    if status:
        query = query.filter(Requirement.status == status)
    if priority:
        query = query.filter(Requirement.priority == priority)
    if type:
        query = query.filter(Requirement.type == type)
    if assignee:
        query = query.filter(Requirement.assignee == assignee)
    if component_id:
        query = query.filter(Requirement.component_id == component_id)
    if proposer:
        query = query.filter(Requirement.proposer == proposer)
    if q:
        query = query.filter(Requirement.title.contains(q))
    if not include_archived:
        query = query.filter(Requirement.is_archived == False)  # noqa: E712
    total = query.count()
    items = query.order_by(
        Requirement.priority.asc(),  # P0 < P1 < P2 < P3
        Requirement.created_at.desc(),
    ).offset(offset).limit(limit).all()
    return {"items": items, "total": total}


@router.get("/{req_id}", response_model=RequirementOut)
def get_requirement(req_id: str, db: Session = Depends(get_db)):
    """需求详情"""
    req = db.query(Requirement).filter(Requirement.id == req_id).first()
    if not req:
        raise HTTPException(404, "requirement not found")
    return req


@router.get("/{req_id}/feedbacks", response_model=FeedbackList)
def get_requirement_feedbacks(req_id: str, db: Session = Depends(get_db)):
    """追溯链:Requirement → Component.versions → Feedback"""
    req = db.query(Requirement).filter(Requirement.id == req_id).first()
    if not req:
        raise HTTPException(404, "requirement not found")
    if not req.component_id:
        return {"items": [], "total": 0}
    comp = db.query(Component).filter(Component.id == req.component_id).first()
    if not comp:
        return {"items": [], "total": 0}
    version_ids = [v.id for v in comp.versions]
    if not version_ids:
        return {"items": [], "total": 0}
    items = (
        db.query(Feedback)
        .filter(Feedback.version_id.in_(version_ids))
        .order_by(Feedback.created_at.desc())
        .all()
    )
    return {"items": items, "total": len(items)}


# ===== 写操作 =====

@router.post(
    "",
    response_model=RequirementOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_api_key)],
)
def create_requirement(payload: RequirementCreate, db: Session = Depends(get_db)):
    """创建需求(平铺入口,component_id 可选)"""
    return _create_requirement_impl(db, payload)


@router.patch(
    "/{req_id}",
    response_model=RequirementOut,
    dependencies=[Depends(require_api_key)],
)
def update_requirement(
    req_id: str,
    payload: RequirementUpdate,
    db: Session = Depends(get_db),
):
    """更新需求:状态流转 + 字段更新"""
    req = db.query(Requirement).filter(Requirement.id == req_id).first()
    if not req:
        raise HTTPException(404, "requirement not found")
    if req.is_archived:
        raise HTTPException(422, "cannot update archived requirement; restore first")

    update_data = payload.model_dump(exclude_unset=True)

    # title 业务规则:仅 draft 时可改(对齐 Component.positioning 不可变原则)
    if "title" in update_data and req.status != RequirementStatus.draft:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "title can only be modified when status=draft (CLAUDE.md positioning stability)",
        )

    # 状态流转校验
    new_status = update_data.get("status", req.status)
    if "status" in update_data and update_data["status"] != req.status:
        _validate_transition(req, update_data["status"], payload, db)  # fix FB-98bc3a4c:传 db

    # 应用字段
    for key, val in update_data.items():
        setattr(req, key, val)

    # REQ-69212ee4:verified → triaged/rejected 时把 reason 拼到 description 末尾 + 写 decided_at
    if (
        "status" in update_data
        and req.status in (RequirementStatus.triaged, RequirementStatus.rejected)
        and payload.reason
    ):
        reason_text = payload.reason.strip()
        separator = "\n---\nreason: "
        if req.description:
            req.description = f"{req.description}{separator}{reason_text}"
        else:
            req.description = f"reason: {reason_text}"
        # 打回时也写 decided_at(打回 = 重新评估的决策点)
        if not req.decided_at:
            req.decided_at = datetime.utcnow()

    # 触发器:离开 draft 写 decided_at
    if "status" in update_data and req.status != RequirementStatus.draft and not req.decided_at:
        req.decided_at = datetime.utcnow()

    # 触发器:进入终态写 closed_at
    if "status" in update_data and req.status in TERMINAL_STATUSES and not req.closed_at:
        req.closed_at = datetime.utcnow()

    db.commit()
    db.refresh(req)
    return req


@router.delete(
    "/{req_id}",
    dependencies=[Depends(require_api_key)],
)
def archive_requirement(req_id: str, db: Session = Depends(get_db)):
    """软删除需求(置 is_archived=True)"""
    req = db.query(Requirement).filter(Requirement.id == req_id).first()
    if not req:
        raise HTTPException(404, "requirement not found")
    if req.status == RequirementStatus.verified:
        raise HTTPException(
            422,
            "cannot archive verified requirement; transition to rejected/cancelled instead",
        )
    req.is_archived = True
    db.commit()
    return {"id": req.id, "is_archived": True}


@router.post(
    "/{req_id}/restore",
    response_model=RequirementOut,
    dependencies=[Depends(require_api_key)],
)
def restore_requirement(req_id: str, db: Session = Depends(get_db)):
    """撤销软删除"""
    req = db.query(Requirement).filter(Requirement.id == req_id).first()
    if not req:
        raise HTTPException(404, "requirement not found")
    req.is_archived = False
    db.commit()
    db.refresh(req)
    return req


# ===== 内部辅助(供 components.py 嵌套路由复用) =====

def _create_requirement_impl(db: Session, payload: RequirementCreate) -> Requirement:
    """创建需求的实际实现,供平铺 + 嵌套入口共享"""
    if payload.component_id:
        comp = _resolve_component(db, payload.component_id)
        if not comp:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                f"component '{payload.component_id}' not found",
            )
        comp_id = comp.id
    else:
        comp_id = None

    req = Requirement(
        id=_gen_uuid(),
        component_id=comp_id,
        title=payload.title,
        description=payload.description,
        user_story=payload.user_story,
        acceptance_criteria=[ac.model_dump() for ac in payload.acceptance_criteria],
        nfr=payload.nfr,
        type=payload.type,
        priority=payload.priority,
        proposer="api",  # API 创建时默认;CLI/MCP/Web UI 在各自层覆盖
        assignee=payload.assignee,
        due_date=payload.due_date,
        tags=payload.tags,
    )
    db.add(req)
    db.commit()
    db.refresh(req)
    return req