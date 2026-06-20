# AI-Assets 集成

> 架构平台 + AI-Assets 仓库的双层结构说明

## 为什么需要第二个仓库

CLAUDE.md 资产原则要求"每一个产品/平台/功能都应该尽可能以可复用资产的形式生成"。但**AI 上下文资产**(skill / agent / prompt template / memory / CLAUDE.md 本身)跟传统代码资产有本质区别:

| 维度 | 传统代码资产 | AI 上下文资产 |
|------|------------|--------------|
| **载体** | GitHub repo / 包仓库 / 容器镜像 | `~/.claude/` 系统目录 + 个人笔记 |
| **分发形态** | package / container / binary / source | skill / tool / prompt_template / memory |
| **消费方式** | `pip install` / `docker pull` / `git clone` | Claude Code 加载到上下文 |
| **备份机制** | GitHub push(天然) | **需要单独设计**(本地无异地备份) |
| **登记目的** | 跨项目复用 + 版本追溯 | 跨会话复用 + 跨机器同步 + 灾难恢复 |

架构平台(Component 元数据登记)只解决"是什么",不解决"怎么异地备份 AI 资产本身"。

## 双层结构

```
┌─────────────────────────────────────────────┐
│ Architecture-Platform(公开仓库)             │
│  - 登记 Component 元数据                    │
│  - knowledge_artifact=true 时:              │
│      Component.repo_url 指向 ↓              │
└─────────────────────────────────────────────┘
                  ↓ repo_url
┌─────────────────────────────────────────────┐
│ AI-Assets(私密仓库)                         │
│  - 实际载体:skill .md / agent .md / prompt  │
│  - CLAUDE.md(全局宪法主版本)                │
│  - memory/(8 个 memory 文件)                │
│  - dotfiles 风格半自动 sync                 │
└─────────────────────────────────────────────┘
```

## 例子:登记一个 skill

### 在 AI-Assets 仓库

```
AI-Assets/mirror/skills/pushgithub/SKILL.md
```

### 在架构平台(Component 元数据)

```yaml
name: skill-push-github
title: 一键 push 到 GitHub 的 skill
layer: L2_capability
category: util
scope: tool
atomic: true
positioning: |
  封装 git add + commit + push 到 GitHub 的标准流程,
  接受 commit message,可指定 target branch
language: other
package_name: ""
install_command: "git clone git@github.com:AndyWongWithAI/AI-Assets.git ~/projects/AI-Assets && cp -r ~/projects/AI-Assets/mirror/skills/pushgithub ~/.claude/skills/"
usage_example: "/pushgithub fix: 修复 xxx"
status: stable
repo_url: "https://github.com/AndyWongWithAI/AI-Assets/blob/main/mirror/skills/pushgithub/SKILL.md"
is_asset: true
distribution_form: skill
interface_contract: ""
knowledge_artifact: true
```

### 跨平台使用流程

1. 别人 `arch use skill-push-github`
2. CLI 从 Architecture-Platform 拿到 `repo_url`
3. CLI 去 AI-Assets 仓库拉 `mirror/skills/pushgithub/` 到 `~/.claude/skills/pushgithub/`
4. 重启 Claude Code 即可用 `/pushgithub`

## 数据模型对应

架构平台 Component 字段 vs AI-Assets 仓库路径:

| Component 字段 | AI-Assets 对应 |
|-----------------|----------------|
| `name` | 仓库里的目录名 |
| `repo_url` | `https://github.com/AndyWongWithAI/AI-Assets/blob/main/mirror/...` |
| `distribution_form` | skill / tool / agent / prompt_template |
| `knowledge_artifact` | 始终 `true` |
| `positioning` | 在仓库 SKILL.md 里有完整描述 |

## 哪些东西应该走 AI-Assets

| 内容 | 在 AI-Assets? | 理由 |
|------|---------------|------|
| CLAUDE.md | ✅ | 全局宪法,异地备份关键 |
| memory 文件 | ✅ | 8 个 memory 含架构/服务器/SDLC 关键事实 |
| skill 定义 | ✅ | Claude Code 加载,跨会话复用 |
| agent 定义 | ✅ | 同上 |
| hook 配置 | ✅ | 关键行为定义 |
| prompt template | ✅ | 可复用 LLM 调用模板 |
| secrets.json | ❌ 永远不 | 密钥 |
| history.jsonl / sessions/ | ❌ | 临时会话数据,无价值 |
| plans/ / tasks/ | ❌ | 临时任务,价值在 memory 里沉淀 |

## 同步机制

- **手动**: `cd ~/projects/AI-Assets && ./sync.sh --push`
- **自动(cron 兜底)**: 每天 23:00,日志写 `sync.log`
- **私密仓库**,IP/账号直接写不脱敏

## Phase 5 数据导入

Phase 5 数据导入时,架构平台会从 AI-Assets 仓库批量登记公开 AI 资产(skill / agent / prompt):

```
1. 读取 AI-Assets/mirror/skills/ 下所有 SKILL.md
2. 为每个生成一个 Component 记录
3. Component.repo_url 指向对应路径
4. knowledge_artifact=true
5. is_asset=true + distribution_form=skill
6. positioning 从 SKILL.md 的描述提取
```

这样架构平台就成为"AI 资产中心",别人搜 `arch search ai-skill` 能直接找到。

## 关联

- AI-Assets 仓库: https://github.com/AndyWongWithAI/AI-Assets(私密)
- 同步脚本: `~/projects/AI-Assets/sync.sh`
- 数据字典: `docs/data-dictionary.md` Component 实体
- 资产判定: `docs/asset-criteria.md`