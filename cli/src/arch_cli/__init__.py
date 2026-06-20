"""arch-platform-cli — 架构平台命令行工具

包结构:
- cli:        Click 入口
- client:     HTTP 客户端(封装 API Key + 重试)
- config:     配置文件管理(~/.config/arch-cli/config.toml)
- commands:   各子命令模块(component / version / feedback / search / use / tree / ...)
- output:     Rich 表格 + 颜色格式化
"""

__version__ = "0.2.0"
__all__ = ["client", "config"]