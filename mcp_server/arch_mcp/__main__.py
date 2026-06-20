"""支持 python -m arch_mcp 启动 + arch-mcp-server entry point"""
import asyncio
from .server import main as _async_main


def main():
    """同步入口,asyncio.run 包一层 async main"""
    asyncio.run(_async_main())


if __name__ == "__main__":
    main()