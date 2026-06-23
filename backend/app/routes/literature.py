"""Literature routes — 架构文献/论文收集(REQ-7c4bcb32,2026-06-23)

平台首例「知识资产」实体(CLAUDE.md 资产原则):
- 不挂在 component 上(component_id 可空),跨组件复用
- 人工登记 + 未来支持批量导入
- 软删除走 is_archived(对齐 Requirement 一致性)
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Literature
from ..schemas import LiteratureList, LiteratureOut, LiteratureCreate, LiteratureUpdate
from ..auth import require_api_key

router = APIRouter()


def _gen_uuid() -> str:
    import uuid
    return str(uuid.uuid4())


# ===== 读操作(GET,公开)=====


@router.get("", response_model=LiteratureList)
def list_literatures(
    q: Optional[str] = Query(None, description="title/authors/summary 模糊搜索"),
    tag: Optional[str] = Query(None, description="按 tag 过滤(任一命中)"),
    source: Optional[str] = Query(None, description="按 source 过滤"),
    include_archived: bool = Query(False),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """列出文献(支持 ?q=keyword&tag=xxx 过滤)

    搜索:title / authors / summary 任一 LIKE 命中
    tag 过滤:tags JSON list 中包含目标 tag(JSON contains 简化版:Python 端 in 过滤)
    """
    query = db.query(Literature)
    if q:
        like = f"%{q}%"
        query = query.filter(
            (Literature.title.contains(like))
            | (Literature.authors.contains(like))
            | (Literature.summary.contains(like))
        )
    if source:
        query = query.filter(Literature.source == source)
    if not include_archived:
        query = query.filter(Literature.is_archived == False)  # noqa: E712

    # tag 过滤:先取候选再 Python 端过滤(JSON 列 LIKE 兜底)
    if tag:
        query = query.filter(Literature.tags.contains(tag))

    total = query.count()
    items = query.order_by(Literature.added_at.desc()).offset(offset).limit(limit).all()
    return {"items": items, "total": total}


@router.get("/{lit_id}", response_model=LiteratureOut)
def get_literature(lit_id: str, db: Session = Depends(get_db)):
    """文献详情"""
    lit = db.query(Literature).filter(Literature.id == lit_id).first()
    if not lit:
        raise HTTPException(404, "literature not found")
    return lit


# ===== 写操作(POST/PATCH/DELETE,需 API Key)=====


@router.post(
    "",
    response_model=LiteratureOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_api_key)],
)
def create_literature(payload: LiteratureCreate, db: Session = Depends(get_db)):
    """新建文献(added_by 缺省 = 'api')"""
    lit = Literature(
        id=_gen_uuid(),
        title=payload.title,
        authors=payload.authors,
        url=payload.url,
        tags=payload.tags or [],
        summary=payload.summary,
        source=payload.source,
        added_by=payload.added_by or "api",
    )
    db.add(lit)
    db.commit()
    db.refresh(lit)
    return lit


@router.patch(
    "/{lit_id}",
    response_model=LiteratureOut,
    dependencies=[Depends(require_api_key)],
)
def update_literature(
    lit_id: str,
    payload: LiteratureUpdate,
    db: Session = Depends(get_db),
):
    """更新文献(对齐 FeedbackUpdate 风格:exclude_unset 增量)"""
    lit = db.query(Literature).filter(Literature.id == lit_id).first()
    if not lit:
        raise HTTPException(404, "literature not found")
    if lit.is_archived:
        raise HTTPException(422, "cannot update archived literature; restore first")

    update_data = payload.model_dump(exclude_unset=True)
    for key, val in update_data.items():
        setattr(lit, key, val)

    db.commit()
    db.refresh(lit)
    return lit


@router.delete(
    "/{lit_id}",
    dependencies=[Depends(require_api_key)],
)
def archive_literature(lit_id: str, db: Session = Depends(get_db)):
    """软删除文献(置 is_archived=True,对齐 Requirement 一致性)"""
    lit = db.query(Literature).filter(Literature.id == lit_id).first()
    if not lit:
        raise HTTPException(404, "literature not found")
    lit.is_archived = True
    db.commit()
    return {"id": lit.id, "is_archived": True}


@router.post(
    "/{lit_id}/restore",
    response_model=LiteratureOut,
    dependencies=[Depends(require_api_key)],
)
def restore_literature(lit_id: str, db: Session = Depends(get_db)):
    """撤销软删除"""
    lit = db.query(Literature).filter(Literature.id == lit_id).first()
    if not lit:
        raise HTTPException(404, "literature not found")
    lit.is_archived = False
    db.commit()
    db.refresh(lit)
    return lit
