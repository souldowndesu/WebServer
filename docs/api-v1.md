# Management API v1

所有 JSON 修改请求使用 `Content-Type: application/json`。错误形状为 `{"error":{"code":"...","message":"..."}}`。正式浏览器使用 HttpOnly cookie 与 `X-CSRF-Token`；受控 API 调试可以使用 `Authorization: Bearer <session>`。

## 认证与用户

| 方法 | 路径 | 权限 | 说明 |
| --- | --- | --- | --- |
| GET | `/api/v1/health` | 公共 | 健康、初始化状态和消息配额 |
| POST | `/api/v1/auth/login` | 公共 | 账号密码登录；返回会话与 CSRF，设置 cookie |
| POST | `/api/v1/auth/logout` | 登录 | 撤销当前会话 |
| GET | `/api/v1/me` | 登录 | 当前资料与独立设置 |
| PATCH | `/api/v1/me/profile` | 登录 | 昵称与头像 data URL |
| PATCH | `/api/v1/me/settings` | 登录 | 主题和语言；代理不属于个人设置 |
| GET | `/api/v1/users` | 登录 | 可见账号、私人备注和连接状态 |
| PUT | `/api/v1/users/{id}/remark` | 登录 | 设置自己对目标账号的备注 |
| GET | `/api/v1/users/{id}/avatar` | 登录 | 读取头像 |

## 管理员账号池

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET/POST | `/api/v1/admin/accounts` | 列表或创建账号 |
| PATCH | `/api/v1/admin/accounts/{id}` | `disabled`、`role` |
| POST | `/api/v1/admin/accounts/{id}/password` | 设置新密码并清空该账号会话 |

密码字段只可写，不可读。最后一个可用管理员不能被停用或降级。

## 日历同步

| 方法 | 路径 | 权限 | 说明 |
| --- | --- | --- | --- |
| GET/POST | `/api/v1/me/devices` | 登录 | 列出或创建同步令牌；原文只在创建响应出现 |
| DELETE | `/api/v1/me/devices/{id}` | 登录 | 撤销令牌 |
| GET | `/api/v1/planner/snapshot` | 登录 | 网页只读快照 |
| PUT | `/api/v1/planner/snapshot` | `Authorization: Device ...` | 桌面端写入递增 v5 快照 |

## 连接与通讯

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/v1/connections` | 当前申请与连接 |
| POST | `/api/v1/connections/requests` | `{"account_id":"..."}` |
| POST | `/api/v1/connections/{id}/accept` | 接收方接受 |
| POST | `/api/v1/connections/{id}/reject` | 接收方拒绝 |
| POST | `/api/v1/connections/{id}/cancel` | 发送方撤回 |
| GET | `/api/v1/conversations/{id}/messages?after=0&limit=100` | 已连接双方增量读取 |
| POST | `/api/v1/conversations/{id}/messages` | `{"text":"..."}`，最多 4000 字 |

## 博客

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| PUT | `/api/v1/blog/me` | 发布结构化 title/summary/blocks 图文博客 |
| POST | `/api/v1/blog/me/custom` | 上传自定义 HTML 草稿并进入审核 |
| GET | `/api/v1/blog/me/custom/reviews` | 查看自己的审核历史与备注，不返回 HTML |
| GET | `/api/v1/blogs/{id}` | 登录账号观察公开博客清单 |
| GET | `/api/v1/blogs/{id}/assets/{name}` | 登录账号读取结构化博客图片 |
| GET | `/blogs/{id}/custom/{revision}` | CSP sandbox 自定义页面 |
| GET | `/api/v1/admin/blog-reviews` | 管理员待审核列表 |
| POST | `/api/v1/admin/blog-reviews/{id}/{revision}` | `approved` / `rejected` 与备注 |

## 推理下达与监控端

| 方法 | 路径 | 权限 | 说明 |
| --- | --- | --- | --- |
| GET/POST | `/api/v1/inference/tasks` | 登录 | 列表或创建自己的任务 |
| GET | `/api/v1/inference/tasks/{id}` | 所有者 | 查看状态与结果 |
| POST | `/api/v1/inference/tasks/{id}/cancel` | 所有者 | 取消 queued/running |
| POST | `/api/v1/admin/workers` | 管理员 | 创建 Worker token，原文只返回一次 |
| POST | `/api/v1/workers/tasks/claim` | `Authorization: Worker ...` | 领取任务与短期 lease token |
| POST | `/api/v1/workers/tasks/{id}/progress` | Worker + lease | 进度与续租 |
| POST | `/api/v1/workers/tasks/{id}/complete` | Worker + lease | 成功 JSON 结果或错误 |

任务参数顶层允许 `model`、`adapter`、`temperature`、`top_p`、`max_tokens`、`seed`、`batch_size`、`precision`、`device` 和受限 `extra`。文件路径、命令、URL 与凭据类键被拒绝。

## 代理

| 方法 | 路径 | 权限 | 说明 |
| --- | --- | --- | --- |
| GET | `/api/v1/proxy/status` | 管理员 | 白名单状态、选择和节点延迟 |
| POST | `/api/v1/proxy/mode` | 管理员 | rule/global/direct |
| POST | `/api/v1/proxy/selection` | 管理员 | AUTO 或允许节点 |
| POST | `/api/v1/proxy/refresh` | 管理员 | 刷新 provider |
