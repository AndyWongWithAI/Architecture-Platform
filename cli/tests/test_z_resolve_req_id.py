"""单元测试:arch_cli.client.ArchClient._resolve_req_id

覆盖 feedback 62634495:CLI requirement get 100% 404 修复。

按 [[feedback-test-ordering]] 约定,共享 DB/env 用 test_z_ 前缀排最后。
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# 让 import 找得到 src/arch_cli
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from arch_cli.client import APIError, ArchClient  # noqa: E402


FULL_UUID_1 = "aace22c5-f06d-4f86-b0fc-ae3274ebf978"
FULL_UUID_2 = "aace22c5-ffff-4fff-bfff-ae3274ebf999"  # 同前缀 8 位
FULL_UUID_3 = "b0000000-0000-0000-0000-000000000000"


def _make_client():
    """跳过真实 HTTP,所有 request 调用走 mock"""
    cfg = MagicMock()
    cfg.api_key = None
    return ArchClient(cfg)


def test_full_uuid_returned_as_is():
    """完整 UUID 直接返回(大小写皆识别),不查 list"""
    c = _make_client()
    assert c._resolve_req_id(FULL_UUID_1) == FULL_UUID_1
    # 大小写皆被正则接受,返回值原样保留
    assert c._resolve_req_id(FULL_UUID_1.upper()) == FULL_UUID_1.upper()


def test_short_id_resolves_to_full_uuid():
    """短 ID 前缀唯一匹配时返回完整 UUID"""
    c = _make_client()
    c.request = MagicMock(return_value={
        "items": [{"id": FULL_UUID_1}, {"id": FULL_UUID_3}],
        "total": 2,
    })
    out = c._resolve_req_id("aace22c5")
    assert out == FULL_UUID_1
    # 命中后早退,只调一次 list
    assert c.request.call_count == 1


def test_short_id_ambiguous_raises_409():
    """同前缀 8 位有 2 个匹配时,抛 409 提示用户加长前缀"""
    c = _make_client()
    c.request = MagicMock(return_value={
        "items": [{"id": FULL_UUID_1}, {"id": FULL_UUID_2}],
        "total": 2,
    })
    with pytest.raises(APIError) as exc:
        c._resolve_req_id("aace22c5")
    assert exc.value.status_code == 409
    assert "匹配到 2" in exc.value.message
    # 早退(找到 2 个就 break),不会继续翻页
    assert c.request.call_count == 1


def test_short_id_not_found_raises_404():
    """短 ID 无匹配时抛 404,提示检查 --include-archived"""
    c = _make_client()
    c.request = MagicMock(return_value={
        "items": [{"id": FULL_UUID_3}],
        "total": 1,
    })
    with pytest.raises(APIError) as exc:
        c._resolve_req_id("deadbeef")
    assert exc.value.status_code == 404
    assert "deadbeef" in exc.value.message
    assert "include-archived" in exc.value.message


def test_short_id_pagination_walks_pages():
    """目标在第 2 页也能找到;超过 max_pages 才停"""
    c = _make_client()
    page1 = {"items": [{"id": f"a{i:07x}-1111-4111-8111-111111111111"} for i in range(100)], "total": 150}
    page2 = {"items": [
        {"id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"},
        *[{"id": f"b{i:07x}-1111-4111-8111-111111111111"} for i in range(49)],
    ], "total": 150}
    c.request = MagicMock(side_effect=[page1, page2])
    out = c._resolve_req_id("aaaaaaaa")
    assert out == "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
    assert c.request.call_count == 2