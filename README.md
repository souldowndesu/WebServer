# WebServer 认证管理后台

本仓库的产品入口是 `control_plane`：一个多账号管理 API，以及位于 `control_plane/ui/` 的已验收基础界面模板。原来的浏览器时钟、匿名聊天室、终端聊天客户端和独立代理页面已经从产品源码移除；代理能力已整合为仅管理员可见的服务器全局模块。

从 [BACKEND_GUIDE.md](BACKEND_GUIDE.md) 开始。它给出代码位置、初始管理员、数据目录、运行测试、桌面同步和监控端接入的具体路径。IrohaWalendar 实际同步步骤见 [docs/holiday-planner-sync.md](docs/holiday-planner-sync.md)，可运行脚本位于 [tools/holiday-planner-sync.ps1](tools/holiday-planner-sync.ps1)。系统设计见 [docs/platform-architecture.md](docs/platform-architecture.md)，HTTP 契约见 [docs/api-v1.md](docs/api-v1.md)，前端 AI 的实现说明见 [docs/frontend-handoff.md](docs/frontend-handoff.md)。

## 当前边界

- 后端、数据隔离、权限、容量治理和 API 已实现并接受自动化测试。
- `control_plane/ui/` 是本轮验收后提升为可部署基线的临时模板，不代表最终交互或美术；后续前端 AI 可按交接契约整体替换。
- 未配置 HTTPS 时只允许通过 SSH 隧道访问开发服务，不能在公网 HTTP 上输入账号密码。公网部署使用受信任证书的 `https://公网 IP`，应用本身仍只监听 loopback。
- 正式服务只能由审核后的 `main` 部署副本运行；工作区预览使用分配给 agent-1 的 loopback 端口。

## 开发预览

```sh
cd /root/ai-workspaces/agent-1
python3 tools/workspace_runtime.py run \
  --session <active-session> control-plane -- \
  python3 -m control_plane.server --host {host} --port {port} \
    --data-root "$APP_DATA_DIR" --ui-root control_plane/ui
```

未传 `--ui-root` 时，根路径只返回 API 元数据。工作区测试通过 SSH 隧道访问，agent-1 预览端口由 `config/workspace-runtime.json` 固定为 `18761`：

```sh
ssh -N -L 18761:127.0.0.1:18761 aliyun-server
# 浏览器打开 http://127.0.0.1:18761
```

工作区预览使用现有服务器的多工作区租约机制，只占用 `agent-1` 已登记的独立 loopback 端口，不创建外部云服务，也不开放公网端口。使用结束后应停止前台预览，并执行 `python3 tools/workspace_runtime.py release --session <active-session>` 归还工作区租约与测试端口。单部署区版本必须另走环境变更，从已审核的 `main` 安装只读代码和模板；没有 HTTPS 时仍只允许通过 SSH 隧道访问。公网 IP HTTPS 由本机反向代理终止 TLS，只把请求转发到 `127.0.0.1:8790`，不得直接公开应用端口。

初始化空数据目录中的唯一管理员时，不在命令行参数、Git 或日志中传入密码：

```sh
python3 -m control_plane.cli --data-root "$APP_DATA_DIR" init-admin --username admin
```

测试：

```sh
python3 -m unittest discover -s tests -v
```

服务器工作区、租约、PR 和环境变更规则仍以 `AGENTS.md`、`OPERATIONS.md`、`COORDINATION.md` 和 `ENVIRONMENT_CHANGES.md` 为准。
