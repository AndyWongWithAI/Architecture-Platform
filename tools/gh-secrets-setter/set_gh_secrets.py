#!/usr/bin/env python3
"""Set GitHub Actions secrets via API with libsodium sealed_box encryption.

Why this exists (the asset value):
- GitHub's API requires secrets to be encrypted with the repo's public key
  using libsodium sealed_box (X25519 + XSalsa20-Poly1305), NOT RSA.
- WSL DNS hijacks `api.github.com` → 127.0.0.1, breaking both `gh` CLI
  and direct `requests`. This script patches `socket.getaddrinfo` to
  bypass the poisoning transparently.

Scope (CLAUDE.md 定位稳定性):
- IN:  write encrypted GH Actions secrets for any public/private repo
- OUT: secret rotation, secret deletion, fine-grained tokens, org-level secrets
       (use `gh secret` CLI for those, or extend here as separate functions)

Usage:
  # minimal: one secret
  set_gh_secrets.py --repo OWNER/REPO --token ghp_xxx \\
    --secret SSH_USER=root

  # multiple secrets, with SSH key from file
  set_gh_secrets.py --repo OWNER/REPO --token ghp_xxx \\
    --secret SSH_USER=root \\
    --secret 'SSH_KEY=@~/.ssh/github_actions_arch_platform' \\
    --secret ARCH_API_KEY=abc123

  # from config file
  set_gh_secrets.py --repo OWNER/REPO --token ghp_xxx --config secrets.json

  # force GitHub IP even outside WSL (useful in CI runners with broken DNS)
  set_gh_secrets.py --repo OWNER/REPO --token ghp_xxx \\
    --force-ip 140.82.112.5 \\
    --secret FOO=bar

Reference: https://docs.github.com/en/rest/actions/secrets
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import socket
import sys
from pathlib import Path
from typing import Iterable

import requests
from nacl.public import PublicKey, SealedBox


# === DNS bypass (the WSL differentiator) ===
# WSL's /etc/resolv.conf points to a DNS that returns 127.0.0.1 for
# api.github.com. The actual GitHub API IP is 140.82.112.5 (or 140.82.112.4).
_ORIG = socket.getaddrinfo


def _patched_getaddrinfo(host, *args, **kwargs):
    if host == "api.github.com":
        # Try env override first (for non-WSL environments that need same fix)
        ip = os.environ.get("GH_API_IP", "140.82.112.5")
        host = ip
    return _ORIG(host, *args, **kwargs)


socket.getaddrinfo = _patched_getaddrinfo


API_BASE = os.environ.get("GH_API_BASE", "https://api.github.com:443")


# === CLI parsing ===
def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Set GH Actions secrets via sealed_box encrypted API",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("--repo", required=True, help="owner/repo, e.g. AndyWongWithAI/industry-value-flow")
    p.add_argument(
        "--token",
        default=os.environ.get("GH_TOKEN"),
        help="GitHub PAT with `actions:write` scope (or env GH_TOKEN)",
    )
    p.add_argument(
        "--secret",
        action="append",
        default=[],
        metavar="NAME=VALUE",
        help="Secret to set. Use @/path to read value from file. Repeat for multiple.",
    )
    p.add_argument(
        "--config",
        type=Path,
        help="JSON file with {secrets: {NAME: VALUE_OR_@path}}. Merged with --secret (CLI wins).",
    )
    p.add_argument(
        "--force-ip",
        metavar="IP",
        help="Override the IP used for api.github.com (default: 140.82.112.5). "
        "Use 140.82.112.4 as fallback if one is blocked.",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be set, don't actually write.",
    )
    return p.parse_args()


def load_secrets(args: argparse.Namespace) -> dict[str, str]:
    """Merge --config + --secret (CLI wins). Resolve @file references."""
    secrets: dict[str, str] = {}

    if args.config:
        cfg = json.loads(args.config.read_text())
        cfg_secrets = cfg.get("secrets", cfg)  # accept either {secrets: {...}} or flat dict
        for k, v in cfg_secrets.items():
            secrets[k] = _resolve_value(v)

    for spec in args.secret:
        if "=" not in spec:
            print(f"WARN: ignoring malformed --secret '{spec}' (expected NAME=VALUE)", file=sys.stderr)
            continue
        name, _, raw = spec.partition("=")
        secrets[name.strip()] = _resolve_value(raw)

    return secrets


def _resolve_value(raw: str) -> str:
    """If value starts with @, read file content; else return raw."""
    raw = raw.strip()
    if raw.startswith("@"):
        return Path(os.path.expanduser(raw[1:])).read_text()
    return raw


# === API calls ===
def get_public_key(repo: str, headers: dict) -> tuple[str, str]:
    r = requests.get(
        f"{API_BASE}/repos/{repo}/actions/secrets/public-key",
        headers=headers,
        timeout=30,
    )
    r.raise_for_status()
    data = r.json()
    return data["key_id"], data["key"]


def encrypt(public_key_b64: str, value: str) -> str:
    pk_bytes = base64.b64decode(public_key_b64)
    pk = PublicKey(pk_bytes)
    box = SealedBox(pk)
    return base64.b64encode(box.encrypt(value.encode("utf-8"))).decode("utf-8")


def set_secret(repo: str, name: str, value: str, headers: dict, dry_run: bool = False) -> bool:
    if dry_run:
        preview = value if len(value) < 40 else f"{value[:20]}...({len(value)} chars)"
        print(f"  [dry-run] {name} = {preview}")
        return True

    key_id, pub_key = get_public_key(repo, headers)
    encrypted = encrypt(pub_key, value)
    r = requests.put(
        f"{API_BASE}/repos/{repo}/actions/secrets/{name}",
        headers=headers,
        json={"encrypted_value": encrypted, "key_id": key_id},
        timeout=30,
    )
    if r.status_code in (201, 204):
        print(f"  ✓ {name}")
        return True
    print(f"  ✗ {name}: HTTP {r.status_code} {r.text[:200]}", file=sys.stderr)
    return False


def main() -> int:
    args = parse_args()

    if not args.token:
        print("ERROR: --token (or env GH_TOKEN) required", file=sys.stderr)
        return 2

    if args.force_ip:
        os.environ["GH_API_IP"] = args.force_ip
        # Re-apply patch with new IP
        socket.getaddrinfo = _patched_getaddrinfo

    headers = {
        "Authorization": f"Bearer {args.token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    secrets = load_secrets(args)
    if not secrets:
        print("ERROR: no secrets provided (use --secret or --config)", file=sys.stderr)
        return 2

    print(f"[gh-secrets-setter] repo={args.repo}  count={len(secrets)}  dry_run={args.dry_run}")
    ok = all(set_secret(args.repo, n, v, headers, args.dry_run) for n, v in secrets.items())
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
