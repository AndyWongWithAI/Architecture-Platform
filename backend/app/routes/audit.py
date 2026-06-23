"""Audit routes — REQ-7328c640 每日 04:00 自审结果入库与查询

数据契约对齐:`~/.claude/skills/audit/scripts/scan.py --json` 输出:
  { ts, scope, gate, severity_min, summary, findings: [...] }

调用方:
  - 内部 cron(deploy/audit.sh, 主机 #1 每天 04:00):POST /api/v1/audit/runs
  - Web UI(/audit, /audit/{id}):只读查询
"""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import AuditRun, AuditFinding
from ..schemas import (
    AuditFindingList,
    AuditRunCreate,
    AuditRunDetail,
    AuditRunList,
    AuditRunOut,
)
from ..auth import require_api_key

router = APIRouter()


# ===== 写操作:接收 cron POST(仅 X-API-Key)=====


@router.post(
    "",
    response_model=AuditRunOut,
    status_code=201,
    dependencies=[Depends(require_api_key)],
)
def create_audit_run(payload: AuditRunCreate, db: Session = Depends(get_db)):
    """接收 scan.py --json 输出,落地 AuditRun + 批量 AuditFinding。

    事务语义:
      1. 建 AuditRun(status=completed, started_at/finished_at 都用 now_utc)
      2. 批量建 AuditFinding(run_id=new_run.id)
      3. 一次性 commit,失败整体回滚(避免 orphan findings)

    计数一致性:服务端以 findings 数组长度为准,覆盖 summary 的 total。
    blocker / warn / info 计数由 findings.severity 重新计算,避免
    scan.py 与 DB 写入之间的不一致。
    """
    # 重新计算计数(以 findings 为准)
    findings_payload = payload.findings or []
    total = len(findings_payload)
    blocker_count = sum(1 for f in findings_payload if f.severity == "blocker")
    warn_count = sum(1 for f in findings_payload if f.severity == "warn")
    info_count = sum(1 for f in findings_payload if f.severity == "info")

    run = AuditRun(
        started_at=datetime.utcnow(),
        finished_at=datetime.utcnow(),
        scope=payload.scope,
        gate=payload.gate,
        severity_min=payload.severity_min,
        status="completed",
        total=total,
        blocker_count=blocker_count,
        warn_count=warn_count,
        info_count=info_count,
        scanner_ts=payload.ts,
        error_message=None,
    )
    db.add(run)
    db.flush()  # 拿到 run.id 给 findings.run_id

    for f in findings_payload:
        db.add(AuditFinding(
            run_id=run.id,
            principle=f.principle,
            check=f.check,
            severity=f.severity,
            scope=f.scope,
            target=f.target,
            detail=f.detail,
            fingerprint=f.fingerprint,
        ))

    db.commit()
    db.refresh(run)
    return run


# ===== 读操作 =====


@router.get("", response_model=AuditRunList)
def list_audit_runs(
    status: Optional[str] = Query(None, pattern=r"^(running|completed|failed)$"),
    severity_min: Optional[str] = Query(None, pattern=r"^(info|warn|blocker)$"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """列出 audit run(分页 + 过滤)

    默认按 started_at desc。
    """
    query = db.query(AuditRun)
    if status:
        query = query.filter(AuditRun.status == status)
    # severity_min:筛选「触发该严重度的 run」,即
    # info → block_count > 0;warn → warn_count > 0;blocker → blocker_count > 0
    if severity_min == "blocker":
        query = query.filter(AuditRun.blocker_count > 0)
    elif severity_min == "warn":
        query = query.filter(AuditRun.warn_count > 0)
    elif severity_min == "info":
        query = query.filter(AuditRun.info_count > 0)

    total = query.count()
    items = (
        query.order_by(AuditRun.started_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return {"items": items, "total": total}


@router.get("/{run_id}", response_model=AuditRunDetail)
def get_audit_run(run_id: str, db: Session = Depends(get_db)):
    """audit run 详情(含 findings)"""
    run = db.query(AuditRun).filter(AuditRun.id == run_id).first()
    if not run:
        raise HTTPException(404, "audit run not found")
    return run


@router.get("/{run_id}/findings", response_model=AuditFindingList)
def list_audit_findings(
    run_id: str,
    severity: Optional[str] = Query(None, pattern=r"^(info|warn|blocker)$"),
    principle: Optional[str] = Query(None, max_length=50),
    limit: int = Query(200, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """单 run 下的 finding 列表(支持 severity/principle 过滤)"""
    # 校验 run 存在(404 比空列表更准确)
    run = db.query(AuditRun).filter(AuditRun.id == run_id).first()
    if not run:
        raise HTTPException(404, "audit run not found")

    query = db.query(AuditFinding).filter(AuditFinding.run_id == run_id)
    if severity:
        query = query.filter(AuditFinding.severity == severity)
    if principle:
        query = query.filter(AuditFinding.principle == principle)

    total = query.count()
    items = query.order_by(AuditFinding.id).offset(offset).limit(limit).all()
    return {"items": items, "total": total}