"""Version routes — GET + POST deployments / feedbacks"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Version, Deployment, Feedback
from ..schemas import VersionOut, VersionUpdate, DeploymentCreate, DeploymentOut, FeedbackCreate, FeedbackOut
from ..auth import require_api_key

router = APIRouter()


def _gen_uuid() -> str:
    import uuid
    return str(uuid.uuid4())


@router.get("/{version_id}", response_model=VersionOut)
def get_version(version_id: str, db: Session = Depends(get_db)):
    """版本详情"""
    ver = db.query(Version).filter(Version.id == version_id).first()
    if not ver:
        raise HTTPException(404, "version not found")
    return ver


@router.patch(
    "/{version_id}",
    response_model=VersionOut,
    dependencies=[Depends(require_api_key)],
)
def update_version(
    version_id: str,
    payload: VersionUpdate,
    db: Session = Depends(get_db),
):
    """版本 PATCH(2026-06-21 新增):补 design_doc / changelog / compatibility_window 等。

    注意:version 号、semver_intent 等"身份字段"不可改(避免语义混乱)。
    """
    ver = db.query(Version).filter(Version.id == version_id).first()
    if not ver:
        raise HTTPException(404, "version not found")

    # 只更新 payload 里显式提供的字段
    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(ver, field, value)

    db.commit()
    db.refresh(ver)
    return ver


@router.post(
    "/{version_id}/deployments",
    response_model=DeploymentOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_api_key)],
)
def create_deployment(
    version_id: str,
    payload: DeploymentCreate,
    db: Session = Depends(get_db),
):
    """登记部署(需要 API Key)"""
    ver = db.query(Version).filter(Version.id == version_id).first()
    if not ver:
        raise HTTPException(404, "version not found")

    dep = Deployment(
        id=_gen_uuid(),
        version_id=ver.id,
        env=payload.env,
        host=payload.host,
        deploy_path=payload.deploy_path,
        config_hash=payload.config_hash,
        deployed_by=payload.deployed_by,
        rollback_to=payload.rollback_to,
        resolved_versions=payload.resolved_versions or {},
        lockfile_hash=payload.lockfile_hash,
        build_reproducible=payload.build_reproducible,
    )
    db.add(dep)
    db.commit()
    db.refresh(dep)
    return dep


@router.post(
    "/{version_id}/feedbacks",
    response_model=FeedbackOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_api_key)],
)
def create_feedback(
    version_id: str,
    payload: FeedbackCreate,
    db: Session = Depends(get_db),
):
    """登记 Bug 反馈(需要 API Key)"""
    ver = db.query(Version).filter(Version.id == version_id).first()
    if not ver:
        raise HTTPException(404, "version not found")

    fb = Feedback(
        id=_gen_uuid(),
        version_id=ver.id,
        reporter=payload.reporter,
        bug_summary=payload.bug_summary,
        root_cause=payload.root_cause,
        fix_plan=payload.fix_plan,
        severity=payload.severity,
        reused_in_projects=payload.reused_in_projects or [],
    )
    db.add(fb)
    db.commit()
    db.refresh(fb)
    return fb