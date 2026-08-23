[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [ValidateSet('help', 'connect', 'status', 'progress', 'sync', 'git', 'prs', 'download', 'upload')]
    [string]$Action = 'help',

    [Parameter(Position = 1)]
    [string]$Value,

    [Parameter(Position = 2)]
    [string]$Destination
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$script:ControlRoot = $PSScriptRoot
$script:SshHost = 'aliyun-server'
$script:RemoteRoot = '/root/ai-workspaces/agent-1'
$script:Repo = 'souldowndesu/agent'
$script:DownloadsRoot = Join-Path $script:ControlRoot 'downloads'
$script:StateRoot = Join-Path $script:ControlRoot 'state'

function Invoke-CheckedNative {
    param(
        [Parameter(Mandatory)] [string]$Command,
        [Parameter(Mandatory)] [string[]]$Arguments
    )

    & $Command @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "$Command failed with exit code $LASTEXITCODE."
    }
}

function Invoke-ServerCommand {
    param([Parameter(Mandatory)] [string]$RemoteCommand)

    Invoke-CheckedNative -Command 'ssh' -Arguments @(
        '-o', 'BatchMode=yes',
        '-o', 'ConnectTimeout=12',
        $script:SshHost,
        $RemoteCommand
    )
}

function Sync-ServerDocuments {
    $files = @(
        'AGENTS.md',
        'README.md',
        'OPERATIONS.md',
        'COORDINATION.md',
        'ENVIRONMENT_CHANGES.md',
        'STATUS.md',
        'TASKS.md',
        'server.ps1',
        'skills/server-workspace-ops/SKILL.md'
    )

    foreach ($file in $files) {
        $localPath = Join-Path $script:ControlRoot ($file -replace '/', [IO.Path]::DirectorySeparatorChar)
        $localParent = Split-Path -Parent $localPath
        New-Item -ItemType Directory -Path $localParent -Force | Out-Null
        $remoteSource = "${script:SshHost}:$script:RemoteRoot/$file"
        Invoke-CheckedNative -Command 'scp' -Arguments @(
            '-q',
            '-o', 'BatchMode=yes',
            '-o', 'ConnectTimeout=12',
            $remoteSource,
            $localPath
        )
    }

    Write-Host 'Server documents synchronized to the local control folder.'
}

function Get-DownloadsPath {
    param([Parameter(Mandatory)] [string]$InputPath)

    New-Item -ItemType Directory -Path $script:DownloadsRoot -Force | Out-Null
    $candidate = if ([IO.Path]::IsPathRooted($InputPath)) {
        $InputPath
    } else {
        $underDownloads = Join-Path $script:DownloadsRoot $InputPath
        if (Test-Path -LiteralPath $underDownloads) { $underDownloads } else { $InputPath }
    }

    $resolved = (Resolve-Path -LiteralPath $candidate).Path
    $downloadsFull = [IO.Path]::GetFullPath($script:DownloadsRoot).TrimEnd('\', '/')
    $allowedPrefix = $downloadsFull + [IO.Path]::DirectorySeparatorChar
    if (-not $resolved.StartsWith($allowedPrefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Uploads are restricted to $script:DownloadsRoot."
    }
    return $resolved
}

switch ($Action) {
    'help' {
        @'
Usage:
  .\server.ps1 status
  .\server.ps1 progress
  .\server.ps1 git
  .\server.ps1 prs
  .\server.ps1 connect
  .\server.ps1 download <https-url> [local-name]
  .\server.ps1 upload <downloads-file> [remote-relative-path]
'@
    }

    'connect' {
        Invoke-CheckedNative -Command 'ssh' -Arguments @($script:SshHost)
    }

    'status' {
        New-Item -ItemType Directory -Path $script:StateRoot -Force | Out-Null
        $remoteCommand = 'hostname; date -Is; uptime; df -h /; free -h; git -C /root/ai-workspaces/agent-1 status --short --branch'
        $output = & ssh '-o' 'BatchMode=yes' '-o' 'ConnectTimeout=12' $script:SshHost $remoteCommand 2>&1
        if ($LASTEXITCODE -ne 0) {
            $output | ForEach-Object { Write-Error $_ }
            throw "ssh failed with exit code $LASTEXITCODE."
        }

        $snapshot = @(
            '# Server Status Snapshot',
            '',
            "- Refreshed locally: $(Get-Date -Format o)",
            "- SSH alias: $script:SshHost",
            '',
            '```text'
        ) + $output + @('```', '')
        $snapshotPath = Join-Path $script:StateRoot 'SERVER_STATUS.md'
        Set-Content -LiteralPath $snapshotPath -Value $snapshot -Encoding utf8
        $output
        Write-Host "Snapshot saved to $snapshotPath"
    }

    'sync' {
        Sync-ServerDocuments
    }

    'progress' {
        Sync-ServerDocuments
        Get-Content -LiteralPath (Join-Path $script:ControlRoot 'STATUS.md')
        Get-Content -LiteralPath (Join-Path $script:ControlRoot 'TASKS.md')
    }

    'git' {
        Invoke-ServerCommand -RemoteCommand 'git -C /root/ai-workspaces/agent-1 status --short --branch; git -C /root/ai-workspaces/agent-1 log -5 --oneline --decorate'
    }

    'prs' {
        Invoke-ServerCommand -RemoteCommand "/root/.local/bin/agent-gh pr list --repo $script:Repo --state open"
    }

    'download' {
        if ([string]::IsNullOrWhiteSpace($Value)) {
            throw 'download requires an HTTPS URL.'
        }
        $uri = [Uri]$Value
        if ($uri.Scheme -ne 'https') {
            throw 'Only HTTPS downloads are allowed.'
        }

        New-Item -ItemType Directory -Path $script:DownloadsRoot -Force | Out-Null
        $name = $Destination
        if ([string]::IsNullOrWhiteSpace($name)) {
            $name = [Uri]::UnescapeDataString([IO.Path]::GetFileName($uri.AbsolutePath))
        }
        if ([string]::IsNullOrWhiteSpace($name)) {
            $name = 'download.bin'
        }
        if ($name -ne [IO.Path]::GetFileName($name)) {
            throw 'The local download name must be a file name, not a path.'
        }

        $target = Join-Path $script:DownloadsRoot $name
        Invoke-WebRequest -Uri $uri -OutFile $target
        Get-FileHash -Algorithm SHA256 -LiteralPath $target
    }

    'upload' {
        if ([string]::IsNullOrWhiteSpace($Value)) {
            throw 'upload requires a file from the local downloads folder.'
        }
        $localPath = Get-DownloadsPath -InputPath $Value
        $remoteRelative = if ([string]::IsNullOrWhiteSpace($Destination)) {
            [IO.Path]::GetFileName($localPath)
        } else {
            $Destination.Replace('\', '/')
        }

        if ($remoteRelative.StartsWith('/') -or $remoteRelative -notmatch '^[A-Za-z0-9._/-]+$') {
            throw 'Remote relative path contains unsupported characters.'
        }
        $segments = $remoteRelative.Split('/', [StringSplitOptions]::RemoveEmptyEntries)
        if ($segments.Count -eq 0 -or $segments -contains '..') {
            throw 'Remote relative path must stay under .cache/uploads.'
        }

        $remotePath = "$script:RemoteRoot/.cache/uploads/$remoteRelative"
        $remoteDirectory = $remotePath.Substring(0, $remotePath.LastIndexOf('/'))
        Invoke-ServerCommand -RemoteCommand "mkdir -p -- '$remoteDirectory'"
        Invoke-CheckedNative -Command 'scp' -Arguments @(
            '-q',
            '-o', 'BatchMode=yes',
            '-o', 'ConnectTimeout=12',
            '--',
            $localPath,
            "${script:SshHost}:$remotePath"
        )
        Get-FileHash -Algorithm SHA256 -LiteralPath $localPath
        Invoke-ServerCommand -RemoteCommand "sha256sum -- '$remotePath'"
    }
}
