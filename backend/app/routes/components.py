"""Component routes — GET + POST + PATCH (Phase 1.1)
- GET: 公开,无需鉴权
- POST / PATCH: 必须 X-API-Key(由 require_api_key 中间件强制)
"""
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Component, Version, Layer, ComponentStatus, SemverIntent
from ..schemas import (
    ComponentOut, ComponentDetail, ComponentList,
    ComponentTreeNode, ComponentUsage,
    ComponentCreate, ComponentUpdate,
    VersionCreate, VersionOut, VersionList,
)
from ..auth import require_api_key

router = APIRouter()


@router.get("", response_model=ComponentList)
def list_components(
    q: Optional[str] = Query(None, description="关键词搜索 name/title/positioning/tags"),
    name: Optional[str] = Query(None, description="按 name 精确过滤(修复 FB-4:之前该参数被忽略,直接返回第一项)"),
    layer: Optional[Layer] = None,
    category: Optional[str] = None,
    is_asset: Optional[bool] = Query(None, description="None=全部;true=只真资产;false=只项目级"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """列出/搜索组件(默认 is_asset=true 在 Phase 1.1 启用;当前返回全部)"""
    query = db.query(Component)
    if name:
        # FB-4 修复:name 精确过滤(kebab-case 唯一,适合脚本化批量操作)
        query = query.filter(Component.name == name)
    if q:
        like = f"%{q}%"
        query = query.filter(
            (Component.name.like(like))
            | (Component.title.like(like))
            | (Component.positioning.like(like))
        )
    if layer:
        query = query.filter(Component.layer == layer)
    if category:
        query = query.filter(Component.category == category)
    if is_asset is not None:
        query = query.filter(Component.is_asset == is_asset)
    total = query.count()
    items = query.order_by(Component.layer, Component.name).offset(offset).limit(limit).all()
    return {"items": items, "total": total}


@router.get("/{component_id}", response_model=ComponentDetail)
def get_component(component_id: str, db: Session = Depends(get_db)):
    """组件详情(含版本列表)"""
    comp = db.query(Component).filter(Component.id == component_id).first()
    if not comp:
        # 兼容按 name 查询
        comp = db.query(Component).filter(Component.name == component_id).first()
    if not comp:
        raise HTTPException(404, "component not found")
    return comp


@router.get("/{component_id}/tree", response_model=ComponentTreeNode)
def get_component_tree(
    component_id: str,
    max_depth: int = Query(5, ge=1, le=10),
    db: Session = Depends(get_db),
):
    """展开 composed_of 依赖树"""
    comp = db.query(Component).filter(
        (Component.id == component_id) | (Component.name == component_id)
    ).first()
    if not comp:
        raise HTTPException(404, "component not found")

    def build_tree(c: Component, depth: int = 0, visited: set = None) -> ComponentTreeNode:
        visited = visited or set()
        if c.id in visited:
            return ComponentTreeNode(component=c, children=[])
        visited.add(c.id)
        children = []
        if depth < max_depth and c.composed_of:
            for entry in c.composed_of:
                child = db.query(Component).filter(
                    (Component.id == entry.get("component_id"))
                    | (Component.name == entry.get("component_id"))
                ).first()
                if child:
                    children.append(build_tree(child, depth + 1, visited))
        return ComponentTreeNode(component=c, children=children)

    return build_tree(comp)


@router.get("/{component_id}/usage", response_model=ComponentUsage)
def get_component_usage(component_id: str, db: Session = Depends(get_db)):
    """取出 install_command + usage_example + 当前版本(arch use 的输出)"""
    comp = db.query(Component).filter(
        (Component.id == component_id) | (Component.name == component_id)
    ).first()
    if not comp:
        raise HTTPException(404, "component not found")
    current_ver = None
    if comp.current_version_id:
        ver = db.query(Version).filter(Version.id == comp.current_version_id).first()
        if ver:
            current_ver = ver.version
    return ComponentUsage(
        component=comp,
        install_command=comp.install_command,
        usage_example=comp.usage_example,
        current_version=current_ver,
    )


# FB-H 修复(2026-06-21):组件关联反馈端点
@router.get("/{component_id}/feedbacks")
def get_component_feedbacks(component_id: str, db: Session = Depends(get_db)):
    """列出该组件所有版本关联的反馈(用于组件详情页)

    实现:通过 Component 找所有 Version,再查 Version 关联的 Feedback
    """
    from ..models import Feedback  # 避免循环 import
    comp = db.query(Component).filter(
        (Component.id == component_id) | (Component.name == component_id)
    ).first()
    if not comp:
        raise HTTPException(404, "component not found")
    version_ids = [v.id for v in comp.versions] if comp.versions else []
    if version_ids:
        items = db.query(Feedback).filter(Feedback.version_id.in_(version_ids)).order_by(Feedback.created_at.desc()).all()
    else:
        # 没 version 时直接查 component_id(向后兼容老数据)
        items = db.query(Feedback).filter(Feedback.version_id == comp.id).order_by(Feedback.created_at.desc()).all()
    return {"items": items, "total": len(items)}


# Phase 1.2(2026-06-21):组件关联需求端点 — 嵌套创建 + 反查
@router.get("/{component_id}/requirements")
def get_component_requirements(component_id: str, db: Session = Depends(get_db)):
    """反查:该 component 下登记的所有需求"""
    from ..models import Requirement
    comp = db.query(Component).filter(
        (Component.id == component_id) | (Component.name == component_id)
    ).first()
    if not comp:
        raise HTTPException(404, "component not found")
    items = (
        db.query(Requirement)
        .filter(Requirement.component_id == comp.id, Requirement.is_archived == False)  # noqa: E712
        .order_by(Requirement.priority.asc(), Requirement.created_at.desc())
        .all()
    )
    return {"items": items, "total": len(items)}


@router.post(
    "/{component_id}/requirements",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_api_key)],
)
def create_requirement_under_component(
    component_id: str,
    payload: dict,  # 透传给 requirements._create_requirement_impl
    db: Session = Depends(get_db),
):
    """嵌套入口:在指定 component 下创建需求(component_id 自动绑定)"""
    from ..schemas import RequirementCreate
    from .requirements import _create_requirement_impl
    # 强制 component_id 与 URL 一致,防止 body 里传别的 component_id
    payload = dict(payload)
    payload["component_id"] = component_id
    parsed = RequirementCreate(**payload)
    req = _create_requirement_impl(db, parsed)
    from ..schemas import RequirementOut
    return RequirementOut.model_validate(req)


# ===== 写操作(POST / PATCH)— Phase 1.1 =====
# 必须带 X-API-Key(由 require_api_key 强制)


def _validate_component_business_rules(payload, db: Session, exclude_id: Optional[str] = None):
    """业务规则校验(超出 Pydantic schema 的语义检查)
    抛 HTTPException 表示校验失败
    """
    # 1. 资产判定一致性
    if payload.is_asset:
        # 真资产必须填 distribution_form
        if not payload.distribution_form:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "is_asset=true requires distribution_form to be set",
            )
        # http_api 必须填 interface_contract
        if payload.distribution_form.value == "http_api" and not payload.interface_contract:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "distribution_form=http_api requires interface_contract to be set",
            )

    # 2. 原子性自洽
    if payload.atomic and payload.composed_of:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "atomic=true requires composed_of to be empty",
        )
    if not payload.atomic:
        if not payload.composed_of:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "atomic=false requires composed_of to be non-empty",
            )
        # 复合组件:每个子组件必须存在
        for entry in payload.composed_of:
            child = db.query(Component).filter(
                (Component.id == entry.component_id)
                | (Component.name == entry.component_id)
            ).first()
            if not child:
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_ENTITY,
                    f"composed_of references non-existent component: {entry.component_id}",
                )


@router.post(
    "",
    response_model=ComponentOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_api_key)],
)
def create_component(payload: ComponentCreate, db: Session = Depends(get_db)):
    """创建组件(需要 API Key)"""
    # name 唯一性
    existing = db.query(Component).filter(Component.name == payload.name).first()
    if existing:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"component with name '{payload.name}' already exists",
        )

    # 业务规则校验
    _validate_component_business_rules(payload, db)

    comp = Component(
        id=_gen_uuid(),
        **payload.model_dump(),
    )
    db.add(comp)
    db.commit()
    db.refresh(comp)
    return comp


@router.patch(
    "/{component_id}",
    response_model=ComponentOut,
    dependencies=[Depends(require_api_key)],
)
def update_component(
    component_id: str,
    payload: ComponentUpdate,
    db: Session = Depends(get_db),
):
    """更新组件(部分字段,需要 API Key)"""
    comp = db.query(Component).filter(
        (Component.id == component_id) | (Component.name == component_id)
    ).first()
    if not comp:
        raise HTTPException(404, "component not found")

    # 应用 patch(只更新显式提供的字段)
    update_data = payload.model_dump(exclude_unset=True)
    for key, val in update_data.items():
        setattr(comp, key, val)

    # 重新做完整业务规则校验(基于 patch 后的最终状态)
    _validate_component_business_rules(
        ComponentCreate(
            name=comp.name, title=comp.title, positioning=comp.positioning,
            category=comp.category, scope=comp.scope, layer=comp.layer,
            atomic=comp.atomic, composed_of=comp.composed_of or [],
            is_asset=comp.is_asset, distribution_form=comp.distribution_form,
            interface_contract=comp.interface_contract,
            knowledge_artifact=comp.knowledge_artifact,
        ),
        db,
        exclude_id=comp.id,
    )

    db.commit()
    db.refresh(comp)
    return comp


def _gen_uuid() -> str:
    import uuid
    return str(uuid.uuid4())


@router.get(
    "/{component_id}/versions",
    response_model=VersionList,
)
def list_component_versions(
    component_id: str,
    db: Session = Depends(get_db),
):
    """列出某组件的所有版本(FB-6f84124c:arch CLI version list 405 修复)"""
    comp = db.query(Component).filter(
        (Component.id == component_id) | (Component.name == component_id)
    ).first()
    if not comp:
        raise HTTPException(404, "component not found")
    items = (
        db.query(Version)
        .filter(Version.component_id == comp.id)
        .order_by(Version.created_at.desc())
        .all()
    )
    return VersionList(items=items, total=len(items))


@router.post(
    "/{component_id}/versions",
    response_model=VersionOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_api_key)],
)
def create_version(
    component_id: str,
    payload: VersionCreate,
    db: Session = Depends(get_db),
):
    """为组件创建新版本(需要 API Key)

    业务规则:
    - SemVer 格式由 Pydantic 校验(已配)
    - semver_intent=major 时,breaking_changes 必填(CLAUDE.md 一致性)
    - 创建后自动更新 Component.current_version_id 指向新版本
    """
    comp = db.query(Component).filter(
        (Component.id == component_id) | (Component.name == component_id)
    ).first()
    if not comp:
        raise HTTPException(404, "component not found")

    # major 必须填 breaking_changes
    if payload.semver_intent == SemverIntent.major and not payload.breaking_changes:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "semver_intent=major requires breaking_changes to be set (CLAUDE.md consistency)",
        )

    # 组件内 version 唯一性
    existing = db.query(Version).filter(
        Version.component_id == comp.id,
        Version.version == payload.version,
    ).first()
    if existing:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"version '{payload.version}' already exists for component '{comp.name}'",
        )

    ver = Version(
        id=_gen_uuid(),
        component_id=comp.id,
        version=payload.version,
        semver_intent=payload.semver_intent,
        design_doc=payload.design_doc,
        design_decided_at=None,
        replaces_version=payload.replaces_version,
        changelog=payload.changelog,
        breaking_changes=payload.breaking_changes,
        deprecates=payload.deprecates or [],
        compatibility_window=payload.compatibility_window,
    )
    db.add(ver)
    db.flush()  # 拿 id 但不 commit

    # 更新 Component.current_version_id
    comp.current_version_id = ver.id

    db.commit()
    db.refresh(ver)
    return ver