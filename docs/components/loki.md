---
name: loki
title: Loki 日志聚合系统
positioning: "L1 平台层的日志聚合系统,跟 Prometheus 同源生态(Grafana Labs)。从三台服务器抓取日志,通过标签索引,提供高效日志查询。"
layer: L1_platform
category: log
scope: infra
atomic: true
composed_of: []
tags: [logs, aggregation, observability, grafana]
language: go
package_name: ""
install_command: "docker run -d -p 3100:3100 -v /etc/loki:/etc/loki grafana/loki"
usage_example: "open http://localhost:3000/explore"
status: draft
repo_url: https://github.com/grafana/loki
is_asset: true
distribution_form: binary
interface_contract: ""
knowledge_artifact: false
---

## 定位

L1 日志聚合层。跟 Prometheus + Grafana 组成完整 observability 三件套(Promtail 抓 → Loki 存 → Grafana 查)。

## 部署位置(规划)

- **#3 阿里云**:Loki + Promtail,接三台服务器的 docker / systemd / nginx / 架构平台日志

## 关键设计

- 标签索引(只索引标签,不索引全文)→ 存储高效
- LogQL 查询语言(类 PromQL)
- Grafana 数据源统一入口

## 备注

- sdlc.md Phase 7 提到"Loki+Promtail:收集日志到 #3 + 关键词告警"
- 当前 draft,2026 Q3 部署