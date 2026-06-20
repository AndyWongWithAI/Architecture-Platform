# 组件登记总览

> 临时 Markdown 登记(Phase 1 启动前),Phase 1 上线后 importer 转 SQLite DB

## 按层(L0-L3)浏览

### L0 Infrastructure(基础设施)
- [`docker`](docker.md) — Docker 容器引擎 ✅
- [`ubuntu-linux`](ubuntu-linux.md) — Ubuntu 24.04 LTS 系统 ✅

### L1 Platform(平台/中间件)
- [`nginx`](nginx.md) — Nginx Web 服务器 / 反向代理 ✅
- [`certbot`](certbot.md) — Let's Encrypt SSL 自动化 ✅
- [`ssh-key-auth`](ssh-key-auth.md) — SSH 公钥认证 ✅
- [`ufw`](ufw.md) — UFW 防火墙 ✅
- [`fail2ban`](fail2ban.md) — SSH 防爆破 ✅

### L2 Capability(可复用业务能力)
- [`minimax-proxy`](minimax-proxy.md) — MiniMax API 代理 ⚠️ deprecated

### L3 Application(应用)
- [`intelab.cn-website`](intelab.cn-website.md) — intelab.cn 占位站 ✅

## 统计

| 指标 | 数量 |
|------|------|
| 总组件数 | 9 |
| 稳定 (`status=stable`) | 8 |
| 弃用 (`status=deprecated`) | 1 |
| 原子 (`atomic=true`) | 8 |
| 复合 (`atomic=false`) | 1 |
| **真资产 (`is_asset=true`)** | **7** |
| **项目级 (`is_asset=false`)** | **2**(minimax-proxy / intelab.cn-website) |
| `distribution_form=package` | 5 |
| `distribution_form=source` | 2 |
| L0 | 2 |
| L1 | 5 |
| L2 | 1 |
| L3 | 1 |

> 判定依据见 [`../asset-criteria.md`](../asset-criteria.md)。

## 文件结构

每个组件文件 = YAML frontmatter(机器可读)+ Markdown body(人类可读):

```yaml
---
name: docker          # kebab-case,唯一
title: Docker 容器引擎  # 人类可读
layer: L0_infrastructure  # L0/L1/L2/L3
category: deploy     # auth/db/.../other
scope: infra         # app/infra/lib/tool
atomic: true         # true=原子/false=复合
composed_of: []      # 仅 atomic=false 时填
tags: [docker, ...]  # 标签
language: go         # 主要语言
package_name: ""     # pypi/npm 名(distribution_form=package 时填)
install_command: ""  # 一行安装命令(is_asset=true 时必填)
usage_example: ""    # 一行使用示例
status: stable       # draft/stable/deprecated/archived
repo_url: ""         # GitHub repo
is_asset: true       # 是否可复用资产(CLAUDE.md 资产原则);false=项目级代码,登记仅为追溯
distribution_form: package  # package/container/source/http_api;is_asset=true 时必填
interface_contract: ""      # OpenAPI Spec URL 或接口契约文本;http_api 时必填
---
```

## Phase 1 Importer 设计(预演)

Phase 1 启动后,importer 会读这些 YAML frontmatter,转成 SQLite:

```python
# 伪代码
for md_file in docs/components/*.md:
    frontmatter = parse_yaml(md_file.frontmatter)
    component = Component(
        name=frontmatter['name'],
        title=frontmatter['title'],
        layer=frontmatter['layer'],
        category=frontmatter['category'],
        ...
    )
    db.add(component)
db.commit()
```

字段映射对照 `docs/data-dictionary.md` 的 Component 实体。