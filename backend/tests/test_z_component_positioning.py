"""REQ-fd9b6b90 / ComponentUpdate schema 缺 positioning 字段修复测试(2026-06-27)

测试矩阵:
  - PATCH /api/v1/components/{name} body={"positioning": "new text"} → 200 + 落库
  - PATCH 不传 positioning → 原值保留(其他字段可改)
  - PATCH positioning 长度 < 10 → 422(Pydantic min_length 校验)
  - PATCH positioning 长度 > 500 → 422(Pydantic max_length 校验)

端口:8093(避开 test_ui.py 8088 / test_z_requirement_edit.py 8089 /
     test_z_audit.py 8090 / test_z_component_delete.py 8091 / test_z_fcr.py 8092)
DB:独立临时文件,避免污染 dev DB
"""
import os
import sys
import tempfile

# ——— 必须先于任何 app.* import 设置环境变量 ———

# 1) DB:独立临时 DB(隔离)
TEST_DB = tempfile.NamedTemporaryFile(suffix=".db", delete=False, prefix="arch-pos-test-")
TEST_DB.close()
os.environ["ARCH_DB_PATH"] = TEST_DB.name

# 2) UI proxy:指向 8093(本文件专用端口)
os.environ.pop("ARCH_API_BASE", None)
os.environ["ARCH_API_BASE"] = "http://127.0.0.1:8093"

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
    """启动 FastAPI 测试服务器 127.0.0.1:8093"""
    import uvicorn
    from app.main import app

    config = uvicorn.Config(app, host="127.0.0.1", port=8093, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    for _ in range(50):
        try:
            httpx.get("http://127.0.0.1:8093/healthz", timeout=1.0)
            break
        except Exception:
            time.sleep(0.1)

    yield "http://127.0.0.1:8093"

    server.should_exit = True
    thread.join(timeout=2)


def _auth_headers():
    api_key = os.environ.get("ARCH_PLATFORM_API_KEY", "")
    return {"X-API-Key": api_key} if api_key else {}


# ——— 辅助:通过 API 建组件(open 模式) ———

def _create_component(backend, name: str, positioning: str = None) -> dict:
    """建组件(返回 dict)。positioning 默认 ≥ 10 字符,符合 Pydantic 校验"""
    payload = {
        "name": name,
        "title": f"positioning-test-{name}",
        "positioning": positioning or "REQ-fd9b6b90 修复前默认定位文本,测试用临时组件",
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

def test_patch_positioning_succeeds(backend):
    """AC1: PATCH positioning → 200 + 落库(核心修复点)

    修复前: Pydantic ComponentUpdate 缺 positioning 字段 → 静默丢弃,DB 仍是旧值
    修复后: 字段进入 Pydantic → 进入 payload.model_dump(exclude_unset=True)
            → setattr(comp, 'positioning', val) → commit → DB 新值
    """
    comp = _create_component(backend, "pos-patch-ok")
    original_pos = comp["positioning"]
    assert len(original_pos) >= 10  # 起点必须合法

    new_pos = "REQ-fd9b6b90 修复后 PATCH 写入新定位,验证 Pydantic 不再静默丢弃未知字段"
    r = httpx.patch(
        f"{backend}/api/v1/components/pos-patch-ok",
        json={"positioning": new_pos},
        headers=_auth_headers(),
        timeout=5.0,
    )
    assert r.status_code == 200, f"PATCH 失败:{r.status_code} {r.text[:300]}"
    body = r.json()
    assert body["positioning"] == new_pos, f"响应 positioning 应为新值,got {body['positioning']!r}"
    assert body["positioning"] != original_pos, "新值与原值必须不同"

    # 落库校验:再 GET 一次
    r2 = httpx.get(f"{backend}/api/v1/components/pos-patch-ok", timeout=5.0)
    assert r2.json()["positioning"] == new_pos, "DB 持久化失败"
    print(f"  → AC1 PATCH positioning: 200 + 响应新值 + DB 持久化 ✓")


def test_patch_omitting_positioning_preserves_old(backend):
    """AC2: PATCH 不传 positioning → 原值保留(其他字段可改)"""
    comp = _create_component(backend, "pos-preserve", positioning="原始 positioning 文本,不能被覆盖")
    original_pos = comp["positioning"]

    # PATCH 改 title,不带 positioning
    r = httpx.patch(
        f"{backend}/api/v1/components/pos-preserve",
        json={"title": "title 改了,但 positioning 不能动"},
        headers=_auth_headers(),
        timeout=5.0,
    )
    assert r.status_code == 200, f"PATCH 失败:{r.status_code} {r.text[:300]}"
    body = r.json()
    assert body["title"] == "title 改了,但 positioning 不能动", "title 应被改"
    assert body["positioning"] == original_pos, f"positioning 应保留原值,got {body['positioning']!r}"
    print(f"  → AC2 PATCH 不传 positioning: 原值保留 + 其他字段可改 ✓")


def test_patch_positioning_too_short_422(backend):
    """AC3a: positioning 长度 < 10 → 422(min_length=10 校验)"""
    _create_component(backend, "pos-short")
    r = httpx.patch(
        f"{backend}/api/v1/components/pos-short",
        json={"positioning": "太短"},  # 3 字符
        headers=_auth_headers(),
        timeout=5.0,
    )
    assert r.status_code == 422, f"期望 422,got {r.status_code} {r.text[:300]}"
    # 验证错误信息含 min_length 关键词
    body = r.text.lower()
    assert "min_length" in body or "at least 10" in body or "min" in body, \
        f"422 响应应含 min_length 提示,got {r.text[:300]}"
    print(f"  → AC3a PATCH positioning<10 字符: 422 + min_length 校验 ✓")


def test_patch_positioning_too_long_422(backend):
    """AC3b: positioning 长度 > 500 → 422(max_length=500 校验)"""
    _create_component(backend, "pos-long")
    r = httpx.patch(
        f"{backend}/api/v1/components/pos-long",
        json={"positioning": "x" * 501},  # 501 字符
        headers=_auth_headers(),
        timeout=5.0,
    )
    assert r.status_code == 422, f"期望 422,got {r.status_code} {r.text[:300]}"
    body = r.text.lower()
    assert "max_length" in body or "at most 500" in body or "max" in body, \
        f"422 响应应含 max_length 提示,got {r.text[:300]}"
    print(f"  → AC3b PATCH positioning>500 字符: 422 + max_length 校验 ✓")


def test_schema_field_present_at_import_time():
    """smoke: import 阶段就能验证 schema 含 positioning(避免运行时才发现缺)"""
    from app.schemas import ComponentUpdate
    fields = ComponentUpdate.model_fields
    assert "positioning" in fields, f"ComponentUpdate 缺 positioning 字段,当前字段:{list(fields.keys())}"
    # 验证约束(Optional + min_length=10 + max_length=500)
    f = fields["positioning"]
    assert f.default is None, "positioning 应为 Optional(默认 None)"
    # Pydantic v2:metadata 含 min_length/max_length 约束
    from pydantic import Field
    constraints = f.metadata
    min_len = next((c.min_length for c in constraints if hasattr(c, "min_length")), None)
    max_len = next((c.max_length for c in constraints if hasattr(c, "max_length")), None)
    assert min_len == 10, f"min_length 应为 10,got {min_len}"
    assert max_len == 500, f"max_length 应为 500,got {max_len}"
    print(f"  → schema import: ComponentUpdate 含 positioning + min=10 + max=500 ✓")
