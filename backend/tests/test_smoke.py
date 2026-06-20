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
    """建临时表 + 导入 9 个种子组件"""
    init_db()
    db = SessionLocal()
    try:
        importer = MarkdownImporter(db, COMPONENTS_DIR)
        result = importer.import_all()
        print(f"\n[setup] Import: {result}")
        assert result.created == 9, f"expected 9 created, got {result.created}"
        assert len(result.errors) == 0, f"errors: {result.errors}"
    finally:
        db.close()


def test_health():
    _setup()
    client = TestClient(app)
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_list_all():
    client = TestClient(app)
    r = client.get("/api/v1/components")
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 9
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
    assert data["total"] == 7, f"expected 7 assets, got {data['total']}"
    print(f"  → is_asset=true: {data['total']} components")

    r = client.get("/api/v1/components?is_asset=false")
    data = r.json()
    assert data["total"] == 2, f"expected 2 project-level, got {data['total']}"
    print(f"  → is_asset=false: {data['total']} components")


def test_layer_filter():
    client = TestClient(app)
    r = client.get("/api/v1/components?layer=L1_platform")
    data = r.json()
    assert data["total"] == 5, f"expected 5 L1, got {data['total']}"
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


if __name__ == "__main__":
    test_health()
    test_list_all()
    test_get_by_name()
    test_search_assets_only()
    test_layer_filter()
    test_composite_tree()
    test_usage()
    test_search_keyword()
    # Phase 1.1 写操作
    test_post_component_success()
    test_post_duplicate_409()
    test_post_asset_missing_form_422()
    test_post_atomic_conflict_422()
    test_patch_component()
    print("\n✅ All tests passed!")