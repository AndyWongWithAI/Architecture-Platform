"""Search 相关 tools"""
from ..client import api_get


def search_components(query: str, limit: int = 20) -> dict:
    """跨实体关键字搜索(components / versions / feedbacks)

    给 LLM 用:用户问"有没有 redis 相关的组件?" → 一搜全知道。
    """
    return api_get("/api/v1/search", {"q": query, "limit": limit})