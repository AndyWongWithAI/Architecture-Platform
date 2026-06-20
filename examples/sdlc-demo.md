# SDLC 端到端演练 — user-auth-jwt 全流程

> 演示:一个 L2 业务组件从设计到部署到反馈闭环,经过架构平台的 4 个 SDLC 节点。
> 时间:2026-06-20 · 工具:arch-platform-cli + Web UI + GitHub Action(模拟)

## 场景背景

需要做一个新的 L2 业务能力组件:`user-auth-jwt`,跨项目复用的 JWT 认证库。

---

## Phase 1: 需求分析(本阶段不用架构平台)

- 用户需求:Web 项目统一用 JWT 认证,避免每个项目重复造轮子
- 验收标准:`pip install` 即用,支持 FastAPI / Flask

---

## Phase 2: 设计定稿 → 架构平台登记(✓)

```bash
# 1. 创建组件
arch component create \
  --name user-auth-jwt \
  --title "JWT 用户认证库" \
  --positioning "L2 业务能力层的无状态用户认证库,基于 JWT + 刷新令牌,适用于 FastAPI / Flask Web 服务..." \
  --category auth \
  --layer L2_capability \
  --scope lib \
  --form package \
  --tags "jwt,auth,refresh-token,fastapi,oauth"

# 2. 创建第一个版本(设计定稿)
arch version create user-auth-jwt \
  --version 1.0.0 \
  --intent major \
  --changelog "初次发布,JWT + 刷新令牌认证库" \
  --breaking-changes "无(初次发布,建立基线)" \
  --compatibility-window "LTS until 2027-06"
```

**架构平台记录**:Component `user-auth-jwt` + Version `1.0.0`(L2_capability / package)。

---

## Phase 3-5: 编码 / CI / 测试

实现代码 + 跑测试(本演练不展开)。

---

## Phase 6: 部署上线 → 架构平台登记(✓)

```bash
# GitHub Actions 自动跑(模拟):
arch deployment create <version_id> \
  --env prod \
  --host huawei-1 \
  --path /opt/services/user-auth-jwt \
  --config-hash sha256:abc... \
  --lockfile-hash sha256:def... \
  --reproducible \
  --deployed-by "github-actions(myorg/user-auth-jwt@v1.0.0)"
```

或 dev 环境:
```bash
arch deployment create <version_id> \
  --env dev \
  --host huawei-1 \
  --path /opt/dev/user-auth-jwt \
  --deployed-by "manual-cli-test"
```

**架构平台记录**:2 条 Deployment(1 prod + 1 dev on huawei-1)。

---

## Phase 7: 运维监控

Prometheus + Grafana 监控(见 prometheus / grafana 组件)。

---

## Phase 8: Bug 反馈 → 决策闭环(✓)

### Step 1:生产环境反馈

```bash
arch feedback create <version_id> \
  --summary "JWT 刷新令牌在并发场景下偶发 500" \
  --root-cause "竞态条件:旧 token 撤销 + 新 token 颁发未加锁" \
  --fix-plan "用 Redis 分布式锁替代内存 lock" \
  --severity high \
  --reporter "production-oncall" \
  --reused-in "user-management,internal-admin,intelab-website"
```

反馈状态:`open`(等待决策)。

### Step 2:Web UI 看板决策(不需 CLI / 无需 API Key)

打开 https://arch.intelab.cn/feedbacks,在 Open 列看到这张卡片:
- 选 `status=triaged`(已分诊)
- 选 `decision=optimize`(优化现有组件,不新建)
- 填 `root_cause`(补充细节)
- 点保存 → 卡片移到 Triaged 列

### Step 3:修复 + 转 Fixed

修复发布新版本 1.0.1,然后:
```bash
# 或通过 Web UI 看板
arch feedback update <feedback_id> --status fixed
```

反馈状态:`fixed` + `decision=optimize`(闭环完成)。

---

## SDLC 节点 × 工具映射

| 节点 | 工具 | 触发方式 |
|------|------|---------|
| Phase 2 设计定稿 | `arch component create` + `arch version create` | 手动(架构师) |
| Phase 6 部署 | `arch-platform-register` GitHub Action | 自动(CI/CD) |
| Phase 8 Bug 反馈 | `arch feedback create` | 手动(任何人) |
| Phase 8 决策闭环 | Web UI 看板 PATCH | 手动(架构师评审) |
| 任意阶段查询 | `arch search/use/tree/outdated` | 手动(开发者) |

---

## 验证清单(本次演练)

- [x] user-auth-jwt 组件已登记(L2_capability / package / 真资产)
- [x] Version 1.0.0 已创建(major + breaking_changes 填了)
- [x] 部署已登记(prod + dev on huawei-1)
- [x] 反馈已登记(high severity)
- [x] 决策闭环完成(decision=optimize + status=fixed)
- [x] Web UI 看板 4 列展示正确

完整后端验证:
```bash
arch component get user-auth-jwt
arch deployment list
arch feedback list
```

或浏览器:https://arch.intelab.cn/components/user-auth-jwt