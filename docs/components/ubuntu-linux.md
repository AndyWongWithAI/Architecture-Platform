---
name: ubuntu-linux
title: Ubuntu 24.04 LTS 服务器系统
layer: L0_infrastructure
category: other
scope: infra
atomic: true
composed_of: []
tags:
  - linux
  - ubuntu
  - os
  - noble
  - kernel
language: other
package_name: ""
install_command: ""
usage_example: ""
status: stable
repo_url: ""
is_asset: true
distribution_form: binary
interface_contract: ""
knowledge_artifact: false
---

# Ubuntu 24.04 LTS(Noble Numbat)

## 定位

L0 基础设施层的操作系统基线。所有 L1/L2/L3 组件的运行载体。三台云服务器统一基线,符合 CLAUDE.md 一致性原则。

## 版本历史

| 版本 | 时间 | 变更 |
|------|------|------|
| 24.04.4 LTS(Noble) | 2026-06-20 | #1 重装对齐基线 |
| 24.04.4 LTS(Noble) | 2026-06-19 | #2 对齐基线 |
| 24.04.2 LTS(Noble) | 2026-06-20 | #3 对齐基线 |

## 部署位置

| 主机 | 内核 | 内存 | 磁盘 | Swap |
|------|------|------|------|------|
| #1 华为云 | 6.8.0-106-generic | 1.7G / 1.3G 可用 | 40G / 12% | 1.0G(`/swapfile`) |
| #2 腾讯云 | 6.8.0-124-generic | 3.6G / 2.7G 可用 | 59G / 32% | 1.9G(`/swap.img`) |
| #3 阿里云 | 6.8.0-(同 #1) | (对齐中) | (对齐中) | 1.0G |

## 已装基线工具

- Node.js v22.23.0(NodeSource 仓库)
- npm 10.9.8
- Python 3.12.3
- Docker 29.6.0 + Compose v5.1.4
- git / vim / htop / jq / tmux / curl / wget / fail2ban-client / ufw

## 备注

- #1 不 reboot 保持内核 -106(2026-06-19 reboot 教训:sshd 弄丢过)
- #2 已 reboot 到最新内核 -124
- #3 内核状态待确认