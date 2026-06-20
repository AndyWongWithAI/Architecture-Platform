"""Component routes — GET endpoints (Phase 1.0 MVP)
POST/PATCH 留到 Phase 1.1(本会话不实现)
"""
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Component, Version, Layer, ComponentStatus
from ..schemas import ComponentOut, ComponentDetail, ComponentList, ComponentTreeNode, ComponentUsage

router = APIRouter()


@router.get("", response_model=ComponentList)
def list_components(
    q: Optional[str] = Query(None, description="关键词搜索 name/title/positioning/tags"),
    layer: Optional[Layer] = None,
    category: Optional[str] = None,
    is_asset: Optional[bool] = Query(None, description="None=全部;true=只真资产;false=只项目级"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """列出/搜索组件(默认 is_asset=true 在 Phase 1.1 启用;当前返回全部)"""
    query = db.query(Component)
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