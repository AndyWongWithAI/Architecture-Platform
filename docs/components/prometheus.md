---
name: prometheus
title: Prometheus 监控系统
positioning: "L1 平台层的开源时序数据库 + 监控系统,提供多维度指标采集、PromQL 查询、告警规则。为 L0 基础设施(节点 / 容器)和 L2 业务能力(服务)的可观测性提供统一数据源。"
layer: L1_platform
category: monitor
scope: infra
atomic: true
composed_of: []
tags: [metrics, monitoring, timeseries, alerting, observability]
language: go
package_name: ""
install_command: "docker run -d -p 9090:9090 -v /etc/prometheus:/etc/prometheus prom/prometheus --config.file=/etc/prometheus/prometheus.yml"
usage_example: "curl http://localhost:9090/api/v1/query?query=up"
status: stable
repo_url: https://github.com/prometheus/prometheus
is_asset: true
distribution_form: binary
interface_contract: ""
knowledge_artifact: false
---

## 定位

L1 平台层的监控系统核心。所有 #1 / #2 / #3 部署 node_exporter,Prometheus 抓取指标并通过 Alertmanager 触发告警。

## 部署位置

- **#3 阿里云**:Prometheus server + Grafana(主控 + 可视化)
- **#1/#2**:node_exporter(9091 端口,被 Prometheus 抓取)

## 关键配置

```yaml
# /etc/prometheus/prometheus.yml
global:
  scrape_interval: 15s
scrape_configs:
  - job_name: 'node'
    static_configs:
      - targets: ['124.71.219.208:9100', '81.71.132.24:9100', '8.163.80.32:9100']
```

## 备注

- 2026-06-20 部署在 #3,作为监控基础设施
- 告警阈值:CPU > 80% / 内存 > 90% / 磁盘 > 85%(参考 sdlc.md Phase 7)