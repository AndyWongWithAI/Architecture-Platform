---
name: ufw
title: UFW 防火墙(Uncomplicated Firewall)
layer: L1_platform
category: monitor
scope: infra
atomic: true
composed_of: []
tags:
  - firewall
  - security
  - iptables
  - ubuntu
language: other
package_name: ""
install_command: "apt install ufw && ufw enable"
usage_example: "ufw allow 22/tcp && ufw status"
status: stable
repo_url: ""
---

# UFW 防火墙

## 定位

L1 平台层的安全组件,基于 iptables 提供简化的防火墙规则管理。所有对外暴露的端口(SSH/HTTP/HTTPS)必须显式 allow,符合"最小暴露"原则。

## 版本历史

| 版本 | 时间 | 变更 |
|------|------|------|
| (apt default) | 2026-06-20 | #1 启用 + 配 22/80/443 |
| (apt default) | 2026-06-19 | #2 启用 |
| (apt default) | 2026-06-20 | #3 启用 |

## 部署位置

| 主机 | 状态 | 已开放端口 | 备注 |
|------|------|----------|------|
| #1 | ✅ active | 22/80/443/tcp | SSL 申请时新开 80/443 |
| #2 | ✅ active | 22/tcp(+ minimax-proxy 临时端口) | minimax-proxy 下线后清理 |
| #3 | ✅ active | 22/tcp(基线) | — |

## 关键命令

```bash
ufw status verbose       # 看规则
ufw allow 8088/tcp       # 架构平台未来端口
ufw deny 22000/tcp       # 关闭 minimax-proxy 端口(下线时)
```

## 备注

- 所有 L2 业务组件如果需要新端口,必须通过架构平台登记 → 触发 UFW 规则审查
- L3 应用对外端口由 L1 nginx 反代,不需要直接放行到公网