# Architecture Platform GitHub Actions

> 三个 composite action,基于 [arch-platform-cli](../../cli/),用于在 SDLC 各节点自动登记架构平台。

## Action 清单

| Action | SDLC 节点 | 用途 |
|--------|----------|------|
| `arch-platform-register` | **Phase 6 部署** | 登记 Deployment(部署位置 + 主机 + 配置 hash) |
| `arch-platform-create-version` | **Phase 2 设计** | 登记新版本(发版意图 + breaking_changes) |
| `arch-platform-feedback` | **Phase 8 反馈** | 登记 Bug 反馈(严重度 + 根因 + 影响面) |

## 引用方式

```yaml
- uses: AndyWongWithAI/Architecture-Platform/.github/actions/arch-platform-register@v1
```

⚠️ **首次使用前需要先打 tag**(见下方"发布"章节)。

## arch-platform-register

部署时自动登记。**最常用**。

```yaml
- name: Register deployment
  uses: AndyWongWithAI/Architecture-Platform/.github/actions/arch-platform-register@v1
  with:
    # 必填
    arch-platform-url: ${{ secrets.ARCH_PLATFORM_URL }}
    component: my-service              # 组件必须先在架构平台登记
    host: huawei-1
    env: prod
    # 选填
    api-key: ${{ secrets.ARCH_PLATFORM_API_KEY }}
    deploy-path: /opt/services/my-service
    config-hash: sha256:abc...
    lockfile-hash: sha256:def...
    build-reproducible: 'true'
    fail-on-missing: 'true'            # 组件不存在是否失败
```

### 内部流程

1. setup-python 3.12
2. `pip install arch-platform-cli`(若 `install-cli: 'true'`)
3. `arch config set-url` + `arch config set-key`
4. `arch health`(健康检查)
5. `arch component get <name> --format json` → 取 `current_version_id`
6. `arch deployment create <version_id> --env ... --host ...`

## arch-platform-create-version

Phase 2 设计定稿时登记新版本。

```yaml
- name: Register new version
  uses: AndyWongWithAI/Architecture-Platform/.github/actions/arch-platform-create-version@v1
  with:
    arch-platform-url: ${{ secrets.ARCH_PLATFORM_URL }}
    component: my-service
    version: 1.2.0
    semver-intent: major              # major / minor / patch
    changelog: '重构 API 路径'
    breaking-changes: '/v1/auth → /v2/auth'  # major 必填
    compatibility-window: 'LTS until 2027-06'
```

### 校验规则

- `semver-intent: major` 必须填 `breaking-changes`,否则 action 失败
- 重复 version → 409 冲突(后端校验)

## arch-platform-feedback

Phase 8 Bug 反馈。

```yaml
- name: Register feedback
  uses: AndyWongWithAI/Architecture-Platform/.github/actions/arch-platform-feedback@v1
  with:
    arch-platform-url: ${{ secrets.ARCH_PLATFORM_URL }}
    component: my-service             # 或 version-id: <uuid>
    summary: '高并发下连接池超时'
    severity: high
    root-cause: 'max_connections 默认 50 太小'
    fix-plan: '调大到 200 + retry'
    reused-in: 'user-mgmt,internal-admin'
```

## Secrets 配置

在 GitHub 仓库 → Settings → Secrets → Actions 添加:

| Secret | 内容 |
|--------|------|
| `ARCH_PLATFORM_URL` | 架构平台 URL,如 `https://arch.intelab.cn` |
| `ARCH_PLATFORM_API_KEY` | API Key(留空 = 开放模式,生产建议设置) |

## 发布(打 tag)

Action 通过 **Git tag** 标识版本。首次发布:

```bash
git tag v1.0.0
git push origin v1.0.0
```

之后可以引用 `@v1`(跟随最新 v1.x.x)或 `@v1.0.0`(精确锁版)。

**SemVer 升级规则**:
- patch:`v1.0.0` → `v1.0.1`(向后兼容的 bug 修复)
- minor:`v1.0.0` → `v1.1.0`(新增功能,向后兼容)
- major:`v1.0.0` → `v2.0.0`(破坏性变更,如新增必填 input)

## 本地测试

`action.yml` 是 declarative 配置,真实测试需要 GitHub Actions runner。可以用 [act](https://github.com/nektos/act) 在本地模拟:

```bash
# 安装 act
curl -fsSL https://raw.githubusercontent.com/nektos/act/master/install.sh | sudo bash

# 模拟 example workflow
act -j deploy --secret ARCH_PLATFORM_URL=https://arch.intelab.cn
```

或者直接跑 CLI(因为 action 内部就是调 CLI):

```bash
pip install arch-platform-cli
arch config set-url https://arch.intelab.cn
arch deployment create <version_id> --env prod --host huawei-1
```

## 设计原则

| 原则 | 体现 |
|------|------|
| **薄封装** | Action 不写新逻辑,只是封装 CLI,业务逻辑都在后端 |
| **幂等** | 重复运行:create-version 409(预期),register 重复 OK |
| **fail-fast** | 关键校验(major 必填 breaking_changes)在 action 内就失败,不污染架构平台 |
| **可观测** | 每个步骤 echo,失败时 `::error::` 在 GitHub UI 高亮 |
| **可复用** | 一个 action 服务一个 SDLC 节点,不混合 |

## 关联

- 主项目:[Architecture-Platform](../../)
- CLI:[arch-platform-cli](../../cli/)
- 设计:[DESIGN.md](../../docs/DESIGN.md) §8 SDLC 集成点