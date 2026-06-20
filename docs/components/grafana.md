---
name: grafana
title: Grafana 可视化仪表盘
positioning: "L1 平台层的可视化仪表盘工具,基于 Prometheus + Loki + 其他数据源构建运维仪表盘。三台服务器的监控 / 日志 / 告警统一可视化入口。"
layer: L1_platform
category: monitor
scope: infra
atomic: true
composed_of: []
tags: [visualization, dashboard, observability, prometheus, loki]
language: go
package_name: ""
install_command: "docker run -d -p 3000:3000 grafana/grafana"
usage_example: "open http://localhost:3000"
status: stable
repo_url: https://github.com/grafana/grafana
is_asset: true
distribution_form: binary
interface_contract: ""
knowledge_artifact: false
---

## 定位

L1 监控可视化层。接 Prometheus 做指标仪表盘,接 Loki 做日志搜索。

## 部署位置

- **#3 阿里云**:Grafana 3000 端口,跟 Prometheus 同机
- 数据源:Prometheus(http://localhost:9090)+ Loki(http://localhost:3100)

## 关键仪表盘

- 三台服务器资源总览(CPU / 内存 / 磁盘 / 网络)
- 架构平台健康(健康检查 + DB 写入速率 + 备份状态)
- 告警趋势(Alertmanager webhook)

## 备注

- 2026-06-20 部署在 #3
- 默认 admin/admin,首次登录强制改密码