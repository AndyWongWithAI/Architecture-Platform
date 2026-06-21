"""Doubt-Driven Development 路由(2026-06-21 新增)

实现 CLAIM → EXTRACT → DOUBT → RECONCILE → STOP 5 步法的 API。

注意:本模块是"存储 + 编排",**真正的 reviewer 推理**留给 AI 助手(MCP)或人工
(CLI / Web)。架构平台只负责:
- 持久化 cycle + finding
- 提供状态机校验(verdict / cycle_count / stopped_at)
- 4 入口数据共享(同一份 cycle,API/CLI/MCP/Web 都可见)
"""
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session, joinedload

from ..database import get_db
from ..models import DoubtCycle, DoubtFinding, DoubtVerdict, DoubtFindingCategory, DoubtFindingSeverity
from ..schemas import (
    DoubtCycleCreate, DoubtCycleOut, DoubtCycleStop,
    DoubtFindingCreate, DoubtFindingOut,
)
from ..auth import require_api_key


router = APIRouter()


# ——— 创建(POST /doubt/cycle)———

@router.post(
    "/cycle",
    response_model=DoubtCycleOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_api_key)],
)
def create_cycle(
    payload: DoubtCycleCreate,
    db: Session = Depends(get_db),
):
    """开一个新 doubt cycle(Step 1: CLAIM + Step 2: EXTRACT 已完成)"""
    cycle = DoubtCycle(
        claim=payload.claim,
        artifact=payload.artifact,
        contract=payload.contract,
        component_id=payload.component_id,
        created_by=payload.created_by,
        cycle_count=1,  # 第一个 cycle 轮次
    )
    db.add(cycle)
    db.commit()
    db.refresh(cycle)
    return cycle


# ——— 详情 ———

@router.get("/cycles/{cycle_id}", response_model=DoubtCycleOut)
def get_cycle(cycle_id: str, db: Session = Depends(get_db)):
    """查 cycle(含 findings)"""
    cycle = (
        db.query(DoubtCycle)
        .options(joinedload(DoubtCycle.findings))
        .filter(DoubtCycle.id == cycle_id)
        .first()
    )
    if not cycle:
        raise HTTPException(404, "cycle not found")
    return cycle


# ——— 追加 finding(Step 4: RECONCILE)———

@router.post(
    "/cycles/{cycle_id}/findings",
    response_model=DoubtFindingOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_api_key)],
)
def add_finding(
    cycle_id: str,
    payload: DoubtFindingCreate,
    db: Session = Depends(get_db),
):
    """RECONCILE:加一条 finding(classify: actionable/trade-off/noise/contract-misread)"""
    cycle = db.query(DoubtCycle).filter(DoubtCycle.id == cycle_id).first()
    if not cycle:
        raise HTTPException(404, "cycle not found")
    if cycle.stopped_at:
        raise HTTPException(409, "cycle already stopped; create new cycle to continue")

    try:
        cat = DoubtFindingCategory(payload.category)
        sev = DoubtFindingSeverity(payload.severity)
    except ValueError as e:
        raise HTTPException(422, f"invalid enum: {e}")

    finding = DoubtFinding(
        cycle_id=cycle.id,
        category=cat,
        severity=sev,
        description=payload.description,
    )
    db.add(finding)
    db.commit()
    db.refresh(finding)
    return finding


# ——— 推进到下一轮 + 更新 verdict(Step 3: DOUBT 完成)———

@router.patch(
    "/cycles/{cycle_id}/advance",
    response_model=DoubtCycleOut,
    dependencies=[Depends(require_api_key)],
)
def advance_cycle(
    cycle_id: str,
    verdict: str = Query(..., pattern=r"^(pass|fail|needs_more_evidence)$"),
    score: Optional[float] = Query(None, ge=0.0, le=1.0),
    next_step: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """DOUBT 步骤完成:写 verdict / score / next_step。
    业务规则:
    - verdict=pass 或 fail → 同步写 stopped_at(终态)
    - verdict=needs_more_evidence → cycle_count+1(进入下一轮,除非已达 max_cycles)
    """
    cycle = db.query(DoubtCycle).filter(DoubtCycle.id == cycle_id).first()
    if not cycle:
        raise HTTPException(404, "cycle not found")
    if cycle.stopped_at:
        raise HTTPException(409, "cycle already stopped")

    cycle.verdict = DoubtVerdict(verdict)
    cycle.score = score
    cycle.next_step = next_step

    if verdict in ("pass", "fail"):
        # 终态
        cycle.stopped_at = datetime.now(timezone.utc)
        cycle.stopped_reason = f"verdict={verdict}"
    else:
        # needs_more_evidence:进入下一轮(除非超限)
        if cycle.cycle_count >= cycle.max_cycles:
            cycle.stopped_at = datetime.now(timezone.utc)
            cycle.stopped_reason = "max_cycles reached (3)"
        else:
            cycle.cycle_count += 1

    db.commit()
    db.refresh(cycle)
    return cycle


# ——— 主动 STOP(Step 5)———

@router.post(
    "/cycles/{cycle_id}/stop",
    response_model=DoubtCycleOut,
    dependencies=[Depends(require_api_key)],
)
def stop_cycle(
    cycle_id: str,
    payload: DoubtCycleStop,
    db: Session = Depends(get_db),
):
    """STOP 步骤:用户主动 ship,reason 记录"""
    cycle = db.query(DoubtCycle).filter(DoubtCycle.id == cycle_id).first()
    if not cycle:
        raise HTTPException(404, "cycle not found")
    if cycle.stopped_at:
        raise HTTPException(409, "cycle already stopped")

    cycle.stopped_at = datetime.now(timezone.utc)
    cycle.stopped_reason = f"user_stop: {payload.reason}"
    db.commit()
    db.refresh(cycle)
    return cycle
