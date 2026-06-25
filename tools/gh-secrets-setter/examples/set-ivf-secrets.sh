#!/bin/bash
# examples/set-ivf-secrets.sh — 给 industry-value-flow 写部署 secrets 的 wrapper
# 用法:确保 secrets.json 在 ~/.claude/ 下,然后直接跑

set -euo pipefail

REPO="AndyWongWithAI/industry-value-flow"
SECRETS_JSON="${HOME}/.claude/secrets.json"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOOL_DIR="$(dirname "$SCRIPT_DIR")"

if [[ ! -f "$SECRETS_JSON" ]]; then
  echo "ERROR: $SECRETS_JSON not found" >&2
  exit 1
fi

# 从 secrets.json 读 token 和 arch api key
TOKEN=$(python3 -c "import json; print(json.load(open('$SECRETS_JSON'))['github_cli_pat']['token'])")
ARCH_KEY=$(python3 -c "import json; print(json.load(open('$SECRETS_JSON'))['architecture_blueprint']['architecture_api_key'])")

python3 "$TOOL_DIR/set_gh_secrets.py" \
  --repo "$REPO" \
  --token "$TOKEN" \
  --secret SSH_USER=root \
  --secret "SSH_KEY=@${HOME}/.ssh/github_actions_arch_platform" \
  --secret "ARCH_API_KEY=${ARCH_KEY}"

echo ""
echo "✓ All secrets set for $REPO"
