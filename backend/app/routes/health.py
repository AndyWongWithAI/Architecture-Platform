"""Health check"""
from fastapi import APIRouter
from sqlalchemy import text
from ..database import engine

router = APIRouter()


@router.get("/healthz")
def healthz():
    """健康检查 — 验证 DB 连通"""
    with engine.connect() as conn:
        result = conn.execute(text("SELECT 1")).scalar()
    return {"status": "ok", "db_check": result == 1}