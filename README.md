# WebServer 认证管理后台

本仓库的产品入口是 `control_plane`：一个不捆绑正式前端的多账号管理 API。原来的浏览器时钟、匿名聊天室、终端聊天客户端和独立代理页面已经从产品源码移除；代理能力已整合到登录后的管理模块。

从 [BACKEND_GUIDE.md](BACKEND_GUIDE.md) 开始。它给出代码位置、初始管理员、数据目录、运行测试、桌面同步和监控端接入的具体路径。系统设计见 [docs/platform-architecture.md](docs/platform-architecture.md)，HTTP 契约见 [docs/api-v1.md](docs/api-v1.md)，前端 AI 的实现说明见 [docs/frontend-handoff.md](docs/frontend-handoff.md)。

## 当前边界

- 后端、数据隔离、权限、容量治理和 API 已实现并接受自动化测试。
- 正式 UI 不在仓库中；本次仅在操作者本地使用测试 UI 做基础视觉验证。
- 未配置 HTTPS 时只允许通过 SSH 隧道访问开发服务，不能在公网 HTTP 上输入账号密码。
- 正式服务只能由审核后的 `main` 部署副本运行；工作区预览使用分配给 agent-1 的 loopback 端口。

## 开发预览

```sh
cd /root/ai-workspaces/agent-1
python3 tools/workspace_runtime.py run \
  --session codex-account-platform-20260824 control-plane -- \
  python3 -m control_plane.server --host {host} --port {port} --data-root "$APP_DATA_DIR"
```

初始化空数据目录中的唯一管理员时，不在命令行参数、Git 或日志中传入密码：

```sh
python3 -m control_plane.cli --data-root "$APP_DATA_DIR" init-admin --username admin
```

测试：

```sh
python3 -m unittest discover -s tests -v
```

服务器工作区、租约、PR 和环境变更规则仍以 `AGENTS.md`、`OPERATIONS.md`、`COORDINATION.md` 和 `ENVIRONMENT_CHANGES.md` 为准。
