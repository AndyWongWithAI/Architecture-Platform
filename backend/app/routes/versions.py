"""Version routes — GET"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Version
from ..schemas import VersionOut

router = APIRouter()


@router.get("/{version_id}", response_model=VersionOut)
def get_version(version_id: str, db: Session = Depends(get_db)):
    """版本详情"""
    ver = db.query(Version).filter(Version.id == version_id).first()
    if not ver:
        raise HTTPException(404, "version not found")
    return ver