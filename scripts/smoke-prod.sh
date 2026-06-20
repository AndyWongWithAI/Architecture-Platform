#!/bin/bash
# smoke-prod.sh — #1 生产环境端到端冒烟测试
# 验证:健康检查 + 9 个种子数据 + POST/PATCH/Version/Feedback 全栈
#
# 用法:bash scripts/smoke-prod.sh

set -e
HOST="${1:-127.0.0.1:8088}"
PASS=0
FAIL=0

red() { printf "\033[31m%s\033[0m\n" "$*"; }
green() { printf "\033[32m%s\033[0m\n" "$*"; }
check() {
    local desc="$1" expected="$2" actual="$3"
    if [ "$expected" = "$actual" ]; then
        green "  ✓ $desc"
        PASS=$((PASS+1))
    else
        red "  ✗ $desc (expected=$expected, got=$actual)"
        FAIL=$((FAIL+1))
    fi
}

BASE="http://$HOST"

echo "============================================"
echo "  架构平台 #1 生产环境冒烟测试"
echo "  Target: $BASE"
echo "============================================"

# 1. 健康检查
echo ""
echo "[1] 健康检查"
HEALTH=$(curl -s "$BASE/healthz")
echo "    $HEALTH"
DB_OK=$(echo "$HEALTH" | python3 -c "import sys,json; print(json.load(sys.stdin).get('db_check', False))")
check "db_check=true" "True" "$DB_OK"

# 2. 种子数据(应=9,7 真资产 + 2 项目级)
echo ""
echo "[2] 种子数据列表"
TOTAL=$(curl -s "$BASE/api/v1/components" | python3 -c "import sys,json; print(json.load(sys.stdin)['total'])")
check "components.total=9" "9" "$TOTAL"

ASSETS=$(curl -s "$BASE/api/v1/components?is_asset=true" | python3 -c "import sys,json; print(json.load(sys.stdin)['total'])")
check "is_asset=true count=7" "7" "$ASSETS"

PROJECTS=$(curl -s "$BASE/api/v1/components?is_asset=false" | python3 -c "import sys,json; print(json.load(sys.stdin)['total'])")
check "is_asset=false count=2" "2" "$PROJECTS"

# 3. 按层统计
echo ""
echo "[3] 分层统计"
L0=$(curl -s "$BASE/api/v1/components?layer=L0_infrastructure" | python3 -c "import sys,json; print(json.load(sys.stdin)['total'])")
check "L0 count=2" "2" "$L0"

L1=$(curl -s "$BASE/api/v1/components?layer=L1_platform" | python3 -c "import sys,json; print(json.load(sys.stdin)['total'])")
check "L1 count=5" "5" "$L1"

# 4. POST 创建新组件
echo ""
echo "[4] POST 创建组件"
CREATE_HTTP=$(curl -s -o /tmp/arch-post.json -w "%{http_code}" -X POST "$BASE/api/v1/components" \
    -H "Content-Type: application/json" \
    -d '{
        "name":"redis-prod-test",
        "title":"Redis 生产测试",
        "positioning":"架构平台 #1 部署后端到端冒烟测试组件",
        "category":"cache","scope":"infra","layer":"L1_platform",
        "is_asset":true,"distribution_form":"package"
    }')
check "POST /components HTTP=201" "201" "$CREATE_HTTP"
NEW_ID=$(python3 -c "import json; print(json.load(open('/tmp/arch-post.json'))['id'][:8])")
echo "    created id=$NEW_ID"

# 5. POST 创建版本(major + breaking_changes)
echo ""
echo "[5] POST 创建版本"
VER_HTTP=$(curl -s -o /tmp/arch-ver.json -w "%{http_code}" -X POST "$BASE/api/v1/components/redis-prod-test/versions" \
    -H "Content-Type: application/json" \
    -d '{
        "version":"1.0.0",
        "semver_intent":"major",
        "changelog":"初次发布",
        "breaking_changes":"无(初次发布,建立基线)"
    }')
check "POST /versions HTTP=201" "201" "$VER_HTTP"
VER_ID=$(python3 -c "import json; print(json.load(open('/tmp/arch-ver.json'))['id'][:8])")
echo "    version id=$VER_ID"

# 6. major 缺 breaking_changes → 422
echo ""
echo "[6] major 缺 breaking_changes → 422"
HTTP=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE/api/v1/components/redis-prod-test/versions" \
    -H "Content-Type: application/json" \
    -d '{"version":"2.0.0","semver_intent":"major","changelog":"忘记填 breaking_changes"}')
check "major without breaking_changes HTTP=422" "422" "$HTTP"

# 7. POST 部署登记
echo ""
echo "[7] POST 部署登记"
DEP_HTTP=$(curl -s -o /tmp/arch-dep.json -w "%{http_code}" -X POST "$BASE/api/v1/versions/$VER_ID_FULL/deployments" \
    -H "Content-Type: application/json" \
    -d '{
        "env":"prod","host":"huawei-1","deploy_path":"/opt/services/arch-platform-test",
        "deployed_by":"smoke-prod-test","lockfile_hash":"sha256:test",
        "build_reproducible":true
    }' 2>/dev/null || echo "skip")

VER_ID_FULL=$(python3 -c "import json; print(json.load(open('/tmp/arch-ver.json'))['id'])")
DEP_HTTP=$(curl -s -o /tmp/arch-dep.json -w "%{http_code}" -X POST "$BASE/api/v1/versions/$VER_ID_FULL/deployments" \
    -H "Content-Type: application/json" \
    -d '{
        "env":"prod","host":"huawei-1","deploy_path":"/opt/services/arch-platform-test",
        "deployed_by":"smoke-prod-test","lockfile_hash":"sha256:test",
        "build_reproducible":true
    }')
check "POST /deployments HTTP=201" "201" "$DEP_HTTP"

# 8. POST 反馈登记
echo ""
echo "[8] POST 反馈登记"
FB_HTTP=$(curl -s -o /tmp/arch-fb.json -w "%{http_code}" -X POST "$BASE/api/v1/versions/$VER_ID_FULL/feedbacks" \
    -H "Content-Type: application/json" \
    -d '{
        "reporter":"smoke-prod","bug_summary":"冒烟测试反馈样例",
        "root_cause":"无","fix_plan":"关闭","severity":"low",
        "reused_in_projects":["arch-platform"]
    }')
check "POST /feedbacks HTTP=201" "201" "$FB_HTTP"

# 9. Search 跨实体搜索
echo ""
echo "[9] 跨实体搜索"
SEARCH=$(curl -s "$BASE/api/v1/search?q=redis" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['total'])")
[ "$SEARCH" -gt 0 ] && green "  ✓ search 'redis' hits=$SEARCH" && PASS=$((PASS+1)) || { red "  ✗ no hits"; FAIL=$((FAIL+1)); }

# 10. Cleanup — DELETE 测试组件
echo ""
echo "[10] 清理(测试数据)"
CLEAN_HTTP=$(curl -s -o /dev/null -w "%{http_code}" -X DELETE "$BASE/api/v1/components/redis-prod-test" 2>/dev/null || echo "no-delete-endpoint")
echo "    DELETE HTTP=$CLEAN_HTTP(若无 DELETE 端点,留待手工归档)"

# 总结
echo ""
echo "============================================"
TOTAL_TESTS=$((PASS+FAIL))
if [ "$FAIL" -eq 0 ]; then
    green "  ✅ 全部通过 ($PASS/$TOTAL_TESTS)"
else
    red "  ❌ $FAIL 个失败 ($PASS/$TOTAL_TESTS)"
fi
echo "============================================"
exit $FAIL