"""Backend tests conftest — 必须在所有测试文件 import 前生效

目的:重置 ARCH_API_BASE,避免 test_ui.py 默认值 8088 锁住 proxy 模块。

注意:这必须在任何 `from app.ui.proxy import ...` 之前执行。
pytest 会先 collect 所有 conftest.py,再 collect 测试文件,所以这里设置生效。
"""
import os

# 默认让 proxy 指向 8088(test_ui.py 用的端口)
# test_z_requirement_edit.py 在 fixture 中再覆盖成 8089
os.environ.setdefault("ARCH_API_BASE", "http://127.0.0.1:8088")