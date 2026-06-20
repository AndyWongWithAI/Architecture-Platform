"""配置管理:API URL + API Key + 默认输出格式

存储位置:
  Linux:  ~/.config/arch-cli/config.toml
  macOS:  ~/Library/Application Support/arch-cli/config.toml
  WSL:    ~/.config/arch-cli/config.toml(同 Linux)

配置文件示例(~/.config/arch-cli/config.toml):
  [server]
  url = "https://arch.intelab.cn"
  api_key = "sk-xxx..."  # 留空 = 开放模式(读 OK,写被拒)

  [output]
  format = "table"  # table | json
  color = true
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

# Python 3.11+ 内置 tomllib;3.10- 用 tomli
if sys.version_info >= (3, 11):
    import tomllib as toml_lib
else:
    import tomli as toml_lib  # type: ignore[no-redef]


# ——— 默认值 ———
DEFAULT_URL = os.environ.get("ARCH_PLATFORM_URL", "http://127.0.0.1:8088")
DEFAULT_API_KEY = os.environ.get("ARCH_PLATFORM_API_KEY", "")
DEFAULT_FORMAT = "table"
DEFAULT_COLOR = True


def config_dir() -> Path:
    """跨平台配置目录(XDG Base Directory 规范)"""
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg) / "arch-cli"
    return Path.home() / ".config" / "arch-cli"


def config_path() -> Path:
    return config_dir() / "config.toml"


@dataclass
class Config:
    server_url: str = DEFAULT_URL
    api_key: str = DEFAULT_API_KEY
    output_format: str = DEFAULT_FORMAT
    output_color: bool = DEFAULT_COLOR

    def save(self, path: Optional[Path] = None) -> None:
        """写到 TOML 配置文件(权限 0600,因为有 API Key)"""
        path = path or config_path()
        path.parent.mkdir(parents=True, exist_ok=True)

        # 手工写 TOML(避免引入 tomli_w 依赖)
        lines = [
            "# arch-platform-cli 配置",
            "# 权限 0600(包含 API Key)",
            "",
            "[server]",
            f'url = "{self.server_url}"',
            f'api_key = "{self.api_key}"',
            "",
            "[output]",
            f'format = "{self.output_format}"',
            f'color = "{str(self.output_color).lower()}"',
            "",
        ]
        path.write_text("\n".join(lines))
        os.chmod(path, 0o600)

    @classmethod
    def load(cls, path: Optional[Path] = None) -> "Config":
        path = path or config_path()
        if not path.exists():
            return cls()  # 用默认值
        try:
            with open(path, "rb") as f:
                data = toml_lib.load(f)
        except Exception as e:
            raise ValueError(f"配置文件解析失败:{path}: {e}") from e

        server = data.get("server", {})
        output = data.get("output", {})
        return cls(
            server_url=server.get("url", DEFAULT_URL),
            api_key=server.get("api_key", DEFAULT_API_KEY),
            output_format=output.get("format", DEFAULT_FORMAT),
            output_color=output.get("color", DEFAULT_COLOR),
        )

    def masked_key(self) -> str:
        """API Key 脱敏(显示前 4 + 末 4)"""
        if not self.api_key:
            return "(空)"
        if len(self.api_key) <= 8:
            return "***"
        return f"{self.api_key[:4]}...{self.api_key[-4:]}"