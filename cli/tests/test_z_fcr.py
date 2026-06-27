"""Q3 目标 1 / fcr metric CLI 测试(2026-06-27)

测试矩阵(本地 CliRunner + 假 client,避免依赖网络):
  - 正常调用 --name=audit --fcr=0.85 → exit 0
  - fcr > 1.0 → exit 1 + stderr(被 click.FloatRange 拦截)
  - fcr < 0.0 → exit 1 + stderr
  - component 不存在 → exit 1 + stderr(client 抛 APIError)
  - 子命令在 `arch component --help` 中可见
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

# 让 tests/ 能 import arch_cli
CLI_SRC = Path(__file__).resolve().parent.parent / "src"
if str(CLI_SRC) not in sys.path:
    sys.path.insert(0, str(CLI_SRC))

from arch_cli.cli import main  # noqa: E402
from arch_cli.client import APIError  # noqa: E402


@pytest.fixture
def runner():
    return CliRunner(mix_stderr=False)


def _mock_client_method(fcr_value=None, name="audit"):
    """构造 mock ArchClient,让 report_fcr 返回带 fcr 字段的 dict"""
    mock = MagicMock()
    if isinstance(fcr_value, Exception):
        mock.report_fcr.side_effect = fcr_value
    else:
        mock.report_fcr.return_value = {
            "id": "fake-uuid-1234",
            "name": name,
            "fcr": fcr_value,
        }
    return mock


# ===== happy path =====

def test_report_fcr_happy_path(runner):
    """正常调用 --name=audit --fcr=0.85 → exit 0"""
    mock_client = _mock_client_method(fcr_value=0.85, name="audit")
    with patch("arch_cli.commands.component.ArchClient", return_value=mock_client):
        result = runner.invoke(
            main,
            ["component", "report-fcr", "--name", "audit", "--fcr", "0.85"],
        )
    assert result.exit_code == 0, f"应 exit 0,got {result.exit_code}\nstdout: {result.stdout}\nstderr: {result.stderr}"
    assert "audit" in result.stdout
    assert "0.85" in result.stdout
    # 验证 client 被以正确参数调用
    mock_client.report_fcr.assert_called_once_with("audit", 0.85)


def test_report_fcr_boundary_zero(runner):
    """fcr=0.0 合法"""
    mock_client = _mock_client_method(fcr_value=0.0)
    with patch("arch_cli.commands.component.ArchClient", return_value=mock_client):
        result = runner.invoke(
            main,
            ["component", "report-fcr", "--name", "audit", "--fcr", "0.0"],
        )
    assert result.exit_code == 0
    mock_client.report_fcr.assert_called_once_with("audit", 0.0)


def test_report_fcr_boundary_one(runner):
    """fcr=1.0 合法"""
    mock_client = _mock_client_method(fcr_value=1.0)
    with patch("arch_cli.commands.component.ArchClient", return_value=mock_client):
        result = runner.invoke(
            main,
            ["component", "report-fcr", "--name", "audit", "--fcr", "1.0"],
        )
    assert result.exit_code == 0
    mock_client.report_fcr.assert_called_once_with("audit", 1.0)


# ===== 范围校验 =====

def test_report_fcr_above_one_rejected(runner):
    """fcr=1.5 → exit 2(click 校验失败)+ stderr"""
    mock_client = _mock_client_method(fcr_value=0.0)
    with patch("arch_cli.commands.component.ArchClient", return_value=mock_client):
        result = runner.invoke(
            main,
            ["component", "report-fcr", "--name", "audit", "--fcr", "1.5"],
        )
    # click.FloatRange 校验失败 → exit 2
    assert result.exit_code == 2
    # client 不应被调用
    mock_client.report_fcr.assert_not_called()


def test_report_fcr_below_zero_rejected(runner):
    """fcr=-0.1 → exit 2 + stderr"""
    mock_client = _mock_client_method(fcr_value=0.0)
    with patch("arch_cli.commands.component.ArchClient", return_value=mock_client):
        result = runner.invoke(
            main,
            ["component", "report-fcr", "--name", "audit", "--fcr", "-0.1"],
        )
    assert result.exit_code == 2
    mock_client.report_fcr.assert_not_called()


# ===== 业务错误 =====

def test_report_fcr_component_not_found(runner):
    """component 不存在 → client 抛 APIError(404)→ CLI exit 1 + stderr"""
    mock_client = _mock_client_method(
        fcr_value=APIError(404, "资源不存在:component 'xxx' not found"),
    )
    with patch("arch_cli.commands.component.ArchClient", return_value=mock_client):
        result = runner.invoke(
            main,
            ["component", "report-fcr", "--name", "xxx", "--fcr", "0.5"],
        )
    assert result.exit_code == 1, f"应 exit 1,got {result.exit_code}\nstdout: {result.stdout}\nstderr: {result.stderr}"
    assert "上报失败" in result.stdout


def test_report_fcr_missing_required_args(runner):
    """缺 --name 或 --fcr → exit 2"""
    result = runner.invoke(main, ["component", "report-fcr"])
    assert result.exit_code == 2
    # stderr 含 "Missing option"
    # mix_stderr=False → stderr 独立
    # click 8.x 把 usage 写到 stderr
    combined = (result.stdout or "") + (result.stderr or "")
    assert "Missing option" in combined or "required" in combined.lower()


# ===== 子命令在帮助中可见 =====

def test_report_fcr_in_component_help(runner):
    """`arch component --help` 应含 report-fcr"""
    result = runner.invoke(main, ["component", "--help"])
    assert result.exit_code == 0
    assert "report-fcr" in result.stdout
