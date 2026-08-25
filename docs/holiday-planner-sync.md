# IrohaWalendar 桌面同步

网页规划页是只读视图。唯一写入源是电脑端 IrohaWalendar 3.5；适配器从桌面应用的本机 API 读取 v5 状态，再通过当前账号的一次性设备令牌上传服务器。

## 1. 开启桌面接口

在 IrohaWalendar 的“设置 → 本机 API”中开启接口，保留默认回环地址 `127.0.0.1:17321`，生成或复制本机 API 令牌。接口不应监听局域网或公网地址。

## 2. 创建网页设备

登录管理网页，进入“个人设置 → 桌面同步设备”，选择“添加设备”。复制只显示一次的 `planner_sync` 令牌。该令牌只属于当前账号；服务器只保存摘要，可随时在同一页面撤销。

## 3. 建立 SSH 隧道

开发预览只监听服务器回环端口。在 Windows PowerShell 中保持以下命令运行：

```powershell
ssh -N -L 18761:127.0.0.1:18761 aliyun-server
```

正式 HTTPS 部署时，将后续命令的 `-ServerUrl` 改成正式站点，不再使用 SSH 隧道。

## 4. 启动适配器

在本仓库根目录执行：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\tools\holiday-planner-sync.ps1
```

脚本依次无回显询问 IrohaWalendar 本机 API 令牌和网页设备令牌。首次启动立即同步，之后默认每 5 秒检查一次，只在过滤后的规划内容变化时上传。按 `Ctrl+C` 停止。只同步一次可加 `-Once`：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\tools\holiday-planner-sync.ps1 -Once
```

非默认地址可显式设置：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\tools\holiday-planner-sync.ps1 `
  -DesktopUrl http://127.0.0.1:17321 `
  -ServerUrl http://127.0.0.1:18761 `
  -IntervalSeconds 5
```

脚本拒绝把令牌发送到非本机的明文 HTTP 地址。桌面状态中的 `apiToken`、`apiPort`、API 开关、快捷键、焦点日期和侧栏宽度在发出请求前即被剔除；服务器还会再次执行同一白名单过滤。令牌不写入脚本状态文件或日志。

## 5. 验证与撤销

网页规划页点击“刷新”，应看到新的 revision、服务器接收时间和桌面中的目标、行动、日常规划、日/周/月及统计内容。若不再使用该电脑，在“个人设置”撤销设备；适配器之后会收到未授权响应且无法继续上传。

常见问题：

- 桌面连接失败：确认 IrohaWalendar 正在运行、本机 API 已开启、端口和本机令牌一致。
- 服务器连接失败：确认 SSH 隧道仍在运行，且预览端口为工作区注册的 `18761`。
- 上传被拒绝：重新创建网页设备令牌；旧令牌不会被服务器读回。
- 网页内容未变化：点击网页顶部“刷新”，并查看适配器终端是否出现新的 revision。
