"""冒烟测试 — 验证 importer + GET endpoints 工作

用临时 DB 跑测试(避免污染 dev DB)。
通过 ARCH_DB_PATH 环境变量在 init_db() 时切换。
"""
import os
import sys
import tempfile

# 必须在 import app 之前设置 env
TEST_DB = tempfile.NamedTemporaryFile(suffix=".db", delete=False, prefix="arch-test-")
TEST_DB.close()
os.environ["ARCH_DB_PATH"] = TEST_DB.name

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi.testclient import TestClient  # noqa: E402

from app.database import init_db, SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.services import MarkdownImporter  # noqa: E402


COMPONENTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "docs",
    "components",
)


def _setup():
    """建临时表 + 导入 9 个种子组件(幂等:重复调用安全)"""
    init_db()
    db = SessionLocal()
    try:
        importer = MarkdownImporter(db, COMPONENTS_DIR)
        result = importer.import_all()
        print(f"\n[setup] Import: {result}")
        assert len(result.errors) == 0, f"errors: {result.errors}"
        # 不再断言 created ≥ 9 — 第二次调用时 created=0(全部 update),但仍是有效 seed
    finally:
        db.close()


def test_health():
    _setup()  # feedback 53fe92a4:确保 DB + 组件已 seed
    client = TestClient(app)
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_list_all():
    client = TestClient(app)
    r = client.get("/api/v1/components")
    assert r.status_code == 200
    data = r.json()
    assert data["total"] >= 9, f"expected ≥9 components (补登后 22 个), got {data['total']}"
    print(f"  → Listed {data['total']} components")


def test_get_by_name():
    client = TestClient(app)
    r = client.get("/api/v1/components/docker")
    assert r.status_code == 200
    data = r.json()
    assert data["name"] == "docker"
    assert data["layer"] == "L0_infrastructure"
    assert data["is_asset"] is True
    assert data["distribution_form"] == "package"
    assert data["knowledge_artifact"] is False
    print(f"  → docker: layer={data['layer']}, distribution_form={data['distribution_form']}")


def test_search_assets_only():
    client = TestClient(app)

    r = client.get("/api/v1/components?is_asset=true")
    data = r.json()
    assert data["total"] >= 7, f"expected ≥7 assets (补登后更多), got {data['total']}"
    print(f"  → is_asset=true: {data['total']} components")

    r = client.get("/api/v1/components?is_asset=false")
    data = r.json()
    assert data["total"] >= 2, f"expected ≥2 project-level, got {data['total']}"
    print(f"  → is_asset=false: {data['total']} components")


def test_layer_filter():
    client = TestClient(app)
    r = client.get("/api/v1/components?layer=L1_platform")
    data = r.json()
    assert data["total"] >= 5, f"expected ≥5 L1 (补登后 12 个), got {data['total']}"
    print(f"  → L1_platform: {data['total']} components")


def test_composite_tree():
    client = TestClient(app)
    r = client.get("/api/v1/components/intelab.cn-website/tree")
    assert r.status_code == 200
    data = r.json()
    assert data["component"]["name"] == "intelab.cn-website"
    assert data["component"]["atomic"] is False
    assert len(data["children"]) == 2  # nginx + certbot
    child_names = sorted([c["component"]["name"] for c in data["children"]])
    assert child_names == ["certbot", "nginx"], f"got {child_names}"
    print(f"  → intelab.cn-website tree: {child_names}")


def test_usage():
    client = TestClient(app)
    r = client.get("/api/v1/components/docker/usage")
    assert r.status_code == 200
    data = r.json()
    assert "install_command" in data
    assert data["install_command"] == "apt install docker.io"
    print(f"  → docker usage: install={data['install_command']}, example={data['usage_example']}")


def test_search_keyword():
    client = TestClient(app)
    r = client.get("/api/v1/components?q=ssl")
    assert r.status_code == 200
    data = r.json()
    names = [c["name"] for c in data["items"]]
    print(f"  → search 'ssl': {names}")
    assert "certbot" in names


# ===== Phase 1.1 写操作测试 =====
# 注意:开发模式(ARCH_PLATFORM_API_KEY 未设置)= 开放模式,POST/PATCH 不需要 Key
# 生产模式(Key 已设置)= 强制鉴权,无 Key 返回 401


def test_post_component_success():
    """POST 创建新组件(开放模式不需要 Key)"""
    client = TestClient(app)
    payload = {
        "name": "redis",
        "title": "Redis 内存数据库",
        "positioning": "L1 平台层的高性能 KV 缓存,支持多种数据结构,常用于 session/计数器/排行榜",
        "category": "cache",
        "scope": "infra",
        "layer": "L1_platform",
        "atomic": True,
        "composed_of": [],
        "tags": ["cache", "kv", "memory"],
        "is_asset": True,
        "distribution_form": "package",
        "knowledge_artifact": False,
    }
    r = client.post("/api/v1/components", json=payload)
    assert r.status_code == 201, f"got {r.status_code}: {r.text}"
    data = r.json()
    assert data["name"] == "redis"
    assert data["is_asset"] is True
    assert data["distribution_form"] == "package"
    print(f"  → POST created: {data['name']} (id={data['id'][:8]}...)")


def test_post_duplicate_409():
    """重名组件 → 409 Conflict"""
    client = TestClient(app)
    payload = {
        "name": "docker",  # 跟现有 docker 重名
        "title": "Docker 重复",
        "positioning": "尝试创建重名组件,应该返回 409",
        "category": "deploy",
        "scope": "infra",
        "layer": "L0_infrastructure",
        "is_asset": True,
        "distribution_form": "package",
    }
    r = client.post("/api/v1/components", json=payload)
    assert r.status_code == 409, f"expected 409, got {r.status_code}"
    print(f"  → POST duplicate: 409 ✓")


def test_post_asset_missing_form_422():
    """is_asset=true 但没填 distribution_form → 422"""
    client = TestClient(app)
    payload = {
        "name": "broken-asset",
        "title": "broken asset",
        "positioning": "is_asset=true 但不填 distribution_form,应该 422",
        "category": "util",
        "scope": "lib",
        "layer": "L2_capability",
        "is_asset": True,
        # distribution_form 缺失!
    }
    r = client.post("/api/v1/components", json=payload)
    assert r.status_code == 422, f"expected 422, got {r.status_code}: {r.text}"
    print(f"  → POST missing distribution_form: 422 ✓")


def test_post_atomic_conflict_422():
    """atomic=true 但有 composed_of → 422"""
    client = TestClient(app)
    payload = {
        "name": "broken-atomic",
        "title": "broken atomic",
        "positioning": "atomic=true 但又有 composed_of,自相矛盾,应该 422",
        "category": "util",
        "scope": "lib",
        "layer": "L2_capability",
        "atomic": True,
        "composed_of": [{"component_id": "docker", "version_constraint": "^1.0"}],  # 矛盾!
        "is_asset": True,
        "distribution_form": "package",
    }
    r = client.post("/api/v1/components", json=payload)
    assert r.status_code == 422, f"expected 422, got {r.status_code}: {r.text}"
    print(f"  → POST atomic conflict: 422 ✓")


def test_patch_component():
    """PATCH 部分字段更新(把刚才创建的 redis 的 category 改一下)"""
    client = TestClient(app)
    r = client.patch(
        "/api/v1/components/redis",
        json={"title": "Redis 7.x 内存数据库", "tags": ["cache", "kv", "memory", "redis-7"]},
    )
    assert r.status_code == 200, f"got {r.status_code}: {r.text}"
    data = r.json()
    assert data["title"] == "Redis 7.x 内存数据库"
    assert "redis-7" in data["tags"]
    print(f"  → PATCH redis: title updated, tags updated")


# ===== Phase 1.1 步骤 3-6:Version / Deployment / Feedback / Search =====


def test_post_version_success():
    """POST /components/{id}/versions 创建版本(major 必填 breaking_changes)"""
    client = TestClient(app)
    payload = {
        "version": "2.0.0",
        "semver_intent": "major",
        "changelog": "重构 API 路径,/v1 → /v2",
        "breaking_changes": "/v1/auth/login → /v2/auth/token;旧版客户端需升级",
        "compatibility_window": "LTS until 2027-06",
    }
    r = client.post("/api/v1/components/redis/versions", json=payload)
    assert r.status_code == 201, f"got {r.status_code}: {r.text}"
    data = r.json()
    assert data["version"] == "2.0.0"
    assert data["breaking_changes"] is not None
    print(f"  → POST version: redis 2.0.0 (major with breaking_changes)")

    # 验证 Component.current_version_id 自动更新
    r = client.get("/api/v1/components/redis")
    assert r.json()["current_version_id"] is not None
    print(f"  → Component.current_version_id auto-updated")


def test_post_version_major_requires_breaking_changes_422():
    """major 版本不填 breaking_changes → 422"""
    client = TestClient(app)
    payload = {
        "version": "3.0.0",
        "semver_intent": "major",
        "changelog": "破坏性变更但忘了写 breaking_changes",
        # breaking_changes 缺失!
    }
    r = client.post("/api/v1/components/redis/versions", json=payload)
    assert r.status_code == 422, f"expected 422, got {r.status_code}: {r.text}"
    print(f"  → POST major without breaking_changes: 422 ✓")


def test_post_version_duplicate_409():
    """同组件内重复 version → 409"""
    client = TestClient(app)
    payload = {
        "version": "2.0.0",  # 跟刚创建的重复
        "semver_intent": "minor",
        "changelog": "重复创建",
    }
    r = client.post("/api/v1/components/redis/versions", json=payload)
    assert r.status_code == 409, f"expected 409, got {r.status_code}: {r.text}"
    print(f"  → POST duplicate version: 409 ✓")


def test_post_deployment_success():
    """POST /versions/{id}/deployments 登记部署"""
    client = TestClient(app)
    # 先拿 redis 的 current version
    r = client.get("/api/v1/components/redis")
    version_id = r.json()["current_version_id"]
    assert version_id is not None

    payload = {
        "env": "prod",
        "host": "huawei-1",
        "deploy_path": "/opt/services/redis",
        "config_hash": "sha256:abc123...",
        "deployed_by": "github-actions",
        "resolved_versions": {"docker": "29.6.0", "ubuntu-linux": "24.04"},
        "lockfile_hash": "sha256:def456...",
        "build_reproducible": True,
    }
    r = client.post(f"/api/v1/versions/{version_id}/deployments", json=payload)
    assert r.status_code == 201, f"got {r.status_code}: {r.text}"
    data = r.json()
    assert data["host"] == "huawei-1"
    assert data["build_reproducible"] is True
    print(f"  → POST deployment: redis@huawei-1 prod")


def test_post_feedback_success():
    """POST /versions/{id}/feedbacks 登记反馈"""
    client = TestClient(app)
    r = client.get("/api/v1/components/redis")
    version_id = r.json()["current_version_id"]

    payload = {
        "reporter": "andy",
        "bug_summary": "高并发下 redis 偶发连接超时",
        "root_cause": "连接池 max_connections 太小",
        "fix_plan": "调大到 100 + 加 retry",
        "severity": "high",
        "reused_in_projects": ["user-mgmt", "internal-admin"],
    }
    r = client.post(f"/api/v1/versions/{version_id}/feedbacks", json=payload)
    assert r.status_code == 201, f"got {r.status_code}: {r.text}"
    data = r.json()
    assert data["severity"] == "high"
    assert data["status"] == "open"
    print(f"  → POST feedback: redis 高并发连接超时 (high)")


def test_patch_feedback_decision_required_422():
    """转 fixed 状态前必须填 decision → 422"""
    client = TestClient(app)
    r = client.get("/api/v1/feedbacks")
    fb_id = r.json()["items"][0]["id"]

    # 直接 PATCH status=fixed,不填 decision
    r = client.patch(f"/api/v1/feedbacks/{fb_id}", json={"status": "fixed"})
    assert r.status_code == 422, f"expected 422, got {r.status_code}: {r.text}"
    print(f"  → PATCH status=fixed without decision: 422 ✓")


def test_patch_feedback_with_decision_success():
    """先填 decision,再转 fixed → 200 + decided_at 自动设置"""
    client = TestClient(app)
    r = client.get("/api/v1/feedbacks")
    fb_id = r.json()["items"][0]["id"]

    # 1. 先填 decision
    r = client.patch(f"/api/v1/feedbacks/{fb_id}", json={"decision": "optimize"})
    assert r.status_code == 200
    assert r.json()["decided_at"] is not None
    print(f"  → PATCH decision=optimize: decided_at 自动设置")

    # 2. 再转 fixed
    r = client.patch(f"/api/v1/feedbacks/{fb_id}", json={"status": "fixed", "root_cause": "连接池配置问题"})
    assert r.status_code == 200
    assert r.json()["status"] == "fixed"
    print(f"  → PATCH status=fixed (with decision): 200 ✓")


def test_search():
    """GET /search 跨实体搜索"""
    client = TestClient(app)
    r = client.get("/api/v1/search?q=redis")
    assert r.status_code == 200
    data = r.json()
    # 应该搜到 redis component + 之前部署的 deployment 信息可能没出现在 search 里(只在 components)
    comp_names = [c["name"] for c in data["components"]]
    assert "redis" in comp_names
    print(f"  → search 'redis': {data['total']} hits (components: {comp_names})")

    r = client.get("/api/v1/search?q=高并发")
    assert r.status_code == 200
    data = r.json()
    fb_count = len(data["feedbacks"])
    assert fb_count >= 1, f"expected feedback match, got {fb_count}"
    print(f"  → search '高并发': {fb_count} feedbacks matched")


# ===== Phase 1.2 Requirement 模块(2026-06-21)=====


def test_post_requirement_flat():
    """POST /api/v1/requirements 平铺创建(不绑 component)"""
    _setup()  # feedback 53fe92a4:确保 DB + 组件已 seed;不调 _setup() 是因为它会重 import 组件
    client = TestClient(app)
    payload = {
        "title": "建立 GDPR 数据合规审计流程(全公司级)",
        "description": "监管要求 2026-Q3 前完成 GDPR 合规审计流程的搭建",
        "user_story": "As a DPO, I want a repeatable audit flow so that we can prove compliance quarterly",
        "acceptance_criteria": [
            {"given": "客户数据变更", "when": "进入审计流程", "then": "30 天内产出审计报告"}
        ],
        "nfr": {"compliance": "GDPR Article 30"},
        "type": "compliance",
        "priority": "P1",
        "tags": ["gdpr", "audit"],
    }
    r = client.post("/api/v1/requirements", json=payload)
    assert r.status_code == 201, f"got {r.status_code}: {r.text}"
    data = r.json()
    assert data["title"].startswith("建立 GDPR")
    assert data["status"] == "draft"
    assert data["priority"] == "P1"
    assert data["type"] == "compliance"
    assert data["component_id"] is None  # 平铺入口无 component
    print(f"  → POST requirement (flat): {data['id'][:8]}... type={data['type']}")


def test_post_requirement_nested():
    """POST /api/v1/components/{id}/requirements 嵌套创建(绑 component)"""
    _setup()  # feedback 53fe92a4:确保 DB + 组件已 seed
    client = TestClient(app)
    payload = {
        "title": "Redis 支持 cluster 模式自动 failover",
        "description": "当 master 节点故障时,自动选举新 master,客户端无感知",
        "user_story": "As a SRE, I want auto-failover so that SLA 99.99% is achievable",
        "acceptance_criteria": [
            {"given": "master 节点宕机", "when": "sentinel 检测超时", "then": "30s 内完成 master 切换"},
            {"given": "客户端连接", "when": "切换发生", "then": "连接重试透明成功"},
        ],
        "nfr": {"availability": "99.99%"},
        "type": "new_feature",
        "priority": "P0",
        "assignee": "andy",
        "tags": ["redis", "ha"],
    }
    r = client.post("/api/v1/components/redis/requirements", json=payload)
    assert r.status_code == 201, f"got {r.status_code}: {r.text}"
    data = r.json()
    assert data["component_id"] is not None  # 嵌套入口自动绑 component
    assert data["priority"] == "P0"
    assert data["type"] == "new_feature"
    print(f"  → POST nested requirement: redis cluster failover (P0)")


def test_post_requirement_title_too_short_422():
    """title < 20 字符 → 422"""
    _setup()  # feedback 53fe92a4:确保 DB + 组件已 seed
    client = TestClient(app)
    r = client.post("/api/v1/requirements", json={
        "title": "太短了",  # 4 字符
        "type": "new_feature",
    })
    assert r.status_code == 422, f"expected 422, got {r.status_code}"
    print(f"  → POST short title: 422 ✓")


def test_patch_requirement_transition_triaged_requires_assignee_422():
    """draft → triaged 不填 assignee → 422"""
    _setup()  # feedback 53fe92a4:确保 DB + 组件已 seed
    client = TestClient(app)
    # 自给自足:创建 draft(不依赖其他测试)
    r = client.post("/api/v1/requirements", json={
        "title": "测试需求-状态转换必填校验-不应保留-test-only",
        "type": "new_feature",
        "priority": "P2",
    })
    assert r.status_code == 201
    req_id = r.json()["id"]
    # 不传 assignee,直接转 triaged
    r = client.patch(f"/api/v1/requirements/{req_id}", json={"status": "triaged"})
    assert r.status_code == 422, f"expected 422, got {r.status_code}: {r.text}"
    print(f"  → PATCH triaged without assignee: 422 ✓")


def test_patch_requirement_transition_invalid_422():
    """draft → verified(跳级) → 422"""
    _setup()  # feedback 53fe92a4:确保 DB + 组件已 seed
    client = TestClient(app)
    r = client.post("/api/v1/requirements", json={
        "title": "测试需求-状态跳级应被拒绝-不应保留-test-only",
        "type": "refactor",
        "priority": "P3",
    })
    assert r.status_code == 201
    req_id = r.json()["id"]
    r = client.patch(f"/api/v1/requirements/{req_id}", json={
        "status": "verified",
        "assignee": "andy",
    })
    assert r.status_code == 422, f"expected 422, got {r.status_code}"
    print(f"  → PATCH draft → verified (skip): 422 ✓")


def test_patch_requirement_transition_success():
    """draft → triaged (with assignee) → 200 + decided_at 自动设置"""
    _setup()  # feedback 53fe92a4:确保 DB + 组件已 seed
    client = TestClient(app)
    r = client.post("/api/v1/requirements", json={
        "title": "测试需求-正常状态流转-decided-at-应自动设置",
        "type": "new_feature",
        "priority": "P2",
    })
    assert r.status_code == 201
    req_id = r.json()["id"]
    r = client.patch(f"/api/v1/requirements/{req_id}", json={
        "status": "triaged",
        "assignee": "andy",
    })
    assert r.status_code == 200, f"got {r.status_code}: {r.text}"
    data = r.json()
    assert data["status"] == "triaged"
    assert data["assignee"] == "andy"
    assert data["decided_at"] is not None, "decided_at should be auto-set"
    print(f"  → PATCH triaged (with assignee): 200, decided_at auto-set ✓")


def test_patch_requirement_transition_verified_with_component_200():
    """regression:FB-98bc3a4c — 带 component + version 的 requirement 推 verified 必须 200

    Bug:_validate_transition() 引用了未注入的 db 变量,导致 component_id 非空 +
    new_status=verified 路径 500 NameError。修复后该路径能正确执行业务规则:
    - component 有 current_version_id → 200
    - component 无 current_version_id → 422(不是 500)
    """
    _setup()
    client = TestClient(app)
    # 1) 先给 user-auth-jwt 建一个 version(否则 verified 会因业务规则 422,盖过 500 信号)
    r = client.post("/api/v1/components/user-auth-jwt/versions", json={
        "version": "0.99.0",
        "semver_intent": "minor",
        "changelog": "test version for FB-98bc3a4c regression",
    })
    assert r.status_code == 201, f"create version: got {r.status_code}: {r.text}"
    # 2) 嵌套创建(自动绑 component)
    r = client.post("/api/v1/components/user-auth-jwt/requirements", json={
        "title": "测试需求-verified-with-component-200-回归测试-不应保留-test-only",
        "type": "new_feature",
        "priority": "P2",
        "assignee": "andy",
    })
    assert r.status_code == 201, f"create nested: got {r.status_code}: {r.text}"
    req_id = r.json()["id"]
    # 3) 走完到 implemented
    for s in ["triaged", "scheduled", "in_progress", "implemented"]:
        r = client.patch(f"/api/v1/requirements/{req_id}", json={"status": s})
        assert r.status_code == 200, f"got {r.status_code} at {s}: {r.text}"
    # 4) 关键步骤:带 component_id + current_version_id 的 verified 必须 200(以前会 500)
    r = client.patch(f"/api/v1/requirements/{req_id}", json={"status": "verified"})
    assert r.status_code == 200, f"FB-98bc3a4c NOT FIXED — got {r.status_code}: {r.text}"
    assert r.json()["status"] == "verified"
    print(f"  → PATCH verified with component+version: 200 (FB-98bc3a4c fix verified) ✓")


def test_patch_requirement_rejected_requires_description_422():
    """triaged → rejected 不填 description → 422"""
    _setup()  # feedback 53fe92a4:确保 DB + 组件已 seed
    client = TestClient(app)
    # 自给自足:创建并推到 triaged
    r = client.post("/api/v1/requirements", json={
        "title": "测试需求-rejected-必填校验-不应保留-test-only",
        "type": "new_feature",
        "priority": "P2",
    })
    assert r.status_code == 201
    req_id = r.json()["id"]
    r = client.patch(f"/api/v1/requirements/{req_id}", json={
        "status": "triaged",
        "assignee": "andy",
    })
    assert r.status_code == 200
    # 不填 description 转 rejected
    r = client.patch(f"/api/v1/requirements/{req_id}", json={"status": "rejected"})
    assert r.status_code == 422, f"expected 422, got {r.status_code}"
    print(f"  → PATCH rejected without description: 422 ✓")


def test_delete_requirement_archive():
    """DELETE → 软删除(is_archived=True)"""
    _setup()  # feedback 53fe92a4:确保 DB + 组件已 seed
    client = TestClient(app)
    # 创建一个临时需求用于归档(feedback cc15cd4f:title 至少 20 字符)
    r = client.post("/api/v1/requirements", json={
        "title": "临时需求-仅用于测试归档功能-不应在默认列表出现",
        "type": "tech_debt",
        "priority": "P3",
    })
    assert r.status_code == 201, f"got {r.status_code}: {r.text}"
    req_id = r.json()["id"]
    # 归档
    r = client.delete(f"/api/v1/requirements/{req_id}")
    assert r.status_code == 200
    assert r.json()["is_archived"] is True
    # 默认 list 不应出现(include_archived=False)
    r = client.get("/api/v1/requirements")
    ids = [it["id"] for it in r.json()["items"]]
    assert req_id not in ids, "archived req 不应在默认列表"
    # include_archived=True 应出现
    r = client.get("/api/v1/requirements?include_archived=true")
    ids = [it["id"] for it in r.json()["items"]]
    assert req_id in ids, "archived req 应在 include_archived 列表"
    print(f"  → DELETE archive: is_archived=True, 默认列表隐藏 ✓")


def test_get_component_requirements_reverse():
    """GET /components/{id}/requirements 反查"""
    _setup()  # feedback 53fe92a4:确保 DB + 组件已 seed
    client = TestClient(app)
    # 之前 test_post_requirement_nested 创建了 redis 的需求
    r = client.get("/api/v1/components/redis/requirements")
    assert r.status_code == 200
    data = r.json()
    assert data["total"] >= 1
    titles = [it["title"] for it in data["items"]]
    assert any("cluster" in t for t in titles)
    print(f"  → GET component/requirements: redis 有 {data['total']} 个需求")


def test_link_feedback_requirement():
    """POST /feedbacks/{id}/link-requirement + GET /feedbacks/{id}/requirement"""
    _setup()  # feedback 53fe92a4:确保 DB + 组件已 seed
    client = TestClient(app)
    # 拿 feedback(id 在 test_post_feedback_success 创建)
    r = client.get("/api/v1/feedbacks")
    fb_id = r.json()["items"][0]["id"]
    # 拿一个 requirement id
    r = client.get("/api/v1/requirements?include_archived=true")
    req_id = r.json()["items"][0]["id"]
    # link
    r = client.post(f"/api/v1/feedbacks/{fb_id}/link-requirement", json={"requirement_id": req_id})
    assert r.status_code == 200, f"got {r.status_code}: {r.text}"
    assert r.json()["requirement_id"] == req_id
    # 反向查询
    r = client.get(f"/api/v1/feedbacks/{fb_id}/requirement")
    assert r.status_code == 200
    assert r.json()["id"] == req_id
    print(f"  → POST link + GET reverse: feedback → requirement 追溯链 ✓")


def test_requirement_list_filters():
    """GET /requirements 多维过滤"""
    _setup()  # feedback 53fe92a4:确保 DB + 组件已 seed
    client = TestClient(app)
    # 按 priority 过滤
    r = client.get("/api/v1/requirements?priority=P0")
    assert r.status_code == 200
    items = r.json()["items"]
    for it in items:
        assert it["priority"] == "P0"
    # 按 type 过滤
    r = client.get("/api/v1/requirements?type=compliance")
    assert r.status_code == 200
    items = r.json()["items"]
    for it in items:
        assert it["type"] == "compliance"
    # 按 assignee 过滤
    r = client.get("/api/v1/requirements?assignee=andy")
    assert r.status_code == 200
    print(f"  → GET filters: priority/type/assignee ✓")


# ===== Phase 0 Doubt-Driven Development(2026-06-21)=====
# 6 个测试:CRUD + 状态机 + finding 分类 + cross-cycle dedup


def test_post_doubt_cycle_success():
    """POST /api/v1/doubt/cycle 创建 cycle,默认 cycle_count=1"""
    _setup()
    client = TestClient(app)
    payload = {
        "claim": "smoke test: deploy workflow rm -rf 会丢 SQLite 数据,需要白名单模式",
        "artifact": "rm -rf $DEPLOY_PATH",
        "contract": "deploy 必须保留 data/ backups/ .env",
        "created_by": "smoke-test",
    }
    r = client.post("/api/v1/doubt/cycle", json=payload)
    assert r.status_code == 201, f"got {r.status_code}: {r.text}"
    data = r.json()
    assert data["claim"].startswith("smoke test")
    assert data["cycle_count"] == 1
    assert data["max_cycles"] == 3
    assert data["verdict"] is None
    assert data["stopped_at"] is None
    assert data["findings"] == []
    print(f"  → POST doubt cycle: {data['id'][:8]} cycle_count={data['cycle_count']}")


def test_post_doubt_cycle_too_short_claim_422():
    """claim < 10 字符 → 422"""
    _setup()
    client = TestClient(app)
    r = client.post("/api/v1/doubt/cycle", json={
        "claim": "太短",
        "artifact": "code snippet",
        "contract": "should keep data directory",
        "created_by": "smoke-test",
    })
    assert r.status_code == 422, f"expected 422, got {r.status_code}"
    print(f"  → POST short claim: 422 ✓")


def test_post_doubt_finding_all_4_categories():
    """RECONCILE:4 个 finding category 全可分类"""
    _setup()
    client = TestClient(app)
    # 先开 cycle
    cycle_r = client.post("/api/v1/doubt/cycle", json={
        "claim": "smoke test: 4 类 finding 分类端到端",
        "artifact": "code to review",
        "contract": "expected behavior per spec",
        "created_by": "smoke-test",
    })
    assert cycle_r.status_code == 201
    cycle_id = cycle_r.json()["id"]
    # 加 4 个 finding
    cats = ["actionable", "trade_off", "noise", "contract_misread"]
    for cat in cats:
        r = client.post(f"/api/v1/doubt/cycles/{cycle_id}/findings", json={
            "category": cat,
            "severity": "medium",
            "description": f"finding 分类测试 - {cat} 类型样本描述文字 10 字符以上",
        })
        assert r.status_code == 201, f"{cat}: got {r.status_code}: {r.text}"
        assert r.json()["category"] == cat
    # GET 应该看到 4 个
    r = client.get(f"/api/v1/doubt/cycles/{cycle_id}")
    assert r.status_code == 200
    findings = r.json()["findings"]
    assert len(findings) == 4
    assert sorted([f["category"] for f in findings]) == sorted(cats)
    print(f"  → POST 4 findings: {len(findings)} categories all classified ✓")


def test_post_finding_after_stop_409():
    """cycle stopped 后再加 finding → 409"""
    _setup()
    client = TestClient(app)
    cycle_r = client.post("/api/v1/doubt/cycle", json={
        "claim": "smoke test: stop 后不能再加 finding",
        "artifact": "code",
        "contract": "expected behavior per spec",
        "created_by": "smoke-test",
    })
    cycle_id = cycle_r.json()["id"]
    # stop
    r = client.post(f"/api/v1/doubt/cycles/{cycle_id}/stop", json={"reason": "ship it"})
    assert r.status_code == 200
    # 再加 finding 应 409
    r = client.post(f"/api/v1/doubt/cycles/{cycle_id}/findings", json={
        "category": "actionable",
        "description": "stopped cycle 不应再接受 finding 至少 10 字符",
    })
    assert r.status_code == 409, f"expected 409, got {r.status_code}"
    print(f"  → POST finding after stop: 409 ✓")


def test_advance_verdict_pass_sets_stopped_at():
    """verdict=pass → 同步写 stopped_at(stopped_reason='verdict=pass')"""
    _setup()
    client = TestClient(app)
    cycle_r = client.post("/api/v1/doubt/cycle", json={
        "claim": "smoke test: verdict=pass 终态验证",
        "artifact": "code",
        "contract": "expected behavior per spec",
        "created_by": "smoke-test",
    })
    cycle_id = cycle_r.json()["id"]
    r = client.patch(
        f"/api/v1/doubt/cycles/{cycle_id}/advance?verdict=pass&score=0.95&next_step=ship",
    )
    assert r.status_code == 200
    data = r.json()
    assert data["verdict"] == "pass"
    assert data["score"] == 0.95
    assert data["next_step"] == "ship"
    assert data["stopped_at"] is not None
    assert data["stopped_reason"] == "verdict=pass"
    print(f"  → PATCH verdict=pass: stopped_at + stopped_reason 自动设置 ✓")


def test_advance_verdict_fail_sets_stopped_at():
    """verdict=fail → 同步写 stopped_at + score 范围校验"""
    _setup()
    client = TestClient(app)
    cycle_r = client.post("/api/v1/doubt/cycle", json={
        "claim": "smoke test: verdict=fail 终态验证",
        "artifact": "code",
        "contract": "expected behavior per spec",
        "created_by": "smoke-test",
    })
    cycle_id = cycle_r.json()["id"]
    r = client.patch(
        f"/api/v1/doubt/cycles/{cycle_id}/advance?verdict=fail&score=0.2&next_step=fix%20it",
    )
    assert r.status_code == 200
    data = r.json()
    assert data["verdict"] == "fail"
    assert data["score"] == 0.2
    assert data["stopped_at"] is not None
    assert data["stopped_reason"] == "verdict=fail"
    print(f"  → PATCH verdict=fail: stopped_at + stopped_reason 自动设置 ✓")


if __name__ == "__main__":
    test_health()
    test_list_all()
    test_get_by_name()
    test_search_assets_only()
    test_layer_filter()
    test_composite_tree()
    test_usage()
    test_search_keyword()
    # Phase 1.1 写操作 — components
    test_post_component_success()
    test_post_duplicate_409()
    test_post_asset_missing_form_422()
    test_post_atomic_conflict_422()
    test_patch_component()
    # Phase 1.1 写操作 — versions/deployments/feedbacks/search
    test_post_version_success()
    test_post_version_major_requires_breaking_changes_422()
    test_post_version_duplicate_409()
    test_post_deployment_success()
    test_post_feedback_success()
    test_patch_feedback_decision_required_422()
    test_patch_feedback_with_decision_success()
    test_search()
    # Phase 1.2 Requirement 模块(2026-06-21)
    test_post_requirement_flat()
    test_post_requirement_nested()
    test_post_requirement_title_too_short_422()
    test_patch_requirement_transition_triaged_requires_assignee_422()
    test_patch_requirement_transition_invalid_422()
    test_patch_requirement_transition_success()
    test_patch_requirement_transition_verified_with_component_200()
    test_patch_requirement_rejected_requires_description_422()
    test_delete_requirement_archive()
    test_get_component_requirements_reverse()
    test_link_feedback_requirement()
    test_requirement_list_filters()
    print("\n✅ All tests passed!")