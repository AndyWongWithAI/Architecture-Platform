---
name: intelab.cn-website
title: intelab.cn 占位网站
layer: L3_application
category: ui
scope: app
atomic: false
composed_of:
  - component_id: nginx
    version_constraint: "^1.24"
  - component_id: certbot
    version_constraint: ">=1.0"
tags:
  - website
  - static-site
  - landing-page
language: html
package_name: ""
install_command: ""
usage_example: "https://intelab.cn"
status: stable
repo_url: ""
is_asset: false
distribution_form: ""
interface_contract: ""
---

# intelab.cn 占位网站

## 定位

L3 应用层的对外 Web 站点,基于 `nginx` + `certbot` L1 平台层组合而成。当前是 SDLC Phase 6 部署产物(占位站),未来会承载真实业务。

## 版本历史

| 版本 | 时间 | 变更 |
|------|------|------|
| 1.0.0 | 2026-06-20 | 初始部署:占位 HTML + nginx + certbot |

## 部署位置

| 主机 | 环境 | 路径 | 配置哈希 |
|------|------|------|---------|
| #1 | prod | `/var/www/intelab.cn/index.html` | sha256:(待算) |

## 依赖拓扑

```
intelab.cn-website (L3 composite)
├── nginx (L1, ^1.24)
└── certbot (L1, >=1.0)
```

## 当前内容

```html
<!doctype html>
<html lang="zh-CN">
<head><meta charset="utf-8"><title>intelab.cn</title></head>
<body><h1>intelab.cn — 黄谦敏</h1></body>
</html>
```

## 备注

- 这是首个 L3 复合组件登记样本,验证分层一致 + composed_of 校验
- 未来内容替换会触发新 Version 登记(major bump)
- HTTP → HTTPS 301 重定向是 `nginx` 配置,不是 L3 应用本身的责任