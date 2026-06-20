---
name: ssh-key-auth
title: SSH 公私钥认证
layer: L1_platform
category: auth
scope: infra
atomic: true
composed_of: []
tags:
  - ssh
  - authentication
  - ed25519
  - key-based
language: other
package_name: ""
install_command: ""
usage_example: "ssh -i ~/.ssh/id_ed25519 ubuntu@server"
status: stable
repo_url: ""
is_asset: true
distribution_form: source
interface_contract: ""
---

# SSH 公私钥认证

## 定位

L1 平台层的身份认证组件,用 ed25519 公私钥对替换密码登录。是 `fail2ban` 的根本补充(密钥不可能被暴力破解)。

## 部署位置

| 主机 | 用户 | 认证方式 | 公钥位置 |
|------|------|---------|---------|
| #1 | root | ed25519 公钥 | `~/.ssh/authorized_keys` |
| #2 | ubuntu | ed25519 公钥 | `~/.ssh/authorized_keys` |
| #3 | (待对齐) | ed25519 公钥 | `~/.ssh/authorized_keys` |

## 关键配置(各服务器 `/etc/ssh/sshd_config.d/`)

```sshd_config
# 关闭密码登录
PasswordAuthentication no
PermitRootLogin prohibit-password  # 仅 #1 保留 root,需密钥
PubkeyAuthentication yes
```

## 备注

- 2026-06-19/20 完成所有服务器密钥对齐(从密码登录迁到公私钥)
- WSL 本地用 `~/.ssh/config` 指定 `IdentityFile`,避开 Windows 路径干扰
- 后续 ops 操作一律 `ssh <alias>`,不再用密码