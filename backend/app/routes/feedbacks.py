"""Feedback routes — GET + PATCH"""
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Feedback, FeedbackStatus
from ..schemas import FeedbackList, FeedbackOut, FeedbackUpdate
from ..auth import require_api_key

router = APIRouter()


# ===== 读操作(GET)=====


@router.get("", response_model=FeedbackList)
def list_feedbacks(
    status: Optional[FeedbackStatus] = None,
    version_id: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """列出反馈(默认按 status=open 优先)"""
    query = db.query(Feedback)
    if status:
        query = query.filter(Feedback.status == status)
    if version_id:
        query = query.filter(Feedback.version_id == version_id)
    total = query.count()
    items = query.order_by(Feedback.created_at.desc()).offset(offset).limit(limit).all()
    return {"items": items, "total": total}


@router.get("/{feedback_id}", response_model=FeedbackOut)
def get_feedback(feedback_id: str, db: Session = Depends(get_db)):
    """反馈明细(FB-I 修复:2026-06-21 加,让 /feedbacks/{id} 能访问详情)"""
    fb = db.query(Feedback).filter(Feedback.id == feedback_id).first()
    if not fb:
        raise HTTPException(404, "feedback not found")
    return fb


# ===== 写操作(PATCH)— Phase 1.1 =====


@router.patch(
    "/{feedback_id}",
    response_model=FeedbackOut,
    dependencies=[Depends(require_api_key)],
)
def update_feedback(
    feedback_id: str,
    payload: FeedbackUpdate,
    db: Session = Depends(get_db),
):
    """更新反馈状态/决策(需要 API Key)

    业务规则(CLAUDE.md 反馈原则闭环):
    - status 转 fixed/wontfix 前必须填 decision
    - 填 decision 自动设 decided_at
    """
    fb = db.query(Feedback).filter(Feedback.id == feedback_id).first()
    if not fb:
        raise HTTPException(404, "feedback not found")

    update_data = payload.model_dump(exclude_unset=True)
    for key, val in update_data.items():
        setattr(fb, key, val)

    # 转 closed 状态前必须填 decision
    new_status = fb.status
    if new_status in (FeedbackStatus.fixed, FeedbackStatus.wontfix) and not fb.decision:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"decision is required before status transitions to '{new_status.value}' (CLAUDE.md feedback principle closure)",
        )

    # 填 decision 自动设 decided_at
    if payload.decision is not None and not fb.decided_at:
        fb.decided_at = datetime.utcnow()

    db.commit()
    db.refresh(fb)
    return fb


# ===== 追溯链:Feedback ↔ Requirement(2026-06-21 Phase 1.2)=====


@router.get("/{feedback_id}/requirement")
def get_feedback_requirement(feedback_id: str, db: Session = Depends(get_db)):
    """反向追溯:Feedback → Requirement"""
    from ..models import Requirement
    from ..schemas import RequirementOut
    fb = db.query(Feedback).filter(Feedback.id == feedback_id).first()
    if not fb:
        raise HTTPException(404, "feedback not found")
    if not fb.requirement_id:
        raise HTTPException(404, "feedback has no linked requirement")
    req = db.query(Requirement).filter(Requirement.id == fb.requirement_id).first()
    if not req:
        raise HTTPException(404, "linked requirement not found")
    return RequirementOut.model_validate(req)


@router.post(
    "/{feedback_id}/link-requirement",
    dependencies=[Depends(require_api_key)],
)
def link_feedback_to_requirement(
    feedback_id: str,
    payload: dict,
    db: Session = Depends(get_db),
):
    """显式回链 feedback → requirement(避免 FeedbackCreate schema 变更)"""
    from ..models import Requirement
    from ..schemas import RequirementLinkFeedback
    fb = db.query(Feedback).filter(Feedback.id == feedback_id).first()
    if not fb:
        raise HTTPException(404, "feedback not found")
    parsed = RequirementLinkFeedback(**payload)
    req = db.query(Requirement).filter(Requirement.id == parsed.requirement_id).first()
    if not req:
        raise HTTPException(422, f"requirement '{parsed.requirement_id}' not found")
    fb.requirement_id = req.id
    db.commit()
    db.refresh(fb)
    return {"feedback_id": fb.id, "requirement_id": fb.requirement_id}


@router.delete(
    "/{feedback_id}/link-requirement",
    dependencies=[Depends(require_api_key)],
)
def unlink_feedback_from_requirement(feedback_id: str, db: Session = Depends(get_db)):
    """取消回链"""
    fb = db.query(Feedback).filter(Feedback.id == feedback_id).first()
    if not fb:
        raise HTTPException(404, "feedback not found")
    fb.requirement_id = None
    db.commit()
    db.refresh(fb)
    return {"feedback_id": fb.id, "requirement_id": None}