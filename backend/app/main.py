"""FastAPI app — 架构平台 MVP"""
import logging
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager

from .database import init_db, SessionLocal
from .routes import api_router
from .ui.routes import router as ui_router

logger = logging.getLogger(__name__)


def _seed_components_if_empty():
    """首次启动时,如果 DB 为空,自动从 docs/components/*.md 导入种子数据

    适用场景:
      - #1 华为云首次部署(空 DB + 镜像内带种子数据)
      - 本地首次 docker run(空 /app/data 挂卷)

    已部署过 / 已有数据的场景:跳过导入,避免重复
    """
    from .models import Component
    from .services import MarkdownImporter

    db = SessionLocal()
    try:
        existing = db.query(Component).count()
        if existing > 0:
            logger.info(f"[seed] DB 已有 {existing} 个组件,跳过种子导入")
            return

        # 镜像内 docs 路径(由 Dockerfile COPY 进去)
        candidates = [
            "/app/docs/components",  # 容器内(Dockerfile 路径)
            os.path.join(os.path.dirname(os.path.dirname(__file__)), "..", "docs", "components"),  # 本地开发
        ]
        components_dir = None
        for c in candidates:
            if os.path.isdir(c) and os.listdir(c):
                components_dir = c
                break

        if not components_dir:
            logger.warning("[seed] 未找到 docs/components 目录,跳过种子导入")
            return

        logger.info(f"[seed] 首次启动,从 {components_dir} 导入种子数据...")
        importer = MarkdownImporter(db, components_dir)
        result = importer.import_all()
        logger.info(
            f"[seed] 导入完成:created={result.created}, "
            f"updated={result.updated}, errors={len(result.errors)}"
        )
        if result.errors:
            for err in result.errors:
                logger.error(f"[seed]   - {err}")
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动时:建表 → 鉴权检查 → 首次自动导入种子数据"""
    init_db()
    _seed_components_if_empty()
    from .auth import warn_if_open_mode
    warn_if_open_mode()
    yield


app = FastAPI(
    title="架构平台 API",
    description="CLAUDE.md 提到的独立组件登记/复用/反馈系统 — MVP 后端",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)
app.include_router(ui_router)

# Phase 4:挂载静态资源
import pathlib
_STATIC_DIR = pathlib.Path(__file__).resolve().parent / "static"
if _STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")


@app.get("/")
def root():
    """服务根(UI 入口)"""
    return {
        "name": "架构平台",
        "version": app.version,
        "ui": "/",
        "docs": "/docs",
        "openapi": "/openapi.json",
        "healthz": "/healthz",
    }