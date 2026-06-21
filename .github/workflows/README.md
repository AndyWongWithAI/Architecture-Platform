# Reusable Deploy Workflow

本目录的 `.github/workflows/deploy.yml` 是一个 **reusable workflow**,可以被你的项目通过 5 行配置复用。

## 一次性设置(架构师已配置)

- [x] `AndyWongWithAI/Architecture-Platform` 仓库公开(已公开)
- [x] reusable workflow 已发布到 `v1` tag
- [x] `arch-platform-register` Action 已可用

## 其他项目接入(3 步)

### 1. 在 GitHub repo settings 配置 2-3 个 secrets

| Secret | 值 |
|---|---|
| `SSH_USER_DEPLOY` | `root`(或你的部署用户) |
| `SSH_KEY_DEPLOY` | SSH 私钥全文(含 BEGIN/END 行) |
| `ARCH_API_KEY` | 架构平台 API Key(开放模式留空) |

### 2. 在你的项目里创建 `.github/workflows/deploy.yml`

```yaml
name: Deploy
on:
  push:
    branches: [main]

jobs:
  deploy:
    uses: AndyWongWithAI/Architecture-Platform/.github/workflows/deploy.yml@v1
    with:
      host: "1.2.3.4"                          # 你的服务器 IP
      service_name: "my-service"               # 容器 / systemd 单元名
      deploy_path: "/opt/services/my-service"  # 服务器上的目录
      healthcheck_url: "http://127.0.0.1:8080/healthz"  # 可选
      arch_component: "my-service"             # 可选:登记到架构平台
    secrets:
      ssh_user: ${{ secrets.SSH_USER_DEPLOY }}
      ssh_key: ${{ secrets.SSH_KEY_DEPLOY }}
      arch_api_key: ${{ secrets.ARCH_API_KEY }}
```

### 3. 服务器前置

```bash
# 服务器上:一次性初始化
mkdir -p /opt/services/my-service
cd /opt/services/my-service
git clone https://github.com/your-org/my-service.git .
# docker-compose.yml 应已在仓库根目录
```

## 跨服务器示例

| Server | 配置项 |
|---|---|
| 华为云 #1 (124.71.219.208) | `host: 124.71.219.208` + 配 `SSH_KEY_HUAWEI1` |
| 腾讯云 #2 (81.71.132.24) | `host: 81.71.132.24` + 配 `SSH_KEY_TX` |
| 阿里云 #3 (8.163.80.32) | `host: 8.163.80.32` + 配 `SSH_KEY_ALI` |

每个项目可以指向不同 server,只换 `host` 和 secret 即可。

## 工作原理

```
你的项目 push main
  ↓
触发你的 .github/workflows/deploy.yml
  ↓
calls reusable workflow @v1
  ↓
SSH 到 host → git pull → docker compose up --build -d
  ↓
(可选) 健康检查 + 登记到架构平台
```

## 升级 reusable workflow

修改 `AndyWongWithAI/Architecture-Platform` 仓库的 `.github/workflows/deploy.yml`:

```bash
# 修改 deploy.yml
git tag v2
git push --tags
# 其他项目只需改 uses: ...@v1 → ...@v2 即可
```

## 限制

- 仓库必须公开(免费 plan),否则 reusable workflow 调用方需要付费 plan
- secrets 不能跨仓库复用,每个 repo 都要配自己的 SSH key
- 部署是阻塞的(SYNC),10 分钟超时
