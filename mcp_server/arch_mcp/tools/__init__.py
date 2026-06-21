"""MCP tools — 每个文件一组相关 tools"""

from . import components, feedbacks, deployments, search, requirements  # noqa: F401
# 注意:list_versions + get_version 在 deployments.py 里(版本跟部署都是 version 表相关)