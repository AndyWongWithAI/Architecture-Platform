"""Q3 目标 1 / fcr metric 测试(2026-06-27)

测试矩阵:
  - PUT /api/v1/components/{name}/fcr happy path(0.85 → 200 + 字段落库)
  - PUT /api/v1/components/{id}/fcr 按 UUID 定位
  - PUT /api/v1/components/{name}/fcr 范围校验(>1.0 / <0.0 → 422)
  - GET /api/v1/components/{name} 返回 JSON 含 fcr 字段
  - 新建 component 后 fcr 默认为 NULL

端口:8092(避开 test_ui.py 8088 / test_z_audit.py 8090 / test_z_requirement_edit.py 8089)
DB:临时文件,避免污染 dev DB
"""
import os
import sys
import tempfile

# ——— 必须先于任何 app.* import 设置环境变量 ———

# 1) DB:独立临时 DB(隔离)
TEST_DB = tempfile.NamedTemporaryFile(suffix=".db", delete=False, prefix="arch-fcr-test-")
TEST_DB.close()
os.environ["ARCH_DB_PATH"] = TEST_DB.name

# 2) UI proxy:指向 8092(本文件专用端口)
os.environ.pop("ARCH_API_BASE", None)
os.environ["ARCH_API_BASE"] = "http://127.0.0.1:8092"

import importlib  # noqa: E402
import threading  # noqa: E402
import time  # noqa: E402

import httpx  # noqa: E402
import pytest  # noqa: E402

for _mod in ("app.ui.proxy", "app.ui.routes"):
    if _mod in sys.modules:
        importlib.reload(sys.modules[_mod])


# ——— 后端 fixture ———

@pytest.fixture(scope="module")
def backend():
    """启动 FastAPI 测试服务器 127.0.0.1:8092"""
    import uvicorn
    from app.main import app

    config = uvicorn.Config(app, host="127.0.0.1", port=8092, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    for _ in range(50):
        try:
            httpx.get("http://127.0.0.1:8092/healthz", timeout=1.0)
            break
        except Exception:
            time.sleep(0.1)

    yield "http://127.0.0.1:8092"

    server.should_exit = True
    thread.join(timeout=2)


# ——— 辅助:通过 API 建组件(open 模式) ———

def _create_component(backend, name: str, title: str = None) -> dict:
    """开 mode 下建组件,返回 dict(含 id)"""
    payload = {
        "name": name,
        "title": title or f"fcr-test-{name}",
        "positioning": "Q3 目标 1 fcr 字段测试用临时组件,验证后清理(测试隔离)",
        "category": "util",
        "layer": "L1_platform",
        "scope": "lib",
        "is_asset": True,
        "distribution_form": "package",
        "atomic": True,
    }
    r = httpx.post(f"{backend}/api/v1/components", json=payload, timeout=5.0)
    assert r.status_code == 201, f"创建失败:{r.status_code} {r.text[:300]}"
    return r.json()


# ===== 测试用例 =====

def test_fcr_default_null_on_new_component(backend):
    """新建 component 后,GET 详情应含 fcr=None"""
    data = _create_component(backend, "fcr-default-test")
    r = httpx.get(f"{backend}/api/v1/components/{data['id']}", timeout=5.0)
    assert r.status_code == 200
    body = r.json()
    assert "fcr" in body, f"GET 详情缺 fcr 字段:{list(body.keys())}"
    assert body["fcr"] is None, f"新组件 fcr 应为 NULL,got {body['fcr']!r}"
    print(f"  → 新组件 fcr=None ✓")


def test_fcr_endpoint_updates_component_by_name(backend):
    """PUT /components/{name}/fcr → 200 + 字段落库"""
    _create_component(backend, "fcr-by-name")
    r = httpx.put(
        f"{backend}/api/v1/components/fcr-by-name/fcr",
        json={"fcr": 0.85},
        timeout=5.0,
    )
    assert r.status_code == 200, f"PUT 失败:{r.status_code} {r.text[:300]}"
    data = r.json()
    assert data["name"] == "fcr-by-name"
    assert data["fcr"] == 0.85
    # 验证落库:再 GET 一次
    r2 = httpx.get(f"{backend}/api/v1/components/fcr-by-name", timeout=5.0)
    assert r2.json()["fcr"] == 0.85
    print(f"  → PUT fcr by name: 0.85 ✓")


def test_fcr_endpoint_updates_component_by_id(backend):
    """PUT /components/{id}/fcr(UUID 定位)→ 200"""
    data = _create_component(backend, "fcr-by-id")
    r = httpx.put(
        f"{backend}/api/v1/components/{data['id']}/fcr",
        json={"fcr": 0.42},
        timeout=5.0,
    )
    assert r.status_code == 200, f"PUT 失败:{r.status_code} {r.text[:300]}"
    body = r.json()
    assert body["fcr"] == 0.42
    print(f"  → PUT fcr by uuid: 0.42 ✓")


def test_fcr_endpoint_validates_range_above_one(backend):
    """fcr=1.5 → 422"""
    _create_component(backend, "fcr-range-high")
    r = httpx.put(
        f"{backend}/api/v1/components/fcr-range-high/fcr",
        json={"fcr": 1.5},
        timeout=5.0,
    )
    assert r.status_code == 422, f"期望 422,got {r.status_code} {r.text[:300]}"
    print(f"  → fcr=1.5 → 422 ✓")


def test_fcr_endpoint_validates_range_below_zero(backend):
    """fcr=-0.1 → 422"""
    _create_component(backend, "fcr-range-low")
    r = httpx.put(
        f"{backend}/api/v1/components/fcr-range-low/fcr",
        json={"fcr": -0.1},
        timeout=5.0,
    )
    assert r.status_code == 422, f"期望 422,got {r.status_code} {r.text[:300]}"
    print(f"  → fcr=-0.1 → 422 ✓")


def test_fcr_endpoint_accepts_boundary_values(backend):
    """fcr=0.0 和 fcr=1.0 都是合法边界"""
    _create_component(backend, "fcr-boundary-zero")
    r = httpx.put(
        f"{backend}/api/v1/components/fcr-boundary-zero/fcr",
        json={"fcr": 0.0},
        timeout=5.0,
    )
    assert r.status_code == 200
    assert r.json()["fcr"] == 0.0

    _create_component(backend, "fcr-boundary-one")
    r = httpx.put(
        f"{backend}/api/v1/components/fcr-boundary-one/fcr",
        json={"fcr": 1.0},
        timeout=5.0,
    )
    assert r.status_code == 200
    assert r.json()["fcr"] == 1.0
    print(f"  → fcr=0.0 / fcr=1.0 边界值均通过 ✓")


def test_fcr_endpoint_404_for_missing_component(backend):
    """PUT 不存在的 component → 404"""
    r = httpx.put(
        f"{backend}/api/v1/components/does-not-exist-xyz/fcr",
        json={"fcr": 0.5},
        timeout=5.0,
    )
    assert r.status_code == 404
    print(f"  → PUT 不存在 component → 404 ✓")


def test_fcr_returned_in_list_response(backend):
    """GET /components 列表里每条都应含 fcr 字段(可能为 null)"""
    _create_component(backend, "fcr-list-test")
    r = httpx.get(f"{backend}/api/v1/components", timeout=5.0)
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) >= 1
    # 至少第一条新组件应含 fcr
    fcr_test = next((it for it in items if it["name"] == "fcr-list-test"), None)
    assert fcr_test is not None
    assert "fcr" in fcr_test
    print(f"  → 列表含 fcr 字段 ✓")
