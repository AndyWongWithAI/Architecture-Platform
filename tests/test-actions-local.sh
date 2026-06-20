#!/bin/bash
# test-actions-local.sh — 在 WSL 模拟 GitHub Actions 跑 action 内部命令
# 验证:每个 action 的逻辑都能在 WSL 复现(action.yml 内部 shell 命令)
#
# 用法:bash tests/test-actions-local.sh

set -e

export PATH=/home/hq/.local/bin:$PATH
URL="${URL:-https://arch.intelab.cn}"
COMP="docker"           # 已有种子组件
HOST="huawei-1-test"
ENV="prod"

echo "============================================"
echo "  Phase 3 本地模拟 GitHub Actions 验证"
echo "  URL: $URL"
echo "============================================"

# Step 1:模拟 setup-python(本地 Python 已有,跳过)
echo ""
echo "[Setup] Python: $(python3 --version)"

# Step 2:模拟 pip install arch-platform-cli(已装,跳过)
echo "[Install] arch-platform-cli: $(arch --version)"

# ——— 验证 arch-platform-register action ———

echo ""
echo "============================================"
echo "[Action 1/3] arch-platform-register 验证"
echo "============================================"

# 先创建一个测试组件 + 版本(因为 docker 没 version)
TEST_COMP="cli-action-deploy-test"
echo ""
echo "[Setup] 准备测试组件 $TEST_COMP(部署登记需要 version)"

# 清理可能残留
ssh root@124.71.219.208 "sqlite3 /opt/services/arch-platform/data/arch.db \"DELETE FROM components WHERE name='$TEST_COMP';\"" 2>/dev/null || true

arch component create \
    --name "$TEST_COMP" \
    --title "CLI Action Deploy Test" \
    --positioning "WSL 模拟 GitHub Actions register action 用的临时组件,测试后清理" \
    --category "util" \
    --layer "L2_capability" \
    --form "package" 2>&1 | head -1

arch version create "$TEST_COMP" \
    --version "1.0.0" \
    --intent major \
    --changelog "初次发布,register action 验证" \
    --breaking-changes "无(初次发布)" 2>&1 | head -1

# Step 3:configure CLI
echo ""
echo "[Step] Configure CLI"
arch config set-url "$URL"
arch config show

# Step 4:health check
echo ""
echo "[Step] Health check"
arch health

# Step 5:get component + current version
echo ""
echo "[Step] Get $TEST_COMP current version"
COMP_DATA=$(arch component get "$TEST_COMP" --format json)
VERSION_ID=$(echo "$COMP_DATA" | python3 -c "import sys,json; print(json.load(sys.stdin).get('current_version_id',''))")
echo "  version_id=$VERSION_ID"

if [ -z "$VERSION_ID" ]; then
    echo "✗ 没有 current_version_id(组件未登记或没版本)"
    exit 1
fi

# Step 6:register deployment(注意:--reproducible 是 boolean flag,不接值)
echo ""
echo "[Step] Register deployment"
arch deployment create "$VERSION_ID" \
    --env "$ENV" \
    --host "$HOST" \
    --path "/tmp/test-deploy" \
    --config-hash "sha256:test-$(date +%s)" \
    --lockfile-hash "sha256:lock-$(date +%s)" \
    --reproducible \
    --deployed-by "github-actions(WSL-test@local)"

# ——— 验证 arch-platform-create-version action(major 必填 breaking_changes)——

echo ""
echo "============================================"
echo "[Action 2/3] arch-platform-create-version 验证"
echo "============================================"

# ——— 验证 arch-platform-create-version action(major 必填 breaking_changes)——

echo ""
echo "============================================"
echo "[Action 2/3] arch-platform-create-version 验证"
echo "============================================"

# 复用上面创建的 TEST_COMP
TEST_COMP="cli-action-deploy-test"
echo ""
echo "[Setup] 复用 $TEST_COMP"

# 清理可能残留
ssh root@124.71.219.208 "sqlite3 /opt/services/arch-platform/data/arch.db \"DELETE FROM components WHERE name='$TEST_COMP';\"" 2>/dev/null || true

arch component create \
    --name "$TEST_COMP" \
    --title "CLI Action Test" \
    --positioning "WSL 模拟 GitHub Actions 验证用的临时组件,测试后清理" \
    --category "util" \
    --layer "L2_capability" \
    --form "package" 2>&1 | head -2 2>/dev/null || echo "(组件已存在,跳过)"

# major 但不填 breaking_changes → 应该失败
echo ""
echo "[Step] major 不填 breaking_changes → 应失败"
if arch version create "$TEST_COMP" \
    --version "2.0.0" \
    --intent major \
    --changelog "忘记填 breaking_changes" 2>&1; then
    echo "✗ 没失败(预期应失败)"
    exit 1
else
    echo "✓ 正确失败(major 必填 breaking_changes)"
fi

# major 填 breaking_changes → 应成功(创建 2.0.0)
echo ""
echo "[Step] major 填 breaking_changes → 应成功"
arch version create "$TEST_COMP" \
    --version "2.0.0" \
    --intent major \
    --changelog "破坏性变更" \
    --breaking-changes "/v1 → /v2 路径调整" 2>&1 | head -2

# ——— 验证 arch-platform-feedback action ——

echo ""
echo "============================================"
echo "[Action 3/3] arch-platform-feedback 验证"
echo "============================================"

# 拿刚创建的版本
NEW_COMP=$(arch component get "$TEST_COMP" --format json)
NEW_VER_ID=$(echo "$NEW_COMP" | python3 -c "import sys,json; print(json.load(sys.stdin).get('current_version_id',''))")

if [ -z "$NEW_VER_ID" ]; then
    echo "✗ 测试组件没拿到 version_id"
    exit 1
fi

echo ""
echo "[Step] 登记 feedback"
arch feedback create "$NEW_VER_ID" \
    --summary "WSL 模拟 GitHub Actions 验证" \
    --root-cause "无(模拟)" \
    --fix-plan "无" \
    --severity "low" \
    --reporter "github-actions-test" \
    --reused-in "test-project" 2>&1 | head -2

# ——— 清理 ———

echo ""
echo "============================================"
echo "[Cleanup] 清理测试数据"
echo "============================================"

# 清理测试组件 + 反馈 + 部署
ssh root@124.71.219.208 "
sqlite3 /opt/services/arch-platform/data/arch.db \"
DELETE FROM feedbacks WHERE version_id IN (SELECT id FROM versions WHERE component_id IN (SELECT id FROM components WHERE name='$TEST_COMP'));
DELETE FROM deployments WHERE version_id IN (SELECT id FROM versions WHERE component_id IN (SELECT id FROM components WHERE name='$TEST_COMP'));
DELETE FROM versions WHERE component_id IN (SELECT id FROM components WHERE name='$TEST_COMP');
DELETE FROM components WHERE name='$TEST_COMP';
SELECT 'cleaned, count=' || COUNT(*) FROM components;
\"
"

# 清理今天的部署(host=$HOST 的)
ssh root@124.71.219.208 "
sqlite3 /opt/services/arch-platform/data/arch.db \"
DELETE FROM deployments WHERE host='$HOST';
SELECT 'deployments with host=$HOST cleaned';
\"
"

echo ""
echo "============================================"
echo "  ✅ Phase 3 本地模拟全部通过"
echo "============================================"