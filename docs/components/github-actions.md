---
name: github-actions
title: GitHub Actions CI/CD 平台
positioning: "L1 平台层的 CI/CD 平台,通过 workflow 文件定义自动化流程。所有服务的 build / test / deploy / 架构平台登记都在 GitHub Actions 完成。"
layer: L1_platform
category: deploy
scope: infra
atomic: true
composed_of: []
tags: [ci-cd, automation, github, workflow]
language: ""
package_name: ""
install_command: ""
usage_example: ".github/workflows/deploy.yml"
status: stable
repo_url: https://github.com/features/actions
is_asset: true
distribution_form: iac
interface_contract: ""
knowledge_artifact: false
---

## 定位

L1 CI/CD 平台。**架构平台的写操作主路径**:
- Phase 2 设计定稿:`arch-platform-create-version` action
- Phase 6 部署:`arch-platform-register` action
- Phase 8 Bug 反馈:`arch-platform-feedback` action

## 关键 Workflow

所有 `AndyWongWithAI/*` 仓库都引用架构平台的 composite action:

```yaml
- uses: AndyWongWithAI/Architecture-Platform/.github/actions/arch-platform-register@v1
  with:
    arch-platform-url: ${{ secrets.ARCH_PLATFORM_URL }}
    api-key: ${{ secrets.ARCH_PLATFORM_API_KEY }}
    component: my-service
    host: huawei-1
    env: prod
```

## 备注

- 未来可加自托管 runner(#3 阿里云),目前用 GitHub 托管
- Phase 3 已发布 v1.0.0 tag,引用方式稳定