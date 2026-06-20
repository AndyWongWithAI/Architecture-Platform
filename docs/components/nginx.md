---
name: nginx
title: Nginx Web 服务器 / 反向代理
layer: L1_platform
category: ui
scope: infra
atomic: true
composed_of: []
tags:
  - web-server
  - http
  - https
  - reverse-proxy
  - http2
language: c
package_name: ""
install_command: "apt install nginx"
usage_example: "nginx -t && systemctl reload nginx"
status: stable
repo_url: ""
is_asset: true
distribution_form: package
interface_contract: ""
knowledge_artifact: false
---

# Nginx Web 服务器 / 反向代理

## 定位

L1 平台层的 HTTP/HTTPS 入口组件。对外提供 Web 服务 + 反向代理 + 静态文件托管。是 `intelab.cn-website` L3 应用的前置入口,也是未来架构平台(Phase 1 端口 8088)的反代上游。

## 版本历史

| 版本 | 时间 | 变更 |
|------|------|------|
| 1.24.0(Ubuntu) | 2026-06-20 | #1 安装 + reload,绑 intelab.cn |

## 部署位置

| 主机 | 状态 | 监听 | 服务 | 配置路径 |
|------|------|------|------|---------|
| #1 | ✅ active | 0.0.0.0:80, 0.0.0.0:443 | `intelab.cn-website` + 未来架构平台 | `/etc/nginx/sites-enabled/` |

## 关键配置

```nginx
# HTTP → HTTPS 301 重定向
server {
    listen 80;
    server_name intelab.cn www.intelab.cn;
    return 301 https://$host$request_uri;
}

# HTTPS 服务
server {
    listen 443 ssl http2;
    server_name intelab.cn www.intelab.cn;
    ssl_certificate /etc/letsencrypt/live/intelab.cn/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/intelab.cn/privkey.pem;
    root /var/www/intelab.cn;
    index index.html;
}
```

## 备注

- 架构平台 Phase 1 上线后会加一个 `server { listen 127.0.0.1:8088; ... }` 反代段
- 公网只暴露 80/443,所有应用通过 Nginx 反代到 localhost
- 未来加 rate limiting + gzip + 静态资源缓存策略