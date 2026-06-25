# gh-secrets-setter

跨项目可复用的 GitHub Actions secrets 写入工具,核心特性:

1. **WSL DNS 兼容**:自动绕过 `api.github.com → 127.0.0.1` 劫持
2. **libsodium sealed_box 加密**:GitHub 现行的加密方式(X25519 + XSalsa20-Poly1305),不是老 RSA
3. **纯 stdlib + 2 deps**:无 gh CLI 依赖,无 git 依赖,任何 Python 3.10+ 都能跑

## 安装

```bash
pip install -r requirements.txt
```

## 最简用法(单 secret)

```bash
python set_gh_secrets.py \
  --repo AndyWongWithAI/industry-value-flow \
  --token ghp_xxxxxxxx \
  --secret SSH_USER=root
```

## 多 secret + SSH 私钥从文件读

```bash
python set_gh_secrets.py \
  --repo AndyWongWithAI/industry-value-flow \
  --token ghp_xxxxxxxx \
  --secret SSH_USER=root \
  --secret 'SSH_KEY=@~/.ssh/github_actions_arch_platform' \
  --secret ARCH_API_KEY=abc123def
```

`@/path` 前缀会自动读文件内容(用于 SSH 私钥这种带换行的长内容)。

## 配置文件模式(JSON)

```json
// secrets.json
{
  "secrets": {
    "SSH_USER": "root",
    "SSH_KEY": "@~/.ssh/github_actions_arch_platform",
    "ARCH_API_KEY": "abc123def"
  }
}
```

```bash
python set_gh_secrets.py \
  --repo OWNER/REPO \
  --token ghp_xxx \
  --config secrets.json
```

`--config` 和 `--secret` 可以混用,CLI 的 `--secret` 优先级更高。

## Token 来源

按优先级:
1. `--token ghp_xxx` 参数
2. `GH_TOKEN` 环境变量

不要把 token 写在命令行历史里,推荐:
```bash
export GH_TOKEN=$(cat ~/.config/gh/hosts.yml | grep oauth_token | cut -d' ' -f3)
python set_gh_secrets.py --repo OWNER/REPO --secret FOO=bar
```

## 为什么 gh CLI 不行

WSL 下:
- `gh secret set` → 调用 `api.github.com` → DNS 解析为 127.0.0.1 → 连接失败
- WSL2 的 `/etc/resolv.conf` 指向一个把 GitHub 域名解析到本机的 DNS

本工具在 `socket.getaddrinfo` 层劫持 `api.github.com` → 真实 IP(140.82.112.5),绕开 DNS 解析。
非 WSL 环境(普通 Linux/Mac)上同样工作,只是 patch 不会触发实际差异。

## 强制使用指定 IP(可选)

如果默认 IP(140.82.112.5)被防火墙拦了,可以用 `--force-ip 140.82.112.4` 切到备用 IP。

## 退出码

| Code | 含义 |
|------|------|
| 0 | 全部 secret 写入成功 |
| 1 | 至少一个 secret 失败 |
| 2 | 参数错误(token 缺失、没 secret 等)|

## 局限

- **不写 org-level secrets**:仅 repo-level
- **不删除 secrets**:GitHub API PUT 不支持删除,需要 UI 或 `gh secret remove`
- **不轮转**:如需定期轮转,加 cron + 本脚本即可
- **不验证值正确性**:它只加密 + 推送,不验证 SSH key 是否合法、API key 是否有效

## 关联

- SDLC SOP §Phase 6.0.2: 必设 GH Secrets 3 个
- arch 平台 component: `gh-secrets-setter` (L1_platform, tool)
- 来源: industry-value-flow 部署经验(2026-06-25)
