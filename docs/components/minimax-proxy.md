---
name: minimax-proxy
title: MiniMax API 代理服务
layer: L2_capability
category: util
scope: tool
atomic: true
composed_of: []
tags:
  - proxy
  - api-gateway
  - minimax
  - deprecated
language: other
package_name: ""
install_command: ""
usage_example: ""
status: deprecated
repo_url: ""
---

# MiniMax API 代理服务

## 定位

> ⚠️ **状态:deprecated(2026-06-20 用户决策)**
>
> 用户决策:**自建后端服务**,优先做架构平台;
> minimax-proxy 业务下线或迁移,具体方式未定。

L2 业务层的 API 代理组件,曾用于转发到 MiniMax API。**当前待下线/迁移**——业务归属未明确。

## 版本历史

| 版本 | 时间 | 变更 |
|------|------|------|
| (历史) | 2026-06-19 之前 | 对齐基线前的原业务 |
| (现状) | 2026-06-20 | deprecated,等服务下线/迁移 |

## 部署位置

| 主机 | 状态 | 端口 | 备注 |
|------|------|------|------|
| #2 | ⚠️ 待下线 | 22000 / 8384 / 53 / 8899 | systemd: `minimax-proxy.service` |

## 待办(用户决策)

- [ ] 决定迁移目标(下线 / 迁到 #1 / 迁到 #3)
- [ ] 通知 minimax-proxy 的用户/客户端
- [ ] 停服务:`systemctl stop minimax-proxy`
- [ ] 清理端口:`ufw deny 22000/8384/53/8899`
- [ ] 删除服务文件:`/etc/systemd/system/minimax-proxy.service`
- [ ] 更新 memory `server-2.md` 删除此条目

## 备注

- 此组件登记是为了**追溯历史**,不是继续维护
- 决策记录见 memory `server-2.md` 的"角色变更记录"
- 一旦下线,status 转 `archived`,composed_of 清空