---
name: docker
title: Docker 容器引擎
layer: L0_infrastructure
category: deploy
scope: infra
atomic: true
composed_of: []
tags:
  - docker
  - container
  - runtime
  - docker-engine
language: go
package_name: ""
install_command: "apt install docker.io"
usage_example: "docker run hello-world"
status: stable
repo_url: ""
is_asset: true
distribution_form: package
interface_contract: ""
knowledge_artifact: false
---

# Docker 容器引擎

## 定位

Docker 是 L0 基础设施层的容器运行时,为 L1 平台层(nginx / 数据库 / 镜像仓库)和 L2 业务层(自研服务)提供一致的部署载体。所有生产服务的进程隔离、镜像分发、运行时配置都依赖 Docker Engine。

## 版本历史

| 版本 | 时间 | 变更 |
|------|------|------|
| 29.6.0 | 2026-06-20 | 三台服务器对齐基线(对齐基线操作) |
| 29.1.3 | 2026-06-20 | WSL2 本地首次安装(本地开发用) |

## 部署位置

| 主机 | 环境 | 路径 | 部署时间 |
|------|------|------|---------|
| #1 华为云 124.71.219.208 | prod | `apt install docker.io` | 2026-06-20 |
| #2 腾讯云 81.71.132.24 | prod | `apt install docker.io` | 2026-06-19 |
| #3 阿里云 8.163.80.32 | prod | `apt install docker.io` | 2026-06-20 |
| WSL2 本地开发机 | dev | `apt install docker.io` | 2026-06-20 |

## 配置

- **镜像源**(daemon.json):
  - `docker.m.daocloud.io`
  - `docker.1ms.run`
  - `docker.ketches.cn`
- **用户组**:`hq` 已加入 `docker` 组(下次登录生效)
- **API 端口**:2375(默认 Unix socket,生产不开 TCP)

## 备注

- 跨服务器版本对齐(都是 29.6.0 + Compose v5.1.4)符合 CLAUDE.md **一致性** 原则
- L2 业务组件未来默认部署形态 = Docker 镜像
- 未来 L1 平台层组件(如 postgresql / redis)也走 Docker 部署,减少主机级安装