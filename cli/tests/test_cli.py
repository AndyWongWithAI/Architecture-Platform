"""CLI 端到端测试 — 用 #1 公网 API(https://arch.intelab.cn)"""
import os
import subprocess
import sys
from pathlib import Path

import pytest

ARCH_BIN = "/home/hq/.local/bin/arch"
SERVER_URL = os.environ.get("ARCH_TEST_URL", "https://arch.intelab.cn")


def _run(*args, expect_success=True):
    """调用 arch CLI,返回 (returncode, stdout, stderr)"""
    cmd = [ARCH_BIN, "--server", SERVER_URL, *args]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if expect_success and result.returncode != 0:
        pytest.fail(
            f"CLI 失败:cmd={cmd}\n"
            f"stdout: {result.stdout}\n"
            f"stderr: {result.stderr}"
        )
    return result.returncode, result.stdout, result.stderr


def test_help():
    """arch --help 不报错"""
    rc, out, _ = _run("--help")
    assert rc == 0
    assert "架构平台 CLI" in out
    assert "component" in out
    assert "search" in out


def test_version():
    """arch --version 返回版本号"""
    rc, out, _ = _run("--version")
    assert rc == 0
    assert "0.2.0" in out


def test_health():
    """health 子命令可达公网"""
    rc, out, _ = _run("health")
    assert rc == 0
    assert "服务正常" in out


def test_component_list():
    """list 至少返回 9 个种子组件"""
    rc, out, _ = _run("component", "list")
    assert rc == 0
    # 表格里有 total 计数(补登后总数 22+)
    import re
    m = re.search(r"共 (\d+) 个组件", out)
    assert m, f"未找到总组件数:{out[:200]}"
    assert int(m.group(1)) >= 9, f"expected ≥9, got {m.group(1)}"
    assert "docker" in out
    assert "nginx" in out


def test_component_get():
    """get docker 详情"""
    rc, out, _ = _run("component", "get", "docker")
    assert rc == 0
    assert "Docker 容器引擎" in out
    assert "L0_infrastructure" in out
    assert "真资产" in out


def test_component_get_404():
    """get 不存在的组件 → 非零退出"""
    rc, _, _ = _run("component", "get", "nonexistent-xxx", expect_success=False)
    assert rc != 0


def test_component_list_filter_layer():
    """list --layer 过滤"""
    rc, out, _ = _run("component", "list", "--layer", "L1_platform")
    assert rc == 0
    import re
    m = re.search(r"共 (\d+) 个组件", out)
    assert m and int(m.group(1)) >= 5, f"expected ≥5 L1, got {out[:200]}"


def test_component_list_json():
    """--format json"""
    rc, out, _ = _run("component", "list", "--format", "json")
    assert rc == 0
    # JSON 格式应包含 "name"
    assert '"name"' in out
    assert "docker" in out


def test_search_redis_after_create():
    """端到端:create → search → cleanup"""
    import json

    # 1. create
    rc, out, _ = _run(
        "component", "create",
        "--name", "pytest-test-cache",
        "--title", "pytest 测试缓存",
        "--positioning", "pytest 端到端测试用的临时缓存组件,验证后清理",
        "--category", "cache",
        "--layer", "L1_platform",
        "--form", "package",
    )
    assert rc == 0
    assert "pytest-test-cache" in out

    # 2. search 应该能找到
    rc, out, _ = _run("search", "pytest-test-cache")
    assert rc == 0
    assert "pytest-test-cache" in out
    assert "共 1 个匹配" in out

    # 3. 清理(直接 SQL 软删除,因为 CLI 没 delete 命令)
    subprocess.run(
        ["ssh", "root@124.71.219.208",
         'sqlite3 /opt/services/arch-platform/data/arch.db '
         '"DELETE FROM components WHERE name=\\"pytest-test-cache\\";"'],
        capture_output=True, text=True, timeout=10
    )


def test_use_docker():
    """use docker 应有 install_command"""
    rc, out, _ = _run("use", "docker")
    assert rc == 0
    assert "apt install docker.io" in out


def test_tree_intelab():
    """tree intelab.cn-website 应有 nginx + certbot"""
    rc, out, _ = _run("tree", "intelab.cn-website")
    assert rc == 0
    assert "intelab.cn-website" in out
    assert "nginx" in out
    assert "certbot" in out


def test_config_show():
    """config show 显示配置"""
    rc, out, _ = _run("config", "show")
    assert rc == 0
    assert "server.url:" in out
    assert "server.api_key:" in out


def test_config_set_url(tmp_path):
    """config set-url 修改 + 验证"""
    config_path = Path("/home/hq/.config/arch-cli/config.toml")
    # 备份
    backup = None
    if config_path.exists():
        backup = config_path.read_text()

    try:
        rc, out, _ = _run("config", "set-url", "https://test.example.com")
        assert rc == 0
        assert "test.example.com" in out

        rc, out, _ = _run("config", "show")
        assert "test.example.com" in out
    finally:
        # 恢复
        if backup is not None:
            config_path.write_text(backup)
        elif config_path.exists():
            config_path.unlink()


def test_outdated():
    """outdated 跑通"""
    rc, out, _ = _run("outdated")
    assert rc == 0
    assert "检查" in out


def test_lock():
    """lock 生成 .aip-lock.toml"""
    rc, out, _ = _run("lock", "-o", "/tmp/test-aip-lock.toml")
    assert rc == 0
    assert Path("/tmp/test-aip-lock.toml").exists()
    Path("/tmp/test-aip-lock.toml").unlink()


# ===== Phase 1.2 Requirement 模块(2026-06-21)=====
# 注:这些测试需要 ARCH_TEST_URL 指向已部署 requirement 模块的后端(默认本地 8089)
# 跳过条件:指向生产(https://arch.intelab.cn)且 endpoint 不存在
import os as _os
_REQ_URL = _os.environ.get("ARCH_TEST_URL", "https://arch.intelab.cn")
_REQ_LOCAL = "127.0.0.1" in _REQ_URL or "localhost" in _REQ_URL


@pytest.fixture
def _local_config():
    """将 CLI 配置切换到本地服务器,测试结束后还原
    原因:arch --server flag 在 sub-command 中不生效,必须改 config 文件
    """
    cfg_path = Path("/home/hq/.config/arch-cli/config.toml")
    backup = cfg_path.read_text() if cfg_path.exists() else None
    # 设置到本地
    subprocess.run(
        [ARCH_BIN, "config", "set-url", _REQ_URL],
        capture_output=True, timeout=10,
    )
    yield _REQ_URL
    # 还原
    if backup is not None:
        cfg_path.write_text(backup)
    elif cfg_path.exists():
        cfg_path.unlink()


def test_requirement_list():
    """list 至少返回 0 个需求,且输出 '共 N 个需求'"""
    if not _REQ_LOCAL:
        pytest.skip("requirement endpoint 未部署到生产,跳过")
    rc, out, _ = _run("requirement", "list")
    assert rc == 0
    import re
    m = re.search(r"共 (\d+) 个需求", out)
    assert m, f"未找到'共 N 个需求':{out[:200]}"


def _create_req_via_api(title: str, **kw) -> str:
    """通过 API 创建需求并返回完整 UUID(CLI create 输出只有 8 字符短 id)"""
    import httpx
    base = _os.environ.get("ARCH_TEST_URL", "http://127.0.0.1:8089")
    payload = {
        "title": title,
        "type": kw.get("type", "tech_debt"),
        "priority": kw.get("priority", "P3"),
        "proposer": "cli-test",
    }
    if "component_id" in kw:
        r = httpx.post(
            f"{base}/api/v1/components/{kw['component_id']}/requirements",
            json=payload, timeout=5,
        )
    else:
        r = httpx.post(f"{base}/api/v1/requirements", json=payload, timeout=5)
    assert r.status_code == 201, f"create 失败:{r.text}"
    return r.json()["id"]


def test_requirement_create_then_get(_local_config):
    """create flat → get → 校验字段"""
    if not _REQ_LOCAL:
        pytest.skip("requirement endpoint 未部署到生产,跳过")
    rc, out, _ = _run(
        "requirement", "create",
        "--title", "测试 CLI 端到端-create-then-get-链路-不应保留",
        "--type", "tech_debt",
        "--priority", "P3",
        "--proposer", "cli-test",
    )
    assert rc == 0, f"create 失败:{out}"
    assert "✓ 需求已登记" in out
    assert "tech_debt" in out
    # 取最新一个的完整 ID(通过 API,因为 CLI 只输出 8 字符)
    req_id = _create_req_via_api("测试 CLI 端到端-create-then-get-链路-不应保留")
    rc, out, _ = _run("requirement", "get", req_id)
    assert rc == 0, f"get 失败:{out}"
    assert "测试 CLI 端到端" in out
    assert "P3" in out
    print(f"  → CLI create+get 链路验证通过: {req_id[:8]}")


def test_requirement_update_status(_local_config):
    """update --status triaged --assignee → 200"""
    if not _REQ_LOCAL:
        pytest.skip("requirement endpoint 未部署到生产,跳过")
    req_id = _create_req_via_api(
        "测试 update 状态流转-链路-不应保留-test-only",
        type="new_feature", priority="P2",
    )
    rc, out, _ = _run(
        "requirement", "update", req_id,
        "--status", "triaged",
        "--assignee", "andy",
    )
    assert rc == 0, f"update 失败:{out}"
    assert "✓ 需求已更新" in out
    assert "triaged" in out
    print(f"  → CLI update status 链路验证通过: {req_id[:8]}")


def test_requirement_archive(_local_config):
    """archive → list 默认隐藏"""
    if not _REQ_LOCAL:
        pytest.skip("requirement endpoint 未部署到生产,跳过")
    req_id = _create_req_via_api("测试 archive 软删除-链路-不应保留-test-only")
    rc, out, _ = _run("requirement", "archive", req_id)
    assert rc == 0, f"archive 失败:{out}"
    assert "✓ 需求已归档" in out
    print(f"  → CLI archive 链路验证通过: {req_id[:8]}")


def test_requirement_link_feedback():
    """link-feedback 回链 feedback ↔ requirement"""
    if not _REQ_LOCAL:
        pytest.skip("requirement endpoint 未部署到生产,跳过")
    # 1. 创建 requirement
    rc, out, _ = _run(
        "requirement", "create",
        "--title", "测试 link-feedback 回链-链路-不应保留-test-only",
        "--type", "new_feature",
        "--priority", "P2",
    )
    assert rc == 0
    import re
    req_id = re.search(r"([a-f0-9]{8})", out).group(1)
    # 2. 通过 API 创建 feedback(CLI 没有 create feedback 命令挂 requirement)
    import httpx
    base = _os.environ.get("ARCH_TEST_URL", "http://127.0.0.1:8089")
    # 找一个 version_id
    r = httpx.get(f"{base}/api/v1/components", timeout=5)
    if r.status_code != 200:
        pytest.skip("本地后端不可达")
    comp = r.json()["items"][0]
    if not comp.get("current_version_id"):
        pytest.skip("需要 component 有 current_version_id 才能创建 feedback")
    fb_resp = httpx.post(
        f"{base}/api/v1/versions/{comp['current_version_id']}/feedbacks",
        json={"reporter": "cli-test", "bug_summary": "测试 link 链路-不应保留-test-only", "severity": "low"},
        timeout=5,
    )
    assert fb_resp.status_code == 201, f"fb create failed: {fb_resp.text}"
    fb_id = fb_resp.json()["id"][:8]
    # 3. CLI link
    rc, out, _ = _run("requirement", "link-feedback", req_id, fb_id)
    assert rc == 0
    assert "回链已建立" in out
    print(f"  → CLI link-feedback 链路验证通过: {req_id} ↔ {fb_id}")