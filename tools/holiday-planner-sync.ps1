[CmdletBinding()]
param(
    [string]$DesktopUrl = "http://127.0.0.1:17321",
    [string]$ServerUrl = "http://127.0.0.1:18761",
    [ValidateRange(2, 3600)]
    [int]$IntervalSeconds = 5,
    [ValidateRange(2, 120)]
    [int]$TimeoutSeconds = 15,
    [switch]$Once
)

$ErrorActionPreference = "Stop"

$listFields = @(
    "goals",
    "actions",
    "routineCategories",
    "routines",
    "plans",
    "completionRecords"
)
$syncedSettingFields = @(
    "theme",
    "statsPeriod",
    "statsMode",
    "calendarZoom",
    "dayStartMinute",
    "dayEndMinute",
    "timeDivisionMode",
    "timeDivisionInterval",
    "timeDivisionPoints",
    "calendarSelectionEnabled"
)

function Assert-Endpoint {
    param(
        [Parameter(Mandatory = $true)][string]$Value,
        [Parameter(Mandatory = $true)][string]$Label,
        [switch]$Desktop
    )

    try {
        $uri = [Uri]$Value
    }
    catch {
        throw "$Label 地址无效。"
    }
    if ($uri.Scheme -notin @("http", "https")) {
        throw "$Label 只允许 http 或 https。"
    }
    $isLoopback = $uri.IsLoopback
    if ($Desktop -and -not $isLoopback) {
        throw "IrohaWalendar 自动化接口必须使用本机回环地址。"
    }
    if ($uri.Scheme -eq "http" -and -not $isLoopback) {
        throw "$Label 的非本机地址必须使用 https，避免设备令牌明文传输。"
    }
    return $Value.TrimEnd("/")
}

function Read-SecretValue {
    param(
        [Parameter(Mandatory = $true)][string]$Prompt,
        [Parameter(Mandatory = $true)][string]$EnvironmentName
    )

    $fromEnvironment = [Environment]::GetEnvironmentVariable($EnvironmentName)
    if (-not [string]::IsNullOrWhiteSpace($fromEnvironment)) {
        return $fromEnvironment
    }
    $secure = Read-Host -Prompt $Prompt -AsSecureString
    $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    try {
        return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)
    }
    finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)
        $secure.Dispose()
    }
}

function Get-PropertyValue {
    param(
        [Parameter(Mandatory = $true)]$Object,
        [Parameter(Mandatory = $true)][string]$Name
    )

    $property = $Object.PSObject.Properties[$Name]
    if ($null -eq $property) {
        return $null
    }
    return $property.Value
}

function New-FilteredSnapshot {
    param(
        [Parameter(Mandatory = $true)]$State,
        [Parameter(Mandatory = $true)][long]$Revision
    )

    if ([int](Get-PropertyValue -Object $State -Name "version") -ne 5) {
        throw "桌面端状态不是受支持的 IrohaWalendar v5。"
    }
    $snapshot = [ordered]@{
        version = 5
        revision = $Revision
        source_updated_at = [DateTimeOffset]::UtcNow.ToString("yyyy-MM-ddTHH:mm:ss.fffZ")
    }
    foreach ($field in $listFields) {
        $property = $State.PSObject.Properties[$field]
        if ($null -eq $property) {
            throw "桌面端状态缺少 $field 列表。"
        }
        $snapshot[$field] = @($property.Value)
    }

    $settingsProperty = $State.PSObject.Properties["settings"]
    if ($null -eq $settingsProperty) {
        throw "桌面端状态缺少 settings。"
    }
    $settings = $settingsProperty.Value
    $safeSettings = [ordered]@{}
    foreach ($field in $syncedSettingFields) {
        $property = $settings.PSObject.Properties[$field]
        if ($null -ne $property) {
            $safeSettings[$field] = $property.Value
        }
    }
    $snapshot["settings"] = $safeSettings
    return $snapshot
}

function Get-SnapshotFingerprint {
    param([Parameter(Mandatory = $true)]$Snapshot)

    $content = [ordered]@{}
    foreach ($field in @("version") + $listFields + @("settings")) {
        $content[$field] = $Snapshot[$field]
    }
    $bytes = [Text.Encoding]::UTF8.GetBytes(($content | ConvertTo-Json -Depth 100 -Compress))
    $sha = [Security.Cryptography.SHA256]::Create()
    try {
        return ([BitConverter]::ToString($sha.ComputeHash($bytes))).Replace("-", "")
    }
    finally {
        $sha.Dispose()
    }
}

$desktopEndpoint = Assert-Endpoint -Value $DesktopUrl -Label "桌面端" -Desktop
$serverEndpoint = Assert-Endpoint -Value $ServerUrl -Label "服务器"
$desktopToken = Read-SecretValue -Prompt "IrohaWalendar 本机 API 令牌" -EnvironmentName "IROHA_WALENDAR_API_TOKEN"
$deviceToken = Read-SecretValue -Prompt "网页生成的 planner_sync 设备令牌" -EnvironmentName "CONTROL_PLANE_DEVICE_TOKEN"
if ([string]::IsNullOrWhiteSpace($desktopToken) -or [string]::IsNullOrWhiteSpace($deviceToken)) {
    throw "两个令牌都不能为空。"
}

$lastFingerprint = ""
$lastRevision = 0L
$firstPass = $true

try {
    while ($true) {
        try {
            $state = Invoke-RestMethod `
                -Uri "$desktopEndpoint/api/v1/state" `
                -Method Get `
                -Headers @{ Authorization = "Bearer $desktopToken" } `
                -TimeoutSec $TimeoutSeconds
            $clockRevision = [long]([DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds() * 1000L)
            $revision = [Math]::Max(($lastRevision + 1L), $clockRevision)
            $snapshot = New-FilteredSnapshot -State $state -Revision $revision
            $fingerprint = Get-SnapshotFingerprint -Snapshot $snapshot
            if ($firstPass -or $fingerprint -ne $lastFingerprint) {
                $body = $snapshot | ConvertTo-Json -Depth 100 -Compress
                $result = Invoke-RestMethod `
                    -Uri "$serverEndpoint/api/v1/planner/snapshot" `
                    -Method Put `
                    -Headers @{ Authorization = "Device $deviceToken" } `
                    -ContentType "application/json; charset=utf-8" `
                    -Body ([Text.Encoding]::UTF8.GetBytes($body)) `
                    -TimeoutSec $TimeoutSeconds
                $lastRevision = [long]$result.revision
                $lastFingerprint = $fingerprint
                Write-Host ("[{0}] 已同步 revision {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $lastRevision)
            }
            $firstPass = $false
            if ($Once) {
                break
            }
        }
        catch {
            if ($Once) {
                throw
            }
            Write-Warning ("同步失败，将在 {0} 秒后重试：{1}" -f $IntervalSeconds, $_.Exception.Message)
        }
        Start-Sleep -Seconds $IntervalSeconds
    }
}
finally {
    $desktopToken = $null
    $deviceToken = $null
    [GC]::Collect()
}
