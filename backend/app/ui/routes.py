"""app/ui/routes.py — Web UI 8 个页面路由

所有页面都是 GET(只读);唯一写操作是 PATCH /feedbacks/{id} via proxy.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from ..database import get_db
from ..services.graph_dsl import build_component_graph
from .helpers import register_filters
from .markdown_renderer import (
    DOCS_DIR,
    get_pygments_css,
    list_markdown_files_grouped,
    render_markdown_file,
    resolve_slug,
)
from .proxy import api_delete, api_get, api_patch, api_post


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

# A-1 (REQ-6cce2927):tab 标识 → 现有 layer 取值的映射。
# tab 是 UI 概念(短名 + 包含 all),layer 是后端 enum。
# 后端 API 不变,只把 tab 翻译成 layer(或留空=all)。
TAB_LAYER_MAP = {
    "L0_infrastructure": "L0_infrastructure",
    "L1_platform": "L1_platform",
    "L2_capability": "L2_capability",
    "L3_application": "L3_application",
    "all": None,
}


@router.get("/components", response_class=HTMLResponse)
async def components_list(
    request: Request,
    layer: Optional[str] = None,
    tab: Optional[str] = None,
    category: Optional[str] = None,
    is_asset: Optional[str] = None,  # FB-K 修复(2026-06-21):改为 str,内部判断 "true"/"false",避免空字符串触发 422
    q: Optional[str] = None,
    include_archived: Optional[str] = None,  # REQ-f740a3be:UI 列表显式展开归档项
):
    """组件列表:tab 分层(L0/L1/L2/L3/all)+ 下方二级过滤(category/is_asset/q)

    参数优先级:
      tab    >  layer(向下兼容老的 ?layer= 直接传值)
      两者皆无 → active_tab="all"(默认)

    tab → layer 翻译:
      "L0_infrastructure" → "L0_infrastructure"(传给后端)
      "all"               → None(不传 layer)
      未知 tab 值        → 兜底为 "all"

    REQ-f740a3be:
      include_archived="true" → 传给后端 API 的 ?include_archived=true,
      后端 list 默认隐藏已归档组件,需显式开关才展示。
    """
    # 1. tab → layer 翻译
    active_tab = "all"
    effective_layer = layer
    if tab:
        if tab in TAB_LAYER_MAP:
            active_tab = tab
            effective_layer = TAB_LAYER_MAP[tab]  # 可能为 None
        else:
            # 未知 tab:忽略,走 all
            active_tab = "all"
            effective_layer = None
    elif layer and layer in TAB_LAYER_MAP:
        # 老 ?layer= 链接直接进来:把它映射回对应的 tab,UI 视觉一致
        active_tab = layer

    # 2. 用一次 SQL COUNT GROUP BY 拿各层级组件数(对 all 视图用,节省 N+1)
    # REQ-f740a3be:tab 计数也尊重 include_archived,这样切换开关后 tab 数字准确
    list_query = {"limit": 200}
    if include_archived == "true":
        list_query["include_archived"] = "true"
    all_data = await _safe_get(
        "/api/v1/components",
        list_query,
        default={"items": [], "total": 0},
    )
    all_items = all_data.get("items", [])
    tab_counts = {"L0_infrastructure": 0, "L1_platform": 0, "L2_capability": 0, "L3_application": 0}
    for c in all_items:
        layer_key = c.get("layer", "")
        if layer_key in tab_counts:
            tab_counts[layer_key] += 1
    tab_counts["all"] = all_data.get("total", len(all_items))

    # 3. 当前视图的实际查询
    params = {"limit": 200}
    if effective_layer:
        params["layer"] = effective_layer
    if category:
        params["category"] = category
    # FB-K:is_asset 用字符串手动判断("true"/"false" → bool;"" / 其他 → 不过滤)
    if is_asset == "true":
        params["is_asset"] = "true"
    elif is_asset == "false":
        params["is_asset"] = "false"
    if q:
        params["q"] = q
    if include_archived == "true":
        params["include_archived"] = "true"

    data = await _safe_get("/api/v1/components", params, default={"items": [], "total": 0})

    # 4. 构造 tabs(给 partial 用),按 L0→L3→all 顺序
    tabs = [
        {"id": "L0_infrastructure", "label": "L0 基础设施", "count": tab_counts["L0_infrastructure"]},
        {"id": "L1_platform", "label": "L1 平台", "count": tab_counts["L1_platform"]},
        {"id": "L2_capability", "label": "L2 能力", "count": tab_counts["L2_capability"]},
        {"id": "L3_application", "label": "L3 应用", "count": tab_counts["L3_application"]},
        {"id": "all", "label": "全部", "count": tab_counts["all"]},
    ]

    return templates.TemplateResponse(
        request,
        "components/list.html",
        {
            "components": data.get("items", []),
            "total": data.get("total", 0),
            "filters": {
                "layer": effective_layer,
                "category": category,
                "is_asset": is_asset,
                "q": q,
                "include_archived": include_archived,
            },
            "tabs": tabs,
            "active_tab": active_tab,
            "base_url": "/components",
        },
    )


# ——— 3. 组件详情 ———

@router.get("/components/{name}", response_class=HTMLResponse)
async def component_detail(
    request: Request,
    name: str,
    db: Session = Depends(get_db),
):
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

    # Phase 1.2(2026-06-21):组件关联需求(嵌入 detail 页)
    requirements = await _safe_get(
        f"/api/v1/components/{name}/requirements",
        default={"items": []},
    )

    # REQ-a77efd18:组件详情页 mermaid 架构图
    # 直接走 DB(避免再调一次 API);build_component_graph 内部容错
    graph_dsl = build_component_graph(name, db)

    return templates.TemplateResponse(
        request,
        "components/detail.html",
        {
            "c": component,
            "versions": component.get("versions", []),
            "feedbacks": feedbacks.get("items", []),
            "requirements": requirements.get("items", []),
            "graph_dsl": graph_dsl,
        },
    )


# ——— 3.5. 组件软删除 / 恢复(REQ-f740a3be)———

@router.post("/components/{name}/delete")
async def component_delete_from_ui(
    name: str,
    request: Request,
    reason: str = Form(..., min_length=10),
):
    """Web UI 删除按钮(代理 DELETE)

    业务规则:
    - reason ≥ 10 字符(Pydantic Form 兜底,API 层也校验)
    - 后端 200 → 重定向到 /components(回到列表)
    - 后端 409(被引用)/ 422(已归档)/ 404(不存在) → 返回 JSON 错误,
      前端 fetch 拿到后 alert 提示
    """
    try:
        await api_delete(f"/api/v1/components/{name}", params={"reason": reason})
    except HTTPException as e:
        error_msg = e.detail if isinstance(e.detail, str) else str(e.detail)
        return JSONResponse({"error": error_msg}, status_code=e.status_code)
    return RedirectResponse(url="/components", status_code=303)


@router.post("/components/{name}/restore")
async def component_restore_from_ui(
    name: str,
    request: Request,
):
    """Web UI 恢复按钮(代理 POST restore)"""
    try:
        await api_post(f"/api/v1/components/{name}/restore", json={})
    except HTTPException as e:
        error_msg = e.detail if isinstance(e.detail, str) else str(e.detail)
        return JSONResponse({"error": error_msg}, status_code=e.status_code)
    return RedirectResponse(url=f"/components/{name}", status_code=303)


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

    # REQ-5ebc9e3b:拉组件列表(用于「新建 Open Bug」表单下拉)
    comps_data = await _safe_get("/api/v1/components", {"limit": 200}, default={"items": []})
    components = comps_data.get("items", [])

    return templates.TemplateResponse(
        request,
        "feedbacks/kanban.html",
        {
            "columns": columns,
            "total": data.get("total", 0),
            "components": components,
        },
    )


# ——— 5.5. 新建 Open Bug 代理(REQ-5ebc9e3b 2026-06-23)———

@router.post("/feedbacks/create")
async def feedback_create_from_ui(
    request: Request,
    component_id: str = Form(...),
    bug_summary: str = Form(...),
    severity: str = Form(...),
    reporter: str = Form("web-ui"),
    reused_in_projects: Optional[str] = Form(None),
):
    """Web UI → 服务器代理 → POST /api/v1/versions/{current_version_id}/feedbacks

    业务规则:
    - reporter 默认 'web-ui'(Phase 1 acceptance criteria:可改;留空 = web-ui)
    - reused_in_projects:逗号分隔字符串 → list
    - 自动用 component 的 current_version_id(无 version 时报 422)
    """
    payload = {
        "reporter": reporter or "web-ui",
        "bug_summary": bug_summary,
        "severity": severity,
    }
    if reused_in_projects:
        payload["reused_in_projects"] = [
            p.strip() for p in reused_in_projects.split(",") if p.strip()
        ]

    # 1. 取 component 的 current_version_id(后端 POST /api/v1/versions/{ver_id}/feedbacks 需要 version)
    comp = await _safe_get(f"/api/v1/components/{component_id}")
    if not comp:
        return JSONResponse(
            {"error": f"组件 {component_id} 不存在"},
            status_code=404,
        )
    version_id = comp.get("current_version_id")
    if not version_id:
        return JSONResponse(
            {
                "error": (
                    f"组件 {comp.get('name')} 还没有 current_version,"
                    f"请先在 /components/{comp.get('name')} 登记一个版本"
                )
            },
            status_code=422,
        )

    # 2. 代理 POST
    try:
        created = await api_post(f"/api/v1/versions/{version_id}/feedbacks", payload)
    except HTTPException as e:
        return JSONResponse({"error": str(e.detail)}, status_code=e.status_code)

    from fastapi.responses import RedirectResponse
    return RedirectResponse(f"/feedbacks/{created['id']}", status_code=303)


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


# ——— 健康检查(复用后端) ——

@router.get("/healthz", response_class=JSONResponse)
async def healthz():
    data = await _safe_get("/healthz", default={"status": "unknown", "db_check": False})
    return JSONResponse(data)


# ===== Phase 1.2 需求模块 UI(2026-06-21)=====


# ——— 需求 Tab 折叠(A-2 REQ-eab024a9)———
# 需求 9 个状态太多,平铺成 9 个 tab 视觉过载。
# 按 SDLC 阶段折叠成 5 个一级 tab(active / verified / done / closed / all)。
# tab 是 UI 概念,后端 API 不变,客户端按状态桶过滤。
REQ_TAB_BUCKETS = {
    "active": ["draft", "triaged", "scheduled", "in_progress"],
    "verified": ["implemented", "verified"],
    "done": ["complete"],
    "closed": ["rejected", "cancelled"],
}
REQ_TAB_BUCKET_LABEL = {
    "active": "进行中",
    "verified": "已实现",
    "done": "已完成",
    "closed": "已关闭",
    "all": "全部",
}


@router.get("/requirements", response_class=HTMLResponse)
async def requirements_list(
    request: Request,
    status: Optional[str] = None,
    priority: Optional[str] = None,
    type: Optional[str] = None,
    assignee: Optional[str] = None,
    component: Optional[str] = None,
    tab: Optional[str] = None,
):
    """需求列表(对齐 feedbacks 看板布局但用表格,9 状态按 tab 折叠)

    A-2 (REQ-eab024a9) 需求 tab 折叠:
      - 顶部 tab:active / verified / done / closed / all(按 SDLC 阶段分桶)
      - tab 切换 ?tab=ID;老 ?status= 链接直接进 active 视图(保持兼容)
      - 二级过滤:priority / type / assignee / component(下方 select 保留)
      - 一次拉全量(limit=200),在内存里按 tab 过滤 + 算桶计数(避免 N+1)
    """
    # 1. tab → 状态桶翻译
    active_tab = "active"
    if tab and tab in REQ_TAB_BUCKETS:
        active_tab = tab
    elif tab == "all":
        active_tab = "all"
    elif status and status in ("draft", "triaged", "scheduled", "in_progress"):
        active_tab = "active"
    elif status and status in ("implemented", "verified"):
        active_tab = "verified"
    elif status == "complete":
        active_tab = "done"
    elif status and status in ("rejected", "cancelled"):
        active_tab = "closed"

    # 2. 一次拉全量,客户端按 tab 桶过滤 + 算桶计数
    params = {"limit": 200}
    if priority:
        params["priority"] = priority
    if type:
        params["type"] = type
    if assignee:
        params["assignee"] = assignee
    if component:
        params["component_id"] = component

    data = await _safe_get("/api/v1/requirements", params, default={"items": [], "total": 0})
    all_items = data.get("items", [])
    total_all = data.get("total", len(all_items))

    # 3. 按状态分桶计数
    tab_counts = {"active": 0, "verified": 0, "done": 0, "closed": 0, "all": total_all}
    for r in all_items:
        s = r.get("status", "")
        for bucket_id, statuses in REQ_TAB_BUCKETS.items():
            if s in statuses:
                tab_counts[bucket_id] += 1
                break

    # 4. 当前 tab 视图:在内存里按状态桶过滤(其他二级过滤已在 API 层生效)
    if active_tab == "all":
        items = all_items
        total = total_all
    else:
        target_statuses = REQ_TAB_BUCKETS[active_tab]
        items = [r for r in all_items if r.get("status") in target_statuses]
        total = tab_counts[active_tab]

    # 5. tabs 给 partial 用(按 active → verified → done → closed → all 顺序)
    tabs = [
        {"id": "active", "label": REQ_TAB_BUCKET_LABEL["active"], "count": tab_counts["active"]},
        {"id": "verified", "label": REQ_TAB_BUCKET_LABEL["verified"], "count": tab_counts["verified"]},
        {"id": "done", "label": REQ_TAB_BUCKET_LABEL["done"], "count": tab_counts["done"]},
        {"id": "closed", "label": REQ_TAB_BUCKET_LABEL["closed"], "count": tab_counts["closed"]},
        {"id": "all", "label": REQ_TAB_BUCKET_LABEL["all"], "count": tab_counts["all"]},
    ]

    return templates.TemplateResponse(
        request,
        "requirements/list.html",
        {
            "items": items,
            "total": total,
            "tabs": tabs,
            "active_tab": active_tab,
            "filters": {
                "status": status,
                "priority": priority,
                "type": type,
                "assignee": assignee,
                "component": component,
            },
        },
    )


@router.get("/requirements/new", response_class=HTMLResponse)
async def requirement_new_form(request: Request, component: Optional[str] = None):
    """创建需求表单(component 可预填)"""
    prefill_comp = None
    if component:
        prefill_comp = await _safe_get(f"/api/v1/components/{component}")
    return templates.TemplateResponse(
        request,
        "requirements/new.html",
        {"prefill_comp": prefill_comp},
    )


@router.get("/requirements/{req_id}", response_class=HTMLResponse)
async def requirement_detail(request: Request, req_id: str):
    """需求详情"""
    req = await _safe_get(f"/api/v1/requirements/{req_id}")
    if not req:
        raise HTTPException(status_code=404, detail=f"需求 {req_id} 不存在")
    # 追溯链:关联 feedback
    feedbacks = await _safe_get(
        f"/api/v1/requirements/{req_id}/feedbacks",
        default={"items": []},
    )
    return templates.TemplateResponse(
        request,
        "requirements/detail.html",
        {"req": req, "feedbacks": feedbacks.get("items", [])},
    )


@router.post("/requirements/create")
async def requirement_create_from_ui(
    request: Request,
    title: str = Form(...),
    type: str = Form(...),
    priority: str = Form("P2"),
    component_id: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    user_story: Optional[str] = Form(None),
    assignee: Optional[str] = Form(None),
    due_date: Optional[str] = Form(None),
    tags: Optional[str] = Form(None),
    proposer: str = Form("web-ui"),
):
    """Web UI 创建表单提交(代理到 API)"""
    payload = {
        "title": title,
        "type": type,
        "priority": priority,
        "proposer": proposer,
    }
    if description:
        payload["description"] = description
    if user_story:
        payload["user_story"] = user_story
    if assignee:
        payload["assignee"] = assignee
    if due_date:
        payload["due_date"] = due_date
    if tags:
        payload["tags"] = [t.strip() for t in tags.split(",") if t.strip()]

    path = (
        f"/api/v1/components/{component_id}/requirements"
        if component_id
        else "/api/v1/requirements"
    )
    try:
        created = await api_post(path, payload)
    except HTTPException as e:
        return JSONResponse({"error": str(e.detail)}, status_code=e.status_code)

    from fastapi.responses import RedirectResponse
    return RedirectResponse(f"/requirements/{created['id']}", status_code=303)


@router.post("/requirements/{req_id}/patch")
async def requirement_patch_from_ui(
    req_id: str,
    request: Request,
    status: Optional[str] = Form(None),
    priority: Optional[str] = Form(None),
    assignee: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
):
    """Web UI 状态推进表单(代理 PATCH)"""
    payload = {}
    if status:
        payload["status"] = status
    if priority:
        payload["priority"] = priority
    if assignee:
        payload["assignee"] = assignee
    if description:
        payload["description"] = description

    try:
        updated = await api_patch(f"/api/v1/requirements/{req_id}", payload)
    except HTTPException as e:
        return JSONResponse({"error": str(e.detail)}, status_code=e.status_code)

    return templates.TemplateResponse(
        request,
        "requirements/_card.html",
        {"req": updated},
    )


# ===== REQ-c7b6e4a4 需求编辑页(Phase 3,2026-06-23)=====
# 设计:复用 RequirementUpdate schema(schemas.py:231),不在 UI 层重做校验。
# status 字段维持 HTMX 推进表单(职责单一),title 仅 draft 可编辑(对齐 CLAUDE.md 定位稳定性)。
import json as _json
from datetime import datetime as _dt


def _prepare_req_for_edit(req: dict) -> dict:
    """为 edit.html 模板准备渲染数据(JSON 序列化 AC/nfr;CSV 序列化 tags;date 输入格式化)"""
    req = dict(req)
    req["acceptance_criteria_json"] = _json.dumps(
        req.get("acceptance_criteria") or [], ensure_ascii=False, indent=2
    )
    req["nfr_json"] = _json.dumps(
        req.get("nfr") or {}, ensure_ascii=False, indent=2
    )
    req["tags_csv"] = ", ".join(req.get("tags") or [])
    due = req.get("due_date")
    if due:
        # accept ISO 8601 string or datetime
        if isinstance(due, str):
            req["due_date_input"] = due[:10]
        else:
            req["due_date_input"] = due.strftime("%Y-%m-%d")
    else:
        req["due_date_input"] = ""
    return req


@router.get("/requirements/{req_id}/edit", response_class=HTMLResponse)
async def requirement_edit_form(request: Request, req_id: str):
    """需求编辑表单(GET)"""
    req = await _safe_get(f"/api/v1/requirements/{req_id}")
    if not req:
        raise HTTPException(status_code=404, detail=f"需求 {req_id} 不存在")
    return templates.TemplateResponse(
        request,
        "requirements/edit.html",
        {"req": _prepare_req_for_edit(req)},
    )


@router.post("/requirements/{req_id}/edit")
async def requirement_edit_submit(
    request: Request,
    req_id: str,
    title: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    user_story: Optional[str] = Form(None),
    acceptance_criteria: Optional[str] = Form(None),
    nfr: Optional[str] = Form(None),
    priority: Optional[str] = Form(None),
    assignee: Optional[str] = Form(None),
    due_date: Optional[str] = Form(None),
    tags: Optional[str] = Form(None),
):
    """需求编辑提交(POST → 代理 PATCH,303 重定向到详情页)

    设计要点:
    - 仅当字段非空时才写入 payload,避免空字符串覆盖已有值(PATCH 语义)
    - AC/nfr 是 JSON 字符串,解析失败 → 422
    - tags 是逗号分隔,拆分 + 去空
    - 后端 PATCH 端点负责 title 锁定 / 状态流转校验
    """
    payload = {}

    # title:仅在客户端发送时才传(非 draft 时前端会 disabled,name 不提交)
    if title:
        payload["title"] = title.strip()

    if description is not None:
        payload["description"] = description or None

    if user_story is not None:
        payload["user_story"] = user_story or None

    # acceptance_criteria:JSON 数组
    if acceptance_criteria is not None and acceptance_criteria.strip():
        try:
            ac_list = _json.loads(acceptance_criteria)
            if not isinstance(ac_list, list):
                raise ValueError("acceptance_criteria must be a JSON array")
            payload["acceptance_criteria"] = ac_list
        except (ValueError, _json.JSONDecodeError) as e:
            raise HTTPException(
                status_code=422,
                detail=f"acceptance_criteria JSON 解析失败:{e}",
            )

    # nfr:JSON 对象
    if nfr is not None and nfr.strip():
        try:
            nfr_obj = _json.loads(nfr)
            if not isinstance(nfr_obj, dict):
                raise ValueError("nfr must be a JSON object")
            payload["nfr"] = nfr_obj
        except (ValueError, _json.JSONDecodeError) as e:
            raise HTTPException(
                status_code=422,
                detail=f"nfr JSON 解析失败:{e}",
            )

    if priority:
        payload["priority"] = priority

    if assignee is not None:
        payload["assignee"] = assignee or None

    if due_date:
        payload["due_date"] = f"{due_date}T00:00:00"

    if tags is not None:
        payload["tags"] = [t.strip() for t in tags.split(",") if t.strip()]

    if not payload:
        # 没改任何字段,直接回到详情页
        return RedirectResponse(f"/requirements/{req_id}", status_code=303)

    try:
        await api_patch(f"/api/v1/requirements/{req_id}", payload)
    except HTTPException as e:
        # 校验失败:回显到表单(简化版:返回 JSON 错误,前端可扩展)
        return JSONResponse(
            {"error": str(e.detail), "payload_sent": payload},
            status_code=e.status_code,
        )

    return RedirectResponse(f"/requirements/{req_id}", status_code=303)

# ===== Doubt-Driven Development UI(2026-06-21 新增)=====


@router.get("/doubt", response_class=HTMLResponse)
async def doubt_list(
    request: Request,
    verdict: Optional[str] = None,
    component: Optional[str] = None,
    created_by: Optional[str] = None,
):
    """doubt cycle 列表"""
    params = {"limit": 100}
    if verdict:
        params["verdict"] = verdict
    if component:
        params["component_id"] = component
    if created_by:
        params["created_by"] = created_by
    data = await _safe_get("/api/v1/doubt/cycles", params, default={"items": [], "total": 0})
    return templates.TemplateResponse(
        request,
        "doubt/list.html",
        {
            "items": data.get("items", []),
            "total": data.get("total", 0),
            "filters": {"verdict": verdict, "component": component, "created_by": created_by},
        },
    )


@router.get("/doubt/new", response_class=HTMLResponse)
async def doubt_new_form(request: Request):
    """新建 doubt cycle 表单(Step 1 CLAIM + Step 2 EXTRACT)"""
    return templates.TemplateResponse(request, "doubt/new.html", {})


@router.post("/doubt/run")
async def doubt_create_from_ui(
    request: Request,
    claim: str = Form(...),
    artifact: str = Form(...),
    contract: str = Form(...),
    component: str = Form(""),
    created_by: str = Form("web-ui"),
):
    """Web UI → 服务器代理 → POST /api/v1/doubt/cycle"""
    payload = {
        "claim": claim,
        "artifact": artifact,
        "contract": contract,
        "created_by": created_by,
    }
    if component:
        payload["component_id"] = component
    try:
        created = await api_post("/api/v1/doubt/cycle", payload)
    except HTTPException as e:
        return JSONResponse({"error": str(e.detail)}, status_code=e.status_code)
    from fastapi.responses import RedirectResponse
    return RedirectResponse(f"/doubt/cycles/{created['id']}", status_code=303)


@router.get("/doubt/cycles/{cycle_id}", response_class=HTMLResponse)
async def doubt_detail(request: Request, cycle_id: str):
    """doubt cycle 详情页(含 findings + 加 finding 表单 + STOP)"""
    cycle = await _safe_get(f"/api/v1/doubt/cycles/{cycle_id}")
    if not cycle:
        raise HTTPException(status_code=404, detail=f"doubt cycle {cycle_id} 不存在")
    return templates.TemplateResponse(request, "doubt/result.html", {"cycle": cycle})


@router.post("/doubt/cycles/{cycle_id}/finding-from-ui")
async def doubt_finding_from_ui(
    request: Request,
    cycle_id: str,
    category: str = Form(...),
    severity: str = Form("medium"),
    description: str = Form(...),
):
    """Web UI 加 finding(RECONCILE 步骤)"""
    try:
        await api_post(
            f"/api/v1/doubt/cycles/{cycle_id}/findings",
            {"category": category, "severity": severity, "description": description},
        )
    except HTTPException as e:
        return JSONResponse({"error": str(e.detail)}, status_code=e.status_code)
    from fastapi.responses import RedirectResponse
    return RedirectResponse(f"/doubt/cycles/{cycle_id}", status_code=303)


@router.post("/doubt/cycles/{cycle_id}/stop-from-ui")
async def doubt_stop_from_ui(
    request: Request,
    cycle_id: str,
    reason: str = Form(...),
):
    """Web UI STOP cycle"""
    try:
        await api_post(f"/api/v1/doubt/cycles/{cycle_id}/stop", {"reason": reason})
    except HTTPException as e:
        return JSONResponse({"error": str(e.detail)}, status_code=e.status_code)
    from fastapi.responses import RedirectResponse
    return RedirectResponse(f"/doubt/cycles/{cycle_id}", status_code=303)


# ===== REQ-8be0f95c /help 路由(2026-06-23)=====
# 设计要点:
# - Swagger 仍占 /docs,本模块用 /help(命名约定一致)
# - 服务端渲染(mistune + Pygments),无 JS
# - slug → file path,防越界(防 ../ + symlink)
# - 复用 base.html + PicoCSS,跟其他 UI 页风格一致


@router.get("/help", response_class=HTMLResponse)
async def help_index(request: Request):
    """列出 docs/ 下所有 markdown 文件,按 category 分组"""
    grouped = list_markdown_files_grouped()
    total = sum(len(g["files"]) for g in grouped)
    return templates.TemplateResponse(
        request,
        "help/list.html",
        {
            "groups": grouped,
            "total": total,
        },
    )


@router.get("/help/{slug:path}", response_class=HTMLResponse)
async def help_detail(request: Request, slug: str):
    """渲染单个 markdown 文件

    slug 例:
      er-diagram           → docs/er-diagram.md
      adr/0022-...         → docs/adr/0022-....md
      components/docker    → docs/components/docker.md
    """
    md_path = resolve_slug(slug)
    if md_path is None:
        raise HTTPException(status_code=404, detail=f"文档 {slug} 不存在")

    try:
        html_body = render_markdown_file(md_path)
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"读取文档失败:{e}")

    # breadcrumb:category(从 slug 第一段推断)+ 文件名
    parts = slug.split("/")
    if len(parts) == 1:
        category = "概述"
    else:
        sub = parts[0]
        category_map = {"adr": "ADR", "components": "组件", "design": "设计"}
        category = category_map.get(sub, sub)

    # 取标题(从 markdown 第一个 # 头抽),detail 顶部展示
    title = md_path.stem

    return templates.TemplateResponse(
        request,
        "help/detail.html",
        {
            "html_body": html_body,
            "slug": slug,
            "category": category,
            "title": title,
            "filename": md_path.name,
            "pygments_css": get_pygments_css(),
            "docs_dir": str(DOCS_DIR),
        },
    )


# ===== Literature 知识资产 UI(REQ-7c4bcb32,2026-06-23)=====
# 平台首例「知识资产」实体 — 架构文献/论文收集
# 设计:对齐 Requirement UI 模式(列表 + 详情 + 表单 + 编辑)


def _prepare_lit_for_form(lit: dict) -> dict:
    """为 new/edit 表单准备渲染数据(tags CSV)"""
    lit = dict(lit)
    lit["tags_csv"] = ", ".join(lit.get("tags") or [])
    return lit


@router.get("/literature", response_class=HTMLResponse)
async def literature_list(
    request: Request,
    q: Optional[str] = None,
    tag: Optional[str] = None,
):
    """文献列表(支持搜索 + tag 过滤)"""
    params = {"limit": 200}
    if q:
        params["q"] = q
    if tag:
        params["tag"] = tag
    data = await _safe_get(
        "/api/v1/literatures", params, default={"items": [], "total": 0}
    )
    # 聚合所有 tags(用于 filter dropdown)
    all_tags = set()
    for lit in data.get("items", []):
        for t in lit.get("tags") or []:
            all_tags.add(t)
    return templates.TemplateResponse(
        request,
        "literature/list.html",
        {
            "items": data.get("items", []),
            "total": data.get("total", 0),
            "filters": {"q": q, "tag": tag},
            "all_tags": sorted(all_tags),
        },
    )


@router.get("/literature/new", response_class=HTMLResponse)
async def literature_new_form(request: Request):
    """新建文献表单"""
    return templates.TemplateResponse(request, "literature/new.html", {})


@router.post("/literature/create")
async def literature_create_from_ui(
    request: Request,
    title: str = Form(...),
    url: str = Form(...),
    authors: Optional[str] = Form(None),
    summary: Optional[str] = Form(None),
    source: Optional[str] = Form(None),
    tags: Optional[str] = Form(None),
    added_by: str = Form("web-ui"),
):
    """Web UI 创建文献(代理到 POST /api/v1/literatures)"""
    payload = {
        "title": title,
        "url": url,
        "added_by": added_by,
    }
    if authors:
        payload["authors"] = authors
    if summary:
        payload["summary"] = summary
    if source:
        payload["source"] = source
    if tags:
        payload["tags"] = [t.strip() for t in tags.split(",") if t.strip()]

    try:
        created = await api_post("/api/v1/literatures", payload)
    except HTTPException as e:
        return JSONResponse({"error": str(e.detail)}, status_code=e.status_code)
    return RedirectResponse(f"/literature/{created['id']}", status_code=303)


@router.get("/literature/{lit_id}", response_class=HTMLResponse)
async def literature_detail(request: Request, lit_id: str):
    """文献详情页"""
    lit = await _safe_get(f"/api/v1/literatures/{lit_id}")
    if not lit:
        raise HTTPException(status_code=404, detail=f"文献 {lit_id} 不存在")
    return templates.TemplateResponse(
        request,
        "literature/detail.html",
        {"lit": lit},
    )


@router.get("/literature/{lit_id}/edit", response_class=HTMLResponse)
async def literature_edit_form(request: Request, lit_id: str):
    """编辑文献表单(GET)"""
    lit = await _safe_get(f"/api/v1/literatures/{lit_id}")
    if not lit:
        raise HTTPException(status_code=404, detail=f"文献 {lit_id} 不存在")
    return templates.TemplateResponse(
        request,
        "literature/edit.html",
        {"lit": _prepare_lit_for_form(lit)},
    )


@router.post("/literature/{lit_id}/edit")
async def literature_edit_submit(
    request: Request,
    lit_id: str,
    title: Optional[str] = Form(None),
    url: Optional[str] = Form(None),
    authors: Optional[str] = Form(None),
    summary: Optional[str] = Form(None),
    source: Optional[str] = Form(None),
    tags: Optional[str] = Form(None),
):
    """编辑文献提交(POST → 代理 PATCH,303 重定向)"""
    payload = {}
    if title:
        payload["title"] = title.strip()
    if url:
        payload["url"] = url.strip()
    if authors is not None:
        payload["authors"] = authors or None
    if summary is not None:
        payload["summary"] = summary or None
    if source is not None:
        payload["source"] = source or None
    if tags is not None:
        payload["tags"] = [t.strip() for t in tags.split(",") if t.strip()]

    if not payload:
        return RedirectResponse(f"/literature/{lit_id}", status_code=303)

    try:
        await api_patch(f"/api/v1/literatures/{lit_id}", payload)
    except HTTPException as e:
        return JSONResponse(
            {"error": str(e.detail), "payload_sent": payload},
            status_code=e.status_code,
        )
    return RedirectResponse(f"/literature/{lit_id}", status_code=303)


# ===== Audit Module(REQ-7328c640, 2026-06-23)=====
# 每日 04:00 cron → scan.py → POST /api/v1/audit/runs → 这里只读展示


@router.get("/audit", response_class=HTMLResponse)
async def audit_list(
    request: Request,
    status: Optional[str] = None,
    severity_min: Optional[str] = None,
):
    """audit run 列表(分页 + 过滤)

    过滤:
      - status: running / completed / failed
      - severity_min: blocker / warn / info(对应 summary 计数 > 0)
    """
    params = {"limit": 100}
    if status:
        params["status"] = status
    if severity_min:
        params["severity_min"] = severity_min
    data = await _safe_get("/api/v1/audit/runs", params, default={"items": [], "total": 0})
    return templates.TemplateResponse(
        request,
        "audit/list.html",
        {
            "items": data.get("items", []),
            "total": data.get("total", 0),
            "filters": {"status": status, "severity_min": severity_min},
        },
    )


@router.get("/audit/{run_id}", response_class=HTMLResponse)
async def audit_detail(request: Request, run_id: str):
    """audit run 详情页

    布局:
      1. 顶部 summary 卡片(scope / gate / total / blocker / warn / info / 时间)
      2. 按 9 原则分组的 finding 表(severity 色 badge)
    """
    run = await _safe_get(f"/api/v1/audit/runs/{run_id}")
    if not run:
        raise HTTPException(status_code=404, detail=f"audit run {run_id} 不存在")

    findings = run.get("findings", []) or []
    # 按 principle 分组(顺序保留首次出现)
    grouped: dict[str, list] = {}
    order: list[str] = []
    for f in findings:
        p = f.get("principle") or "(未分类)"
        if p not in grouped:
            grouped[p] = []
            order.append(p)
        grouped[p].append(f)

    return templates.TemplateResponse(
        request,
        "audit/detail.html",
        {
            "run": run,
            "findings": findings,
            "grouped": grouped,
            "principle_order": order,
        },
    )
