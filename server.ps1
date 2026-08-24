[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [ValidateSet('help', 'connect', 'status', 'progress', 'sync', 'git', 'push', 'prs', 'workspace', 'download', 'upload')]
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
$script:Repo = 'souldowndesu/WebServer'
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
        'docs/two-agent-runtime.md',
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

function Push-AgentBranchViaLocalRelay {
    $relayPath = Join-Path $script:StateRoot 'git-relay'
    New-Item -ItemType Directory -Path $script:StateRoot -Force | Out-Null

    if (-not (Test-Path -LiteralPath $relayPath)) {
        Invoke-CheckedNative -Command 'git' -Arguments @(
            'clone',
            '--no-hardlinks',
            "${script:SshHost}:$script:RemoteRoot",
            $relayPath
        )
    } elseif (-not (Test-Path -LiteralPath (Join-Path $relayPath '.git'))) {
        throw "$relayPath exists but is not the expected Git relay repository."
    }

    $pending = & git '-C' $relayPath 'status' '--porcelain'
    if ($LASTEXITCODE -ne 0) { throw 'Unable to inspect the local Git relay.' }
    if ($pending) { throw 'The local Git relay has uncommitted changes; inspect it before pushing.' }

    $branch = (& git '-C' $relayPath 'branch' '--show-current').Trim()
    if ($LASTEXITCODE -ne 0 -or $branch -ne 'agent-1') {
        throw "The local Git relay must be on branch agent-1, not '$branch'."
    }

    # The restricted credential helper is path-scoped to this compatibility URL.
    # GitHub redirects it to the canonical souldowndesu/WebServer repository.
    $githubUrl = 'https://github.com/souldowndesu/agent.git'
    $remotes = @(& git '-C' $relayPath 'remote')
    if ($remotes -notcontains 'github') {
        Invoke-CheckedNative -Command 'git' -Arguments @('-C', $relayPath, 'remote', 'add', 'github', $githubUrl)
    } else {
        $actualUrl = (& git '-C' $relayPath 'remote' 'get-url' 'github').Trim()
        if ($actualUrl -ne $githubUrl) { throw "Unexpected github remote URL: $actualUrl" }
    }

    Invoke-CheckedNative -Command 'git' -Arguments @('-C', $relayPath, 'config', '--local', 'credential.useHttpPath', 'true')
    & git '-C' $relayPath 'config' '--local' '--unset-all' 'credential.helper'
    if ($LASTEXITCODE -ne 0 -and $LASTEXITCODE -ne 5) {
        throw 'Unable to reset the local relay credential helpers.'
    }
    & git '-C' $relayPath 'config' '--local' '--add' 'credential.helper' ''
    if ($LASTEXITCODE -ne 0) { throw 'Unable to add the local credential-helper reset entry.' }
    Invoke-CheckedNative -Command 'git' -Arguments @(
        '-C', $relayPath, 'config', '--local', '--add', 'credential.helper',
        '!f() { ssh aliyun-server /root/.local/bin/agent-git-credential "$@"; }; f'
    )

    Invoke-CheckedNative -Command 'git' -Arguments @('-C', $relayPath, 'fetch', 'origin', 'agent-1')
    Invoke-CheckedNative -Command 'git' -Arguments @('-C', $relayPath, 'merge', '--ff-only', 'origin/agent-1')

    $commit = (& git '-C' $relayPath 'rev-parse' 'agent-1').Trim()
    if ($LASTEXITCODE -ne 0 -or $commit -notmatch '^[0-9a-f]{40}$') {
        throw 'Unable to resolve the agent-1 commit for relay push.'
    }

    $previousPromptSetting = $env:GIT_TERMINAL_PROMPT
    try {
        $env:GIT_TERMINAL_PROMPT = '0'
        Invoke-CheckedNative -Command 'git' -Arguments @('-C', $relayPath, 'push', 'github', 'agent-1:agent-1')
    } finally {
        $env:GIT_TERMINAL_PROMPT = $previousPromptSetting
    }

    Invoke-ServerCommand -RemoteCommand "git -C $script:RemoteRoot update-ref refs/remotes/origin/agent-1 '$commit'"
    Write-Host "GitHub agent-1 updated through the local relay at commit $commit."
}

switch ($Action) {
    'help' {
        @'
Usage:
  .\server.ps1 status
  .\server.ps1 progress
  .\server.ps1 git
  .\server.ps1 push
  .\server.ps1 prs
  .\server.ps1 connect
  .\server.ps1 workspace
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

    'push' {
        Push-AgentBranchViaLocalRelay
    }

    'prs' {
        Invoke-ServerCommand -RemoteCommand "/root/.local/bin/agent-gh pr list --repo $script:Repo --state open"
    }

    'workspace' {
        Invoke-ServerCommand -RemoteCommand "env -C $script:RemoteRoot python3 tools/workspace_runtime.py status"
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
