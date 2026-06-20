"""API Key 鉴权中间件

设计原则(架构师实用主义):
- ARCH_PLATFORM_API_KEY 环境变量设置 → 强制鉴权
- 未设置 → 开放模式(开发/单机),启动时 log warning
- Key 通过 X-API-Key 请求头传递
- GET endpoints 不鉴权(只读)
- POST/PATCH/DELETE 必须鉴权

部署时:
- systemd unit 里 Environment=ARCH_PLATFORM_API_KEY=xxx
- 或 docker-compose.yml 里 environment: - ARCH_PLATFORM_API_KEY=${API_KEY}
"""
import os
import logging
from fastapi import Header, HTTPException, status

logger = logging.getLogger(__name__)

API_KEY = os.environ.get("ARCH_PLATFORM_API_KEY", "")


def is_auth_enabled() -> bool:
    """鉴权是否启用(API Key 已配置)"""
    return bool(API_KEY)


async def require_api_key(x_api_key: str = Header(None, alias="X-API-Key")):
    """FastAPI dependency:写操作(POST/PATCH/DELETE)必须带正确的 X-API-Key

    用法:
        @router.post("", dependencies=[Depends(require_api_key)])
        def create_component(...):
            ...
    """
    if not is_auth_enabled():
        # 未启用鉴权 = 开放模式(仅供开发)
        return

    if not x_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing X-API-Key header",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    if x_api_key != API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid X-API-Key",
            headers={"WWW-Authenticate": "ApiKey"},
        )


def warn_if_open_mode():
    """启动时调用:开放模式打印警告"""
    if not is_auth_enabled():
        logger.warning(
            "⚠️  ARCH_PLATFORM_API_KEY not set — API is in OPEN MODE. "
            "Write operations (POST/PATCH/DELETE) are unauthenticated. "
            "Set ARCH_PLATFORM_API_KEY env var to enable auth before production deployment."
        )