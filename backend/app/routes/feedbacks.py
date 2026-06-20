"""Feedback routes — GET"""
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Feedback, FeedbackStatus
from ..schemas import FeedbackList

router = APIRouter()


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