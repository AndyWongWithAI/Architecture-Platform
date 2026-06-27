"""CoreThought routes — 架构平台核心思想实体(REQ-968b1c99 / ADR-0003,2026-06-27)

平台第 6 大事务型实体(道层面资产):
- 沉淀架构原则 / 哲学 / 长期愿景
- 不挂 component_id,通过 tags / examples[].component_id 跨实体引用
- 软删除走 is_archived(对齐 Literature / Requirement 一致性)
- 状态机为轻量(4 态,不校验转换矩阵)
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import CoreThought, CoreThoughtStatus
from ..schemas import (
    CoreThoughtList, CoreThoughtOut, CoreThoughtCreate, CoreThoughtUpdate,
)
from ..auth import require_api_key

router = APIRouter()


def _gen_uuid() -> str:
    import uuid
    return str(uuid.uuid4())


def _normalize_ct(ct) -> dict:
    """P3.6 verify 修复:examples/tags 从 ORM 出来后 normalize None → []
    SQLAlchemy JSON 列写 None 后存的是 JSON 字面 'null',Pydantic 校验 list_type 失败。
    此处统一兜底,避免影响 list/get 输出序列化。
    """
    return {
        "id": ct.id,
        "title": ct.title,
        "thesis": ct.thesis,
        "rationale": ct.rationale,
        "how_to_apply": ct.how_to_apply,
        "origin": ct.origin,
        "status": ct.status,
        "tags": ct.tags or [],
        "examples": ct.examples or [],
        "proposer": ct.proposer,
        "created_at": ct.created_at,
        "updated_at": ct.updated_at,
        "is_archived": ct.is_archived,
    }


# ===== 读操作(GET,公开)=====


@router.get("", response_model=CoreThoughtList)
def list_core_thoughts(
    q: Optional[str] = Query(None, description="title/thesis/rationale/how_to_apply 模糊搜索"),
    tag: Optional[str] = Query(None, description="按 tag 过滤(任一命中)"),
    status_filter: Optional[CoreThoughtStatus] = Query(
        None, alias="status", description="按 status 过滤",
    ),
    include_archived: bool = Query(False, description="包含软删除的记录"),
    proposer: Optional[str] = Query(None, description="按登记人过滤"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """列出核心思想(支持 ?q=keyword&tag=xxx&status=xxx 过滤)

    搜索:title / thesis / rationale / how_to_apply 任一 LIKE 命中
    tag 过滤:tags JSON list 中包含目标 tag(JSON contains 简化版)
    """
    query = db.query(CoreThought)
    if q:
        like = f"%{q}%"
        query = query.filter(
            (CoreThought.title.contains(like))
            | (CoreThought.thesis.contains(like))
            | (CoreThought.rationale.contains(like))
            | (CoreThought.how_to_apply.contains(like))
        )
    if status_filter is not None:
        query = query.filter(CoreThought.status == status_filter)
    if proposer:
        query = query.filter(CoreThought.proposer == proposer)
    if not include_archived:
        query = query.filter(CoreThought.is_archived == False)  # noqa: E712

    # tag 过滤:tags JSON list 中包含目标 tag(JSON contains 简化版)
    if tag:
        query = query.filter(CoreThought.tags.contains(tag))

    total = query.count()
    items = (
        query.order_by(CoreThought.updated_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return {"items": [_normalize_ct(it) for it in items], "total": total}


@router.get("/by-tag/{tag}", response_model=CoreThoughtList)
def list_by_tag(
    tag: str,
    include_archived: bool = Query(False),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """按 tag 列出核心思想(供 UI 反向引用 / 跨实体 search 命中)

    与 list_core_thoughts 的 tag 过滤等价,但语义更明确。
    """
    query = db.query(CoreThought).filter(CoreThought.tags.contains(tag))
    if not include_archived:
        query = query.filter(CoreThought.is_archived == False)  # noqa: E712

    total = query.count()
    items = (
        query.order_by(CoreThought.updated_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return {"items": [_normalize_ct(it) for it in items], "total": total}


@router.get("/{ct_id}", response_model=CoreThoughtOut)
def get_core_thought(ct_id: str, db: Session = Depends(get_db)):
    """核心思想详情"""
    ct = db.query(CoreThought).filter(CoreThought.id == ct_id).first()
    if not ct:
        raise HTTPException(404, "core_thought not found")
    return _normalize_ct(ct)


# ===== 写操作(POST/PATCH/DELETE/restore,需 API Key)=====


@router.post(
    "",
    response_model=CoreThoughtOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_api_key)],
)
def create_core_thought(payload: CoreThoughtCreate, db: Session = Depends(get_db)):
    """新建核心思想(proposer 缺省 = 'api')"""
    ct = CoreThought(
        id=_gen_uuid(),
        title=payload.title,
        thesis=payload.thesis,
        rationale=payload.rationale,
        how_to_apply=payload.how_to_apply,
        origin=payload.origin,
        status=payload.status,
        tags=payload.tags or [],
        examples=[ex.model_dump() for ex in (payload.examples or [])],
        proposer=payload.proposer or "api",
    )
    db.add(ct)
    db.commit()
    db.refresh(ct)
    return ct


@router.patch(
    "/{ct_id}",
    response_model=CoreThoughtOut,
    dependencies=[Depends(require_api_key)],
)
def update_core_thought(
    ct_id: str,
    payload: CoreThoughtUpdate,
    db: Session = Depends(get_db),
):
    """更新核心思想(对齐 LiteratureUpdate 风格:exclude_unset 增量)

    业务规则:已软删除的记录不可改(需先 restore)
    """
    ct = db.query(CoreThought).filter(CoreThought.id == ct_id).first()
    if not ct:
        raise HTTPException(404, "core_thought not found")
    if ct.is_archived:
        raise HTTPException(422, "cannot update archived core_thought; restore first")

    update_data = payload.model_dump(exclude_unset=True)
    # examples 元素是 Pydantic BaseModel,需要 model_dump() 序列化为 dict
    # P3.6 verify 修:null 显式兜底成 [],避免 ORM Column(JSON) 写 None 后 CoreThoughtOut 序列化 list_type 错
    if "examples" in update_data:
        val = update_data["examples"]
        if val is None:
            val = []
        update_data["examples"] = [
            ex.model_dump() if hasattr(ex, "model_dump") else ex
            for ex in val
        ]
    for key, val in update_data.items():
        setattr(ct, key, val)

    db.commit()
    db.refresh(ct)
    return ct


@router.delete(
    "/{ct_id}",
    dependencies=[Depends(require_api_key)],
)
def archive_core_thought(ct_id: str, db: Session = Depends(get_db)):
    """软删除核心思想(置 is_archived=True,与 Literature/Requirement 一致)"""
    ct = db.query(CoreThought).filter(CoreThought.id == ct_id).first()
    if not ct:
        raise HTTPException(404, "core_thought not found")
    ct.is_archived = True
    db.commit()
    return {"id": ct.id, "is_archived": True}


@router.post(
    "/{ct_id}/restore",
    response_model=CoreThoughtOut,
    dependencies=[Depends(require_api_key)],
)
def restore_core_thought(ct_id: str, db: Session = Depends(get_db)):
    """撤销软删除"""
    ct = db.query(CoreThought).filter(CoreThought.id == ct_id).first()
    if not ct:
        raise HTTPException(404, "core_thought not found")
    ct.is_archived = False
    db.commit()
    db.refresh(ct)
    return ct
