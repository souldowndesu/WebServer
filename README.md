# 服务器工作控制台

服务器有两个相互隔离的版本管理工作区：`/root/ai-workspaces/agent-1` 和 `/root/ai-workspaces/agent-2`。两个工作区分别使用同名分支，通过 PR 合并到 `main`；任何 agent 都不能直接修改另一个工作区。

每个工作区还拥有独立的租约、loopback 开发端口、`.runtime` 数据目录和 Compose 命名空间。正式服务只使用审核后的 `main` 部署副本，不读取开发工作区。完整设计见 `docs/two-agent-runtime.md`。

操作者本机的 `ssh-local` 目录不另建产品 Git 仓库，只负责通过本机 SSH 管理服务器、保存文档镜像、缓存外部下载和记录状态。

## 连接测试应用

仓库内包含一个不依赖第三方包的 Python 服务：

- / 显示居中的浏览器本地时间和实时聊天室。
- GET /api/health 返回服务时间和状态。
- GET /api/messages?after=0 返回内存中的消息。
- POST /api/messages 接收 JSON：{"author":"昵称","text":"内容"}。
- GET /api/events?after=0 使用 Server-Sent Events 推送新消息。

开发运行：

~~~sh
cd /root/ai-workspaces/agent-1
python3 tools/workspace_runtime.py claim --session chat-preview --task "chat preview"
python3 tools/workspace_runtime.py run --session chat-preview chat -- \
  python3 -m chat_app.server --host {host} --port {port}
~~~

Agent 1 的聊天预览端口是 18761，Agent 2 是 18861。TCP 8765 只属于正式部署，开发进程不得占用。

自动化验证：

~~~sh
python3 -m unittest discover -s tests -v
~~~

本地终端工具可交互聊天：

~~~powershell
python client/chat_cli.py --url http://SERVER_ADDRESS:8765 --name 本地工具
~~~

也可只发送一条消息：

~~~powershell
python client/chat_cli.py --url http://SERVER_ADDRESS:8765 --message "本地端口测试"
~~~

消息最多保留最近 200 条，仅存在服务器进程内存里，重启服务会清空。这个应用用于临时连通性测试，不应存放敏感信息。

### API 示例

~~~sh
curl -X POST http://SERVER_ADDRESS:8765/api/messages -H 'Content-Type: application/json' -d '{"author":"tool","text":"hello from local"}'
~~~

成功时返回 HTTP 201 和创建后的消息。输入为空、类型错误或超过昵称 40 字/消息 500 字时返回 HTTP 400。

## Mihomo 代理控制页

`proxy_control` 提供只依赖 Python 标准库的本机控制页，可查看运行状态、切换 `rule`/`global`/`direct` 模式、选择 AUTO 或具体节点、搜索节点和刷新订阅。页面只返回节点名称、协议、状态与延迟，不返回订阅或节点凭据。

开发运行：

~~~sh
cd /root/ai-workspaces/agent-1
python3 tools/workspace_runtime.py claim --session proxy-preview --task "proxy control preview"
python3 tools/workspace_runtime.py run --session proxy-preview proxy-control -- \
  python3 -m proxy_control.server --host {host} --port {port} \
  --socket /run/mihomo/controller.sock
~~~

Agent 1 的控制页预览端口是 18762，Agent 2 是 18862。TCP 8790 只属于 `/opt/proxy-control` 中的正式部署副本。

从操作者本机建立 SSH 隧道：

~~~powershell
ssh -N -L 8790:127.0.0.1:8790 aliyun-server
~~~

保持该窗口运行，然后在浏览器访问 `http://127.0.0.1:8790`。控制页不应绑定公网地址，也不需要新增 UFW 规则。

控制 API 只接受 loopback Host、同源 Origin 和 JSON 请求。状态接口会对 Mihomo 返回进行字段白名单处理，隐藏原始配置、订阅地址、节点服务器和密码。

## 最简单的指令

在本目录打开 PowerShell：

```powershell
.\server.ps1 status
.\server.ps1 progress
.\server.ps1 git
.\server.ps1 push
.\server.ps1 prs
.\server.ps1 connect
.\server.ps1 workspace
```

- `status`：观察服务器并把快照保存到 `state/SERVER_STATUS.md`。
- `progress`：先从服务器同步文档，再显示 `STATUS.md` 和 `TASKS.md`。
- `git`：查看服务器端 `agent-1` 分支、工作树和最近提交。
- `push`：服务器到 GitHub 不稳定时，通过本机网络安全推送 `agent-1`；token 不保存到本机。
- `prs`：查看该仓库的开放 PR。
- `connect`：进入服务器交互终端。
- `workspace`：查看 agent-1 当前租约、分支、工作树和开发端口分配。

外部文件必须先下载到本机，再上传服务器：

```powershell
.\server.ps1 download https://example.com/tool.tar.gz
.\server.ps1 upload tool.tar.gz
```

默认上传目录是服务器的 `/root/ai-workspaces/agent-1/.cache/uploads/`。脚本只允许从本地 `downloads/` 上传，并在下载后显示 SHA-256。

## 对 agent 的短指令

以后可以直接说：

- “连接服务器”
- “看服务器状态”
- “看/同步工作进度”
- “把这个地址下载到本机再上传”
- “检查 Git 和 PR”
- “通过本机推送这一轮”
- “提交这一轮并提 PR”

agent 应加载 `skills/server-workspace-ops/SKILL.md` 并遵守 `AGENTS.md`，不再重新摸索路径、凭据入口和协作边界。

## 文件说明

- `AGENTS.md`：不可绕过的工作范围与版本管理规则。
- `OPERATIONS.md`：登录、观察、下载上传、GitHub 和故障处理手册。
- `COORDINATION.md`：分支、PR、环境变更和跨工作区协作规范。
- `STATUS.md`、`TASKS.md`：服务器端工作进程的本地一致副本；不要在本地单独编辑。
- `ENVIRONMENT_CHANGES.md`：服务器环境及工作区外变更台账。
- `config/workspace-runtime.json`：两个 agent 的端口、分支和运行命名空间登记表。
- `tools/workspace_runtime.py`：工作区租约、预检、环境注入和严格端口启动工具。
- `downloads/`：外部文件的本地下载缓存。
- `state/SERVER_STATUS.md`：最近一次服务器状态快照。

SSH 使用本机现有别名 `aliyun-server`。密钥和 GitHub token 仅保留在各自受保护位置，不复制到本目录。
