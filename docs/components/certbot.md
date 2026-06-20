---
name: certbot
title: Certbot / Let's Encrypt SSL 证书自动化
layer: L1_platform
category: deploy
scope: tool
atomic: true
composed_of: []
tags:
  - ssl
  - letsencrypt
  - https
  - tls
  - certificate
language: python
package_name: ""
install_command: "apt install certbot"
usage_example: "certbot certonly --nginx -d intelab.cn -d www.intelab.cn"
status: stable
repo_url: https://github.com/certbot/certbot
---

# Certbot / Let's Encrypt SSL 证书自动化

## 定位

L1 平台层的证书管理组件,为 `nginx` 提供免费、自动续期的 TLS 证书。是 HTTPS 服务的必要前置。

## 版本历史

| 版本 | 时间 | 变更 |
|------|------|------|
| (apt default) | 2026-06-20 | #1 申请 intelab.cn + www.intelab.cn 证书,有效期 2026-06-20 → 2026-09-17 |

## 部署位置

| 主机 | 证书路径 | 自动续期 | 下次续期 |
|------|---------|---------|---------|
| #1 | `/etc/letsencrypt/live/intelab.cn/` | ✅ systemd timer | 2026-09-17 前后 |

## 关键命令

```bash
# 申请证书(Nginx 模式)
certbot certonly --nginx -d intelab.cn -d www.intelab.cn

# 手动测试续期
certbot renew --dry-run

# 看证书详情
certbot certificates
```

## 备注

- 证书有效期 90 天,certbot timer 自动 30 天内续期
- 跟 `nginx` 是 L1 平台层组合,被 L3 `intelab.cn-website` 复合引用