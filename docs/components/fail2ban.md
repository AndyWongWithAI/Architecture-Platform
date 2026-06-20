---
name: fail2ban
title: fail2ban SSH 防爆破
layer: L1_platform
category: monitor
scope: infra
atomic: true
composed_of: []
tags:
  - security
  - ssh
  - brute-force
  - intrusion-prevention
language: python
package_name: ""
install_command: "apt install fail2ban && systemctl enable fail2ban"
usage_example: "fail2ban-client status sshd"
status: stable
repo_url: ""
---

# fail2ban SSH 防爆破

## 定位

L1 平台层的安全组件,扫描 SSH 登录日志,自动封禁多次失败的 IP。是 SSH 公钥认证(fail2ban 不能替代公钥认证,是补充)的第二道防线。

## 版本历史

| 版本 | 时间 | 变更 |
|------|------|------|
| (apt default) | 2026-06-20 | #1 启用 |
| (apt default) | 2026-06-19 | #2 启用 |
| (apt default) | 2026-06-20 | #3 启用 |

## 部署位置

| 主机 | 状态 | jail |
|------|------|------|
| #1 | ✅ active | `sshd` 默认配置 |
| #2 | ✅ active | `sshd` 默认配置 |
| #3 | ✅ active | `sshd` 默认配置 |

## 默认策略

- **maxretry**: 5 次失败
- **findtime**: 10 分钟
- **bantime**: 10 分钟
- **action**: iptables drop

## 备注

- SSH 公钥认证(见 `ssh-key-auth` 组件)是更根本的防线,fail2ban 是补位
- 高频攻击 IP 可考虑永久 ban(jail.local 改 bantime = -1)