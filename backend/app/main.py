"""FastAPI app — 架构平台 MVP"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from .database import init_db
from .routes import api_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动时建表"""
    init_db()
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


@app.get("/")
def root():
    """服务根"""
    return {
        "name": "架构平台",
        "version": app.version,
        "docs": "/docs",
        "openapi": "/openapi.json",
        "healthz": "/healthz",
    }