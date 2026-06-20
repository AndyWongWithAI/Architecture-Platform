"""Deployment routes — GET"""
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Deployment
from ..schemas import DeploymentList

router = APIRouter()


@router.get("", response_model=DeploymentList)
def list_deployments(
    version_id: Optional[str] = None,
    host: Optional[str] = None,
    env: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """查询部署历史"""
    query = db.query(Deployment)
    if version_id:
        query = query.filter(Deployment.version_id == version_id)
    if host:
        query = query.filter(Deployment.host == host)
    if env:
        query = query.filter(Deployment.env == env)
    total = query.count()
    items = query.order_by(Deployment.deployed_at.desc()).offset(offset).limit(limit).all()
    return {"items": items, "total": total}