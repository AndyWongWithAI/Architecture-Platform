# 资产判定准则

> CLAUDE.md 资产原则的落地文档 —— 回答一个问题:**"这个组件到底算不算可复用资产?"**

## CLAUDE.md 原文

> 我们所开发的任何产品、平台、功能，都应该尽可能以可复用资产的形式生成，并将他们妥善记录和保存。
> 每一次部署到生产上，都需要把建立的资产登记到架构平台。
> **资产应是对状态不敏感的，可迁移的，可复用的，只能用于某个特定项目的代码，不能算作资产。**

## 三条正向特征

满足以下**全部三条**才能登记为 `is_asset=true`:

| 特征 | 含义 | 反例(说明不算资产) |
|------|------|--------------------|
| **状态不敏感** | 不依赖特定运行时状态(数据库连接、特定账号、特定文件路径) | 硬编码 `/home/andy/.ssh/id_rsa` 的脚本、绑死某个 GitHub 账号的 OAuth token |
| **可迁移** | 换项目换环境,代码不改就能跑;配置与代码分离 | 写死 `intelab.cn` 域名 + `/var/www/intelab.cn/` 路径的部署脚本、配置文件内联在代码里 |
| **可复用** | 跨项目能直接拿来用;接口稳定 | 只能给"用户中心"项目用的"用户中心专属优惠计算器" |

## 判定流程

登记每个 Component 时,按顺序问自己:

```
1. 这个组件跨项目能直接用吗?
   ├─ 否 → is_asset=false(项目级代码,登记仅为追溯)
   └─ 是 ↓

2. 把配置抽离后,代码本身能不能在另一个环境直接跑?
   ├─ 否 → is_asset=false(状态敏感,绑死当前环境)
   └─ 是 ↓

3. 这个组件的定位稳定吗?半年后还会有人想复用它吗?
   ├─ 否 → is_asset=false(一次性脚本/临时工具)
   └─ 是 ↓

   is_asset=true
   + 必填 distribution_form
   + 必填 install_command
```

## distribution_form 选型指南(11 个 enum)

`is_asset=true` 时必填,选最贴近实际复用形态的一个:

| 值 | 含义 | 例子 |
|----|------|------|
| `package` | 系统包或语言包(apt / pip / npm / cargo) | docker / nginx / user-auth-jwt 库 |
| `container` | Docker / OCI 镜像 | ghcr.io/andywong/user-mgmt:1.0.0 |
| `binary` | 可执行二进制(Release 下载 / go install 产物) | kubectl / terraform / gh CLI |
| `source` | 源码(git clone + build) | 完整可 build 的源码仓库 |
| `http_api` | HTTP API 服务 | intelab.cn-website 这类服务的 API(必须填 interface_contract 指向 OpenAPI Spec) |
| `schema` | 数据结构定义(DDL / proto / Prisma / Avro) | PostgreSQL DDL、protobuf 文件 |
| `dataset` | 数据集 / 训练样本 | CSV/Parquet、标注样本 |
| `config_template` | 配置模板 | nginx.conf / systemd unit / WireGuard peer 配置 |
| `iac` | 基础设施即代码 | Terraform module / Pulumi / Ansible playbook |
| `skill` | Claude Code skill + agent + slash command | `/init` `/review` 这类 skill |
| `tool` | MCP tool(可被 AI 调用的工具) | 我们项目里的 Bash / Read / WebFetch |

## knowledge_artifact: 另一个维度

`distribution_form` 描述的是"资产怎么被消费",`knowledge_artifact` 标记的是**"是不是 AI 上下文资产"**。两者正交:

| knowledge_artifact | 含义 | 典型 distribution_form |
|--------------------|------|------------------------|
| `true` | AI 上下文资产(skill / tool / memory / agent 文档 / prompt template) | `skill` / `tool` |
| `false` | 传统代码资产(默认) | `package` / `container` / `binary` / `source` / `http_api` / `schema` / `dataset` / `config_template` / `iac` |

**为什么单独成一个字段**:`distribution_form` 已经被"消费形态"维度占用(11 个 enum 已足够);"是不是 AI 上下文资产"是另一个正交维度,不应该塞进同一个 enum。Phase 1 实现时,Web UI 可以基于这个字段做视觉区分(比如 AI 资产用不同图标)。

## 各层的资产判定倾向

| 层 | `is_asset=true` 比例 | 理由 |
|----|---------------------|------|
| L0 Infrastructure | 几乎全部 | Docker / Linux / K8s 等基座天生就是资产 |
| L1 Platform | 几乎全部 | 数据库 / 缓存 / Web 服务器等中间件天生就是资产 |
| L2 Capability | **混合** | lib 型通常是资产;service 型需要看是不是只服务特定项目 |
| L3 Application | 多数 `is_asset=false` | L3 多为项目级代码,登记目的主要是**项目组成追溯**,不是复用 |

## L3 的特殊性:登记目的 = 追溯,不是复用

L3 项目级代码登记进架构平台,**目的不是将来被复用**,而是:
- 出问题时知道"这个项目由哪些组件拼成"
- 依赖关系可追溯(哪个 L3 用了哪个 L2)
- 重新部署时能照原样复现

所以 L3 组件即使 `is_asset=false`,也要正常登记(只是不复用、不进搜索默认结果)。

## interface_contract 必填规则

| distribution_form | interface_contract |
|-------------------|---------------------|
| `http_api` | **必填**(URL 指向 OpenAPI Spec,例如 `https://api.example.com/v1/openapi.yaml`) |
| `package` / `container` / `source` | 选填(文本描述签名 / 协议,或不填) |

## 反例参考(刻意标记为非资产的组件)

| 组件 | `is_asset=false` 原因 |
|------|----------------------|
| `minimax-proxy` | 绑死 MiniMax 这一个第三方服务,跨项目价值 = 0 |
| `intelab.cn-website` | 个人主页专属,绑死特定域名 + 内容,跨项目价值 = 0 |

这两个组件的登记目的是**追溯历史**(知道曾经存在过、可以重新部署),不是供他人复用。

## 资产形态变更的反馈

CLAUDE.md 反馈原则(2026-06-20 修订):
> 直接复用组件遇到 bug、**组件的资产形态与实际不符**、组件定位发生变化,或组件出现性能、安全、废弃等问题时,应将情况反馈到架构平台,由架构平台考虑存量引用关系后进行决策。决策的内容包括:**优化组件、新建组件、保持不变、重新审视资产形态等**。

发现以下情况,创建 Feedback 并选 `decision=reassess_form`:
- 设计时定的 `distribution_form` 跟实际不符(例:登记为 `package`,实际是 git clone 源码)
- `is_asset=true` 但实际只有 1 个项目在用 → 应改 `false`
- `is_asset=false` 但发现可推广到 2+ 项目 → 应改 `true` 并补 `distribution_form`
- `interface_contract` 失效(API Spec URL 404 / API 改了未升 Version)

## 判定决策的"反思时机"

不是登记时判完就完了。**每次新项目用这个组件时,都是重新评估资产判定的机会**:
- 用了一次 → 仍可能是资产,也可能发现只对当前项目好用
- 用了 3+ 个不同项目 → 几乎可以确认是资产
- 用了 1 个项目但需要 fork 改 → 不算资产(本项目专有)

## 一句话总结

> **能拆出来给别人的 = 资产;只能服务这一个项目的 = 不是资产,只是登记项。**