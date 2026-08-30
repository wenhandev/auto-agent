# 08 · 部署与运维

生产：**仅控制面**。浏览器与 LLM 执行在用户桌面 Client。

参考环境：`https://rpa.wenhandev.com`（GCP `auto-agent-500007` / VM `auto-agent-rpa`）。

## 1. 架构

```
Internet
    │
    ▼
Caddy (TLS Let's Encrypt, 静态 /downloads)
    │
    ▼
FastAPI uvicorn :8000  +  Admin SPA (/srv/frontend)
    │
    ▼
SQLite volume (/app/data)
```

`EXECUTION_BACKEND=control_plane_only` — 镜像内**不安装** Playwright 浏览器。

---

## 2. 关键文件

| 路径 | 说明 |
|------|------|
| `deploy/Dockerfile` | 多阶段：frontend build → backend slim |
| `deploy/docker-compose.yml` | `app` + `caddy` |
| `deploy/Caddyfile` | 反代 + `/downloads` |
| `deploy/.env.production.example` | 环境变量模板 |
| `deploy/entrypoint.sh` | 启动 uvicorn（proxy-headers） |
| `deploy/bootstrap-server.sh` | 服务器一键引导 |
| `deploy/publish-client-downloads.sh` | 上传安装包到 VM |

---

## 3. 环境变量（必填/关键）

| 变量 | 用途 |
|------|------|
| `EXECUTION_BACKEND` | 必须 `control_plane_only` |
| `SESSION_SECRET` | Cookie/会话签名 |
| `ADMIN_EMAIL` / `ADMIN_PASSWORD` | Bootstrap 管理员 |
| `OAUTH_CALLBACK_BASE` / `FRONTEND_BASE_URL` | OAuth 与前端源 |
| `DESKTOP_CLIENT_BASE_URL` | 桌面 OAuth 回调（默认 `http://127.0.0.1:8745`） |
| `CORS_ORIGINS` | 生产域 |
| `OAUTH_SIGNUP_POLICY` / `OAUTH_ALLOWED_EMAIL_DOMAINS` | Google 登录开通策略 |
| `DOMAIN` / `ACME_EMAIL` | Caddy TLS |
| `DATABASE_URL` | Compose 内 `sqlite:////app/data/auto_agent.db` |

---

## 4. 部署步骤

```bash
git clone <repo> /opt/auto-agent
cd /opt/auto-agent/deploy
cp .env.production.example .env   # 编辑密钥与管理员密码
chmod +x bootstrap-server.sh entrypoint.sh
sudo ./bootstrap-server.sh
```

或：`docker compose build && docker compose up -d`。

健康检查：`curl -fsS https://<domain>/api/health`

更新：

```bash
cd /opt/auto-agent && git pull
cd deploy && docker compose build --pull && docker compose up -d
```

---

## 5. 客户端安装包

Caddy 静态目录 `/downloads/`：

| 平台 | URL 示例 |
|------|----------|
| macOS | `/downloads/Auto-Agent-Client-macos.dmg` |
| Windows | `/downloads/Auto-Agent-Client-windows.msi` |
| Linux | `/downloads/Auto-Agent-Client-linux.AppImage` |

发布流程：

1. Tag `client-v*` → GitHub Actions **Release client**
2. 上传到 VM（`publish-client-downloads.sh` 或 CI + `GCP_SA_KEY`）
3. Web `/client` 页指向这些 URL

Client 构建需烘焙：`VITE_CLOUD_URL=https://rpa.wenhandev.com`。  
**Release 包不得**再 spawn 本地 cloud `:8001`。

---

## 6. 运维检查清单

| 问题 | 排查 |
|------|------|
| 证书 pending | DNS、80 端口 |
| 502 | `docker compose logs app` |
| 桌面登录失败 | Cloud URL 无尾斜杠；CORS |
| OAuth `account_not_provisioned` | 域白名单 / Admin 规则 |
| Worker 一直 pending | Settings → Workers 审批 |

数据持久化：Docker volume `app_data`（SQLite + Fernet 密钥）。

下一章：[09 · SDK 与 MCP](./09-sdk-mcp.md)
