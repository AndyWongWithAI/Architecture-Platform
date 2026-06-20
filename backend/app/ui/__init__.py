"""app/ui — Web UI 模块(Phase 4)

SSR 模式:Jinja2Templates + HTMX + PicoCSS(全部 CDN)
8 个页面:
  /                       总览
  /components             组件列表
  /components/{name}      组件详情
  /components/{name}/tree 依赖树
  /feedbacks              反馈看板(Kanban,支持 PATCH)
  /deployments            部署地图
  /search?q=...           跨实体搜索
  /healthz                健康检查

唯一允许的写操作:feedback PATCH(服务器代理 API Key)
"""