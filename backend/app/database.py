"""SQLAlchemy engine + session 管理"""
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base


def _default_db_path():
    data_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
    os.makedirs(data_dir, exist_ok=True)
    return os.path.join(data_dir, "arch.db")


DB_PATH = os.environ.get("ARCH_DB_PATH") or _default_db_path()
SQLALCHEMY_DATABASE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    echo=False,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    """FastAPI dependency:提供 DB session,自动关闭"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _rebuild_engine(db_path: str):
    """测试用:运行时切换到新 DB"""
    global engine, SessionLocal, DB_PATH, SQLALCHEMY_DATABASE_URL
    DB_PATH = db_path
    SQLALCHEMY_DATABASE_URL = f"sqlite:///{DB_PATH}"
    engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db():
    """建表(Phase 1 用 create_all;Alembic 后续)
    支持 ARCH_DB_PATH 环境变量切换(测试用)
    """
    from . import models  # noqa: F401 注册所有 model

    env_path = os.environ.get("ARCH_DB_PATH")
    if env_path and DB_PATH != env_path:
        _rebuild_engine(env_path)

    Base.metadata.create_all(bind=engine)
    # SQLite create_all 不处理 ALTER;老库加列需运行时迁移
    _migrate_legacy_columns(engine)


def _migrate_legacy_columns(engine):
    """启动时检测缺失列并 ALTER(SQLite 限制:create_all 不处理 ALTER TABLE)

    迁移记录(追加历史):
      - 2026-06-21:feedbacks 表加 requirement_id 列 + 索引(追溯链)
    """
    from sqlalchemy import inspect, text
    insp = inspect(engine)
    if "feedbacks" not in insp.get_table_names():
        return  # 新库,create_all 已建好
    cols = {c["name"] for c in insp.get_columns("feedbacks")}
    with engine.begin() as conn:
        if "requirement_id" not in cols:
            # SQLite 不支持 IF NOT EXISTS 加列;先探测再执行
            conn.execute(text("ALTER TABLE feedbacks ADD COLUMN requirement_id VARCHAR"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_feedback_requirement ON feedbacks (requirement_id)"))