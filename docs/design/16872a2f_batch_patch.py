#!/usr/bin/env python3
"""REQ-16872a2f Phase 3: 批量补全 14 个 skill 的 composed_of 声明

依赖: REQ-f8fa2992(后端 ComponentUpdate 加 composed_of 字段)已 merge 到 main。
用法: python3 16872a2f_batch_patch.py [--dry-run]

⚠️ 2026-06-22 认知修订(FB-76dd519a):脚本暂不执行,等 runtime_dependency 字段
   上线后由 REQ-1f45f486 统筹处理。脚本保留作未来 runtime_dependency 批量迁移模板。
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

# 设计文档 §3 的 14 个 skill composed_of 候选矩阵(L1+L2+L3 共 14)
COMPOSED_OF_PLAN = {
    # L3_application
    "sdlc": ["sdlc-workflow", "sdlc-registry-validate", "arch-platform-cli"],

    # L2_capability (10 个)
    "audit": ["arch-platform-cli", "consolidate-claude"],
    "audit-triage": ["audit", "arch-platform-cli"],
    "sdlc-requirement": ["arch-platform-cli"],
    "sdlc-design": ["sdlc-requirement", "arch-platform-cli"],
    "sdlc-code": ["sdlc-design", "arch-platform-cli", "pushgithub"],
    "sdlc-operate": ["post-deploy-healthcheck", "arch-platform-cli"],
    "sdlc-feedback": ["arch-platform-cli"],
    "sdlc-workflow": [
        "sdlc-requirement", "sdlc-design", "sdlc-code",
        "sdlc-operate", "sdlc-feedback", "sdlc-registry-validate",
        "doubt-driven-development",
    ],
    "doubt-driven-development": ["arch-platform-cli"],
    "consolidate-claude": ["arch-platform-cli"],

    # L1_platform (3 个)
    "sdlc-registry-validate": ["arch-platform-cli"],
    "connect-cd": ["arch-platform-cli"],
    "pushgithub": [],  # 纯 GH API,无依赖
}

# sdlc-workflow 是编排型 skill,L2→L2 同层依赖允许(CLAUDE.md + SOP.md §分层口子 2026-06-22)


def get_component_id(name: str) -> str | None:
    """查 arch-platform 拿到 component_id(为 PATCH body 准备)"""
    out = subprocess.run(
        ["arch", "component", "get", name, "--format", "json"],
        capture_output=True, text=True, check=False,
    )
    if out.returncode != 0:
        print(f"  ⚠ {name}: {out.stderr.strip()}", file=sys.stderr)
        return None
    try:
        data = json.loads(out.stdout)
        return data["id"]
    except (json.JSONDecodeError, KeyError) as e:
        print(f"  ⚠ {name}: parse err {e}", file=sys.stderr)
        return None


def patch_composed_of(name: str, deps: list[str], dry_run: bool) -> tuple[bool, str]:
    """PATCH component 补 composed_of"""
    if not deps:
        if dry_run:
            return True, "  → no deps (atomic leaf), skip"
        return True, "  → no deps (atomic leaf), skip"

    # 把每个依赖 name 转成 component_id
    dep_entries = []
    for d in deps:
        dep_id = get_component_id(d)
        if not dep_id:
            return False, f"  ✗ dep not found: {d}"
        dep_entries.append({"component_id": dep_id, "version_constraint": "^1.0"})

    body = json.dumps({"composed_of": dep_entries}, ensure_ascii=False)

    if dry_run:
        return True, f"  → DRY-RUN: arch component update {name} body={body[:80]}..."

    # arch CLI 当前不支持 composed_of(FB-38f2024f),直接用 curl PATCH
    comp_id = get_component_id(name)
    if not comp_id:
        return False, f"  ✗ component not found: {name}"

    # PATCH 通过 API(走 curl,因为 arch CLI 的 component update 不支持 composed_of)
    import httpx
    cfg_path = Path.home() / ".config/arch-cli/config.toml"
    api_url = "https://arch.intelab.cn"
    api_key = ""
    if cfg_path.exists():
        # 简单 TOML 解析(避免依赖 tomllib)
        for line in cfg_path.read_text().splitlines():
            line = line.strip()
            if line.startswith("url"):
                api_url = line.split("=", 1)[1].strip().strip('"')
            elif line.startswith("api_key"):
                api_key = line.split("=", 1)[1].strip().strip('"')

    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["X-Api-Key"] = api_key

    r = httpx.patch(
        f"{api_url}/api/v1/components/{comp_id}",
        json={"composed_of": dep_entries},
        headers=headers, timeout=30,
    )
    if r.status_code == 200:
        return True, f"  ✓ PATCH ok ({len(dep_entries)} deps)"
    return False, f"  ✗ PATCH failed {r.status_code}: {r.text[:200]}"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="只看不动")
    parser.add_argument("--only", help="只跑某个 skill(调试用)")
    args = parser.parse_args()

    plan = COMPOSED_OF_PLAN
    if args.only:
        plan = {args.only: COMPOSED_OF_PLAN.get(args.only, [])}
        if not COMPOSED_OF_PLAN.get(args.only):
            print(f"unknown skill: {args.only}", file=sys.stderr)
            return 1

    print(f"=== 16872a2f 批量补全 composed_of ({len(plan)} skills, dry_run={args.dry_run}) ===\n")
    ok, fail = 0, 0
    for name, deps in plan.items():
        print(f"[{name}] deps={deps}")
        success, msg = patch_composed_of(name, deps, args.dry_run)
        print(msg)
        if success:
            ok += 1
        else:
            fail += 1

    print(f"\n=== summary: {ok} ok, {fail} fail ===")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())