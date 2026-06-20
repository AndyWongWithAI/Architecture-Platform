"""app/ui/routes.py — Web UI 8 个页面路由

所有页面都是 GET(只读);唯一写操作是 PATCH /feedbacks/{id} via proxy.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from .helpers import register_filters
from .proxy import api_get, api_patch


# ——— 模板配置 ———

# backend/app/ui/routes.py → backend/app/templates
TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
register_filters(templates.env)

# 静态资源(在 main.py 单独挂载,这里只是绝对路径)
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


router = APIRouter()


# ——— 辅助函数 ———

async def _safe_get(path: str, params: Optional[dict] = None, default=None):
    """API GET 容错:失败返回 default"""
    try:
        return await api_get(path, params=params)
    except HTTPException:
        return default
    except Exception:
        return default


# ——— 1. 首页 / 总览 ———

@router.get("/", response_class=HTMLResponse)
async def index(request: Request):
    components = await _safe_get("/api/v1/components", {"limit": 200}, default={"items": [], "total": 0})
    feedbacks = await _safe_get("/api/v1/feedbacks", {"limit": 5}, default={"items": [], "total": 0})
    deployments = await _safe_get("/api/v1/deployments", {"limit": 5}, default={"items": [], "total": 0})

    # 按 layer 分组统计
    by_layer = {"L0_infrastructure": 0, "L1_platform": 0, "L2_capability": 0, "L3_application": 0}
    assets_count = 0
    for c in components.get("items", []):
        layer = c.get("layer", "")
        if layer in by_layer:
            by_layer[layer] += 1
        if c.get("is_asset"):
            assets_count += 1

    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "total_components": components.get("total", 0),
            "by_layer": by_layer,
            "assets_count": assets_count,
            "project_count": components.get("total", 0) - assets_count,
            "total_feedbacks": feedbacks.get("total", 0),
            "total_deployments": deployments.get("total", 0),
            "recent_feedbacks": feedbacks.get("items", [])[:5],
            "recent_deployments": deployments.get("items", [])[:5],
        },
    )


# ——— 2. 组件列表 ———

@router.get("/components", response_class=HTMLResponse)
async def components_list(
    request: Request,
    layer: Optional[str] = None,
    category: Optional[str] = None,
    is_asset: Optional[str] = None,  # FB-K 修复(2026-06-21):改为 str,内部判断 "true"/"false",避免空字符串触发 422
    q: Optional[str] = None,
):
    params = {"limit": 200}
    if layer:
        params["layer"] = layer
    if category:
        params["category"] = category
    # FB-K:is_asset 用字符串手动判断("true"/"false" → bool;"" / 其他 → 不过滤)
    if is_asset == "true":
        params["is_asset"] = "true"
    elif is_asset == "false":
        params["is_asset"] = "false"
    if q:
        params["q"] = q

    data = await _safe_get("/api/v1/components", params, default={"items": [], "total": 0})

    return templates.TemplateResponse(
        request,
        "components/list.html",
        {
            "components": data.get("items", []),
            "total": data.get("total", 0),
            "filters": {
                "layer": layer,
                "category": category,
                "is_asset": is_asset,
                "q": q,
            },
        },
    )


# ——— 3. 组件详情 ———

@router.get("/components/{name}", response_class=HTMLResponse)
async def component_detail(request: Request, name: str):
    component = await _safe_get(f"/api/v1/components/{name}")
    if not component:
        raise HTTPException(status_code=404, detail=f"组件 {name} 不存在")

    # FB-H 修复(2026-06-21):用新端点 GET /components/{id}/feedbacks
    # 之前用 ?version_id=current_version_id 只能查到当前版本的反馈
    # 现在查组件所有版本关联的反馈
    feedbacks = await _safe_get(
        f"/api/v1/components/{name}/feedbacks",
        default={"items": []},
    )

    return templates.TemplateResponse(
        request,
        "components/detail.html",
        {
            "c": component,
            "versions": component.get("versions", []),
            "feedbacks": feedbacks.get("items", []),
        },
    )


# ——— 4. 依赖树 ———

@router.get("/components/{name}/tree", response_class=HTMLResponse)
async def component_tree(request: Request, name: str):
    tree = await _safe_get(f"/api/v1/components/{name}/tree")
    if not tree:
        raise HTTPException(status_code=404, detail=f"组件 {name} 不存在")

    return templates.TemplateResponse(
        request,
        "components/tree.html",
        {"tree": tree, "root_name": name},
    )


# ——— 5. 反馈看板(Kanban) ———

@router.get("/feedbacks", response_class=HTMLResponse)
async def feedbacks_kanban(request: Request):
    """4 列看板:open / triaged / fixing / closed(fixed + wontfix)"""
    data = await _safe_get("/api/v1/feedbacks", {"limit": 200}, default={"items": [], "total": 0})
    items = data.get("items", [])

    # 按 status 分列
    columns = {
        "open": [],
        "triaged": [],
        "fixing": [],
        "closed": [],  # fixed + wontfix 合一
    }
    for fb in items:
        status = fb.get("status", "open")
        if status == "fixed" or status == "wontfix":
            columns["closed"].append(fb)
        elif status in columns:
            columns[status].append(fb)
        else:
            columns["open"].append(fb)  # 兜底

    return templates.TemplateResponse(
        request,
        "feedbacks/kanban.html",
        {"columns": columns, "total": data.get("total", 0)},
    )


# ——— 6. PATCH 反馈代理(看板用)———

@router.post("/feedbacks/{feedback_id}/patch")
async def feedback_patch_from_ui(
    feedback_id: str,
    request: Request,
    status: Optional[str] = Form(None),
    decision: Optional[str] = Form(None),
    root_cause: Optional[str] = Form(None),
    fix_plan: Optional[str] = Form(None),
):
    """Web UI → 服务器代理 → 后端 PATCH /api/v1/feedbacks/{id}

    返回:更新后的 feedback JSON + 新卡片 HTML(供 htmx 替换)
    """
    payload = {}
    if status:
        payload["status"] = status
    if decision is not None:  # 允许清空 decision
        payload["decision"] = decision if decision else None
    if root_cause:
        payload["root_cause"] = root_cause
    if fix_plan:
        payload["fix_plan"] = fix_plan

    try:
        updated = await api_patch(f"/api/v1/feedbacks/{feedback_id}", payload)
    except HTTPException as e:
        # 把错误回传给前端(htmx 会显示在目标元素)
        return JSONResponse({"error": str(e.detail)}, status_code=e.status_code)

    # 返回新卡片 HTML(htmx 用 outerHTML 替换)
    return templates.TemplateResponse(
        request,
        "feedbacks/_card.html",
        {"fb": updated},
    )


# ——— 6.5. 反馈明细(FB-I 修复:2026-06-21)———

@router.get("/feedbacks/{feedback_id}", response_class=HTMLResponse)
async def feedback_detail(request: Request, feedback_id: str):
    """反馈明细页:展示 bug_summary / root_cause / fix_plan / 元数据"""
    fb = await _safe_get(f"/api/v1/feedbacks/{feedback_id}")
    if not fb:
        raise HTTPException(status_code=404, detail=f"反馈 {feedback_id} 不存在")
    return templates.TemplateResponse(
        request,
        "feedbacks/detail.html",
        {"fb": fb},
    )


# ——— 7. 部署地图 ———

@router.get("/deployments", response_class=HTMLResponse)
async def deployments_map(
    request: Request,
    host: Optional[str] = None,
    env: Optional[str] = None,
):
    params = {"limit": 200}
    if host:
        params["host"] = host
    if env:
        params["env"] = env
    data = await _safe_get("/api/v1/deployments", params, default={"items": [], "total": 0})

    # 按 host 分组(地图视图)
    by_host: dict[str, list] = {}
    for dep in data.get("items", []):
        h = dep.get("host", "unknown")
        by_host.setdefault(h, []).append(dep)

    # 取所有组件(用于 host × component 矩阵)
    components = await _safe_get("/api/v1/components", {"limit": 200}, default={"items": []})
    all_components = components.get("items", [])

    # 取所有 version(为了 host × component × version 映射)
    # version 信息包含 component_id → version 字符串
    return templates.TemplateResponse(
        request,
        "deployments/map.html",
        {
            "deployments": data.get("items", []),
            "by_host": by_host,
            "total": data.get("total", 0),
            "filters": {"host": host, "env": env},
            "components": all_components,
        },
    )


# ——— 8. 搜索 ———

@router.get("/search", response_class=HTMLResponse)
async def search(request: Request, q: Optional[str] = Query(None)):
    if not q:
        return templates.TemplateResponse(request, "search.html", {"q": "", "data": None})

    data = await _safe_get("/api/v1/search", {"q": q}, default={"components": [], "versions": [], "feedbacks": [], "total": 0})
    return templates.TemplateResponse(request, "search.html", {"q": q, "data": data})


# ——— 健康检查(复用后端) ———

@router.get("/healthz", response_class=JSONResponse)
async def healthz():
    data = await _safe_get("/healthz", default={"status": "unknown", "db_check": False})
    return JSONResponse(data)