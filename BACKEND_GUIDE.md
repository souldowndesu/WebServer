# 后端位置与接入指引

这份文件是仓库根目录的具体位置索引。正式交互和视觉层由后续前端 AI 实现；不要把本次本地 QA 界面复制进产品提交。

## 代码位置

| 位置 | 责任 |
| --- | --- |
| `control_plane/server.py` | HTTP 路由、会话/CSRF/同源检查、角色授权和安全响应头 |
| `control_plane/storage.py` | 同级账号目录、scrypt 身份哈希、资料、设置、备注、会话、设备、日历和博客文件 |
| `control_plane/shared.py` | 连接申请、受限消息、推理任务、监控端租约和博客审核的 SQLite 事务 |
| `control_plane/planner.py` | IrohaWalendar v5 快照、数量/大小限制和本机敏感设置过滤 |
| `control_plane/proxy.py` | Mihomo Unix socket 白名单适配；不返回服务器、端口、密码或订阅信息 |
| `control_plane/blog.py` | 结构化图文博客、32 MiB 配额、自定义 HTML 校验和管理员审核发布 |
| `control_plane/security.py` | 密码、随机令牌、图像、JSON 深度和通用输入约束 |
| `control_plane/cli.py` | 空账号池的唯一初始管理员安全引导 |
| `tests/test_control_plane.py` | 认证、隔离、同步、通讯、容量、博客、代理、CSRF 和推理队列验收 |

## 数据目录

`--data-root` 或工作区注入的 `APP_DATA_DIR` 是唯一数据根。账号目录相互并列；账号身份与该账号的相关数据位于同一个目录：

```text
data/
├─ accounts/
│  ├─ index.json                     # 只保存规范化账号名到随机 id 的索引，不含密码哈希
│  ├─ <account-id>/                  # 每个账号目录彼此并列，0700
│  │  ├─ identity.json               # 账号名、角色、状态、scrypt 盐和哈希
│  │  ├─ profile.json                # 昵称、头像引用
│  │  ├─ settings.json               # 该账号自己的界面/代理偏好
│  │  ├─ social.json                 # 该账号对其他人的私人备注
│  │  ├─ sessions.json               # 有时限且只存摘要的登录会话
│  │  ├─ devices.json                # 可撤销且只存摘要的桌面同步令牌
│  │  ├─ planner.json                # 最新只读网页快照
│  │  ├─ avatars/
│  │  └─ blog/{assets,drafts,published}/
│  └─ <another-account-id>/
└─ shared/
   └─ platform.sqlite3               # 双方关系、消息、审核、任务和工作租约
```

所有敏感 JSON 文件使用 0600；密码、会话令牌、设备令牌和监控端令牌的原文均不落盘。跨账号数据必须进入 `shared/platform.sqlite3`，不能随意复制进某个账号目录制造所有权歧义。

## 初始管理员与账号管理

空数据根只允许执行一次：

```sh
python3 -m control_plane.cli --data-root /safe/private/data init-admin --username admin
```

命令默认用无回显方式输入并确认密码。不得在命令行参数、环境日志、Git、PR 或聊天中放密码。初始化后，管理员通过 `/api/v1/admin/accounts` 创建账号，通过账号更新接口停用/恢复或变更角色，通过 password 子路由设置新密码；API 永远不返回旧密码或新密码。系统拒绝停用或降级最后一个可用管理员。

账号不做在线物理删除。停用会立即清空该账号会话，但保留数据以便审计和恢复；未来若需要永久清除，必须设计单独的导出、冷静期和双重确认流程。

## 运行与安全边界

开发进程只能通过工作区运行器绑定分配的 `127.0.0.1` 端口。无 TLS 时通过 SSH 隧道使用。真正公开登录前必须先完成独立环境变更：HTTPS 反向代理、可信 Host、Secure Cookie、持久服务账号、只读代码部署和私有可写数据目录。

```sh
python3 tools/workspace_runtime.py run \
  --session <active-session> control-plane -- \
  python3 -m control_plane.server --host {host} --port {port} --data-root "$APP_DATA_DIR"
```

生产 HTTPS 部署应增加 `--secure-cookie`。不允许让 systemd 从 agent-1 或 agent-2 工作区运行，也不允许继续使用旧的公网明文 TCP 8765 登录。

## IrohaWalendar 只读同步

网页版使用登录会话执行 `GET /api/v1/planner/snapshot`，没有会话写入口。用户在“同步设备”中创建 `planner_sync` 令牌；原文只返回一次，电脑端用 `Authorization: Device <token>` 执行 `PUT /api/v1/planner/snapshot`。

快照沿用 v5 的 `goals`、`actions`、`routineCategories`、`routines`、`plans` 和 `completionRecords`，同时加入严格递增的 `revision` 与 `source_updated_at`。服务端只保留跨设备有意义的日历设置；`apiToken`、`apiPort`、本机 API 开关、快捷键、当前焦点日期和侧栏宽度不会同步。每个账号独立保存 12 MiB 以内的最新快照。

桌面应用后续需要增加一个适配器：状态原子保存成功后，递增 revision 并向这个端点上传；失败写入本地 outbox 重试，不能阻塞本地保存。设备令牌可在网页列出和撤销。

## 通讯与容量决定

只有处于 `connected` 的两个账号能够读取或发送双方消息；管理员不获得旁路读取权限。当前只接受 4000 字以内文本，不接受聊天附件。

容量硬限制：

- 单会话最多 10,000 条或 16 MiB文本；
- 单账号参与的全部会话最多 64 MiB文本；
- 全站消息文本最多 512 MiB；
- 最长保留 365 天；
- SQLite WAL 限制为 16 MiB，并自动 checkpoint；
- 服务启动及每次发消息都会从最旧记录开始回收，SQLite 使用增量 vacuum。

这些限制把消息正文和日志增长控制在可预测范围。SQLite 页、索引和 WAL 有少量额外开销，因此实际磁盘预算应为约 650 MiB，而不是精确 512 MiB。若将来开放聊天附件，必须建立独立对象存储配额，不能塞进 SQLite 或 data URL。

## 博客审核边界

结构化博客允许文本和 PNG/JPEG/WebP 图片，经过大小、签名和路径验证后直接发布。每账号博客总额 32 MiB。

自定义网页先保存为草稿并进入管理员审核。即使审核通过也禁止脚本、iframe、表单、外链、事件属性、CSS 外部 URL 和可执行表达式；发布页使用独立 CSP sandbox、禁止网络连接和表单提交。未来如果必须允许 JavaScript，必须改为不同站点/不同 cookie 域、隔离对象存储、恶意内容扫描和人工审核，不能放宽当前同源沙箱。

## 推理任务端

网页创建任务时提交指令、优先级和参数白名单。服务器不执行推理。管理员为电脑监控程序创建 Worker token；监控程序领取一个任务后获得短期租约，通过进度接口续租并通过完成接口回传 JSON 结果。租约过期的任务重新排队，错误 worker 或旧租约不能写入。

参数不允许包含文件路径、shell 命令、URL、密码、token 或凭据字段；监控端仍必须把任务看作不可信输入，在独立用户/容器中执行，并自行白名单模型和资源上限。

## 验收命令

```sh
python3 -m compileall -q control_plane tests
python3 -m unittest discover -s tests -v
```

不得把真实账号数据、设备令牌、Worker token、博客草稿、推理输出或本地 QA UI 提交到 Git。
