# arch-platform-cli

> Architecture Platform CLI — 架构平台命令行工具(组件登记 / 版本 / 反馈 / 部署)

架构平台后端 + CLI 完整方案见 [主仓库 README](../README.md)。本目录是 CLI 子项目。

## 安装

### 方式 A:本地安装(开发模式)

```bash
cd cli/
pip install --break-system-packages -e .
arch --version
```

### 方式 B:从 GitHub Packages 安装(发布后)

```bash
# 配置 pip index-url(参考架构平台 DESIGN.md §12.3)
pip install arch-platform-cli
```

## 快速开始

```bash
# 1. 配置服务端地址 + API Key(只需一次)
arch config set-url https://arch.intelab.cn
arch config set-key sk-xxx...   # 或 '-' 清空(开放模式)
arch config show

# 2. 健康检查
arch health

# 3. 搜索组件
arch search redis

# 4. 查看组件安装指引
arch use docker

# 5. 展开依赖树
arch tree intelab.cn-website

# 6. 列出所有组件(支持过滤)
arch component list --layer L1_platform --asset

# 7. 登记新组件
arch component create \
  --name my-service \
  --title "我的服务" \
  --positioning "L2 业务层的 xxx 服务,负责..." \
  --category auth \
  --layer L2_capability \
  --form package \
  --tags "auth,jwt,oauth" \
  --install-command "pip install my-service" \
  --usage-example "from my_service import Client"

# 8. 登记新版本
arch version create my-service \
  --version 1.0.0 \
  --intent major \
  --changelog "初次发布" \
  --breaking-changes "无"

# 9. 登记反馈
ver_id=$(arch component get my-service --format json | python3 -c "import sys,json; print(json.load(sys.stdin)['current_version_id'])")
arch feedback create "$ver_id" \
  --summary "Bug 描述" \
  --root-cause "根因" \
  --fix-plan "修复方案" \
  --severity high

# 10. 状态输出(JSON 模式,便于脚本处理)
arch component list --format json | jq '.[].name'
```

## 命令清单

| 命令 | 说明 |
|------|------|
| `arch health` | 健康检查 |
| `arch config {show,set-url,set-key,set-format,path}` | CLI 配置管理 |
| `arch component {list,get,create,update}` | Component CRUD |
| `arch version {list,get,create}` | 版本管理 |
| `arch feedback {list,create,update}` | 反馈闭环 |
| `arch deployment {create,list}` | 部署登记 |
| `arch search <query>` | 跨实体搜索 |
| `arch use <name>` | 安装指引 |
| `arch tree <name>` | 依赖树 |
| `arch outdated` | 检查可升级版本 |
| `arch lock` | 生成 lockfile |
| `arch detect [path]` | 读 aip.json 自动预填 |

所有命令支持 `--format json` / `--format table`(默认)。

## 配置文件位置

`~/.config/arch-cli/config.toml`(权限 0600):

```toml
[server]
url = "https://arch.intelab.cn"
api_key = "sk-xxx..."

[output]
format = "table"
color = "true"
```

环境变量可覆盖:`ARCH_PLATFORM_URL` / `ARCH_PLATFORM_API_KEY`

## 测试

```bash
cd cli/
python3 -m pytest tests/ -v
```

测试用例覆盖:`help` / `version` / `health` / list / get / create / search / use / tree / config / outdated / lock / 404 / filter / JSON 输出。

## 发布到 GitHub Packages

GitHub Actions workflow:`/cli/.github/workflows/publish.yml`(待 Phase 2.7)

发布后:

```bash
# 在 GitHub PAT 设置好后,其他用户安装:
pip install --index-url https://pypi.pkg.github.com/AndyWongWithAI/simple/ arch-platform-cli
```

## 设计原则

| 原则 | 体现 |
|------|------|
| **配置独立** | 配置文件 + 环境变量 + CLI 参数 三层覆盖 |
| **API Key 安全** | 配置文件权限 0600,`config show` 自动脱敏 |
| **错误友好** | HTTP 状态码 → 中文友好提示(Pydantic 错误也解析) |
| **输出灵活** | `--format table/json`;JSON 模式适合脚本处理 |
| **不破坏 API** | CLI 是 API 的薄封装,API 升级时 CLI 跟随 |

## 关联

- [主项目 README](../README.md)
- [DESIGN.md](../docs/DESIGN.md) Phase 12 / 13
- [architecture-platform.md](https://github.com/AndyWongWithAI/AI-Assets/blob/main/mirror/projects/-home-hq/memory/architecture-platform.md)(memory)