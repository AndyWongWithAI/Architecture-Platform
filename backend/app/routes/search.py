"""Search route — 跨 components/versions/feedbacks 的简单 LIKE 搜索

Phase 1.1 简化版:LIKE 实现。FTS5 后续(PG 迁移时升级为 tsvector)。
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Component, Version, Feedback
from ..schemas import SearchResponse, ComponentOut, VersionOut, FeedbackOut

router = APIRouter()


@router.get("/search")
def search(
    q: str = Query(..., min_length=1, max_length=200, description="关键词"),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> SearchResponse:
    """全文搜索:跨 components / versions / feedbacks

    匹配规则:
    - components: name / title / positioning / tags
    - versions: version / changelog / breaking_changes
    - feedbacks: bug_summary / root_cause
    """
    like = f"%{q}%"

    comps = db.query(Component).filter(
        or_(
            Component.name.like(like),
            Component.title.like(like),
            Component.positioning.like(like),
        )
    ).order_by(Component.layer, Component.name).limit(limit).all()

    # version.changelog 是 JSON 字符串,LIKE 在 SQLite 上工作但 PG 上要用 ->>
    vers = db.query(Version).filter(
        or_(
            Version.version.like(like),
            Version.changelog.like(like),
            Version.breaking_changes.like(like),
        )
    ).order_by(Version.created_at.desc()).limit(limit).all()

    fbs = db.query(Feedback).filter(
        or_(
            Feedback.bug_summary.like(like),
            Feedback.root_cause.like(like),
        )
    ).order_by(Feedback.created_at.desc()).limit(limit).all()

    return SearchResponse(
        components=comps,
        versions=vers,
        feedbacks=fbs,
        total=len(comps) + len(vers) + len(fbs),
    )