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