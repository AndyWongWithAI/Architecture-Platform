---
name: user-auth-jwt
title: JWT 用户认证库
positioning: "L2 业务能力层的无状态用户认证库,基于 JWT + 刷新令牌,适用于 FastAPI / Flask Web 服务。新 Web 项目首选认证组件,跨项目复用。"
layer: L2_capability
category: auth
scope: lib
atomic: true
composed_of: []
tags: [jwt, auth, refresh-token, fastapi, oauth]
language: python
package_name: "arch-component-user-auth-jwt"
install_command: "pip install arch-component-user-auth-jwt"
usage_example: "from arch_component_user_auth_jwt import AuthService; auth = AuthService(secret_key='xxx')"
status: draft
repo_url: ""
is_asset: true
distribution_form: package
interface_contract: ""
knowledge_artifact: false
---

## 定位

L2 业务能力层。**架构平台的"目标组件"** — 计划发到 GitHub Packages,作为跨项目复用的范例。

## 设计意图

CLAUDE.md 复用原则 + 资产原则:
- **可复用**:任何 FastAPI 项目 `pip install` 即可用
- **可迁移**:纯 Python 标准库依赖,无平台绑定
- **状态不敏感**:不存用户会话(只校验 token),重启不影响

## 计划 API

```python
from arch_component_user_auth_jwt import AuthService, User, Token

auth = AuthService(secret_key="...", access_token_expire_minutes=15)

# 签发
token: Token = auth.create_access_token(user_id="alice", scopes=["read", "write"])

# 校验
user: User = auth.verify_token(token.access_token)
```

## 备注

- 当前为 draft(占位),实际代码未实现
- Phase 5 演示用:登记在架构平台后,后续 L3 项目可引用
- 上层(composition)示例:user-management-service 可 composed_of 引用