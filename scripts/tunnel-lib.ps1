#requires -Version 5.1
<#
.SYNOPSIS
    cloudflared 快速隧道的公共函数（被 tunnel.ps1 与 serve-public.ps1 复用）。

.DESCRIPTION
    只做三件事：确保 cloudflared 存在、起隧道并抓到公网网址、停掉隧道。
    隧道是「快速隧道」：不需要账号与域名，每次启动换一个随机网址。

    子进程统一走 scripts/spawn_bg.py 启动：本机环境里同时存在 NO_PROXY/no_proxy、
    HTTPS_PROXY/https_proxy 这种只差大小写的变量，PowerShell 的 Start-Process
    复制环境字典时会抛「已添加项」，Python 的 subprocess 不受影响。
#>

$ErrorActionPreference = 'Stop'

$script:RepoRoot = Split-Path -Parent $PSScriptRoot
$script:CloudflaredPath = Join-Path $script:RepoRoot '.tmp\cloudflared.exe'
$script:TunnelLogDir = Join-Path $script:RepoRoot '.tmp'
$script:UrlPattern = 'https://[a-z0-9-]+\.trycloudflare\.com'

function Get-VenvPython {
    $python = Join-Path $script:RepoRoot '.venv\Scripts\python.exe'
    if (-not (Test-Path $python)) {
        throw "找不到项目虚拟环境的 Python：$python（先在仓库根跑一次环境搭建）"
    }
    return $python
}

function Resolve-Cloudflared {
    <#
        确保 .tmp\cloudflared.exe 存在；不存在就用项目 venv 的 Python 下载。
        为什么不用 Invoke-WebRequest：本机 schannel 证书链有问题，TLS 握手就失败。
    #>
    if (Test-Path $script:CloudflaredPath) {
        return $script:CloudflaredPath
    }

    Write-Host '未找到 cloudflared，正在下载（约 55 MB，只需一次）…' -ForegroundColor Cyan
    $python = Get-VenvPython
    $fetcher = Join-Path $PSScriptRoot 'fetch_cloudflared.py'
    & $python $fetcher $script:CloudflaredPath
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path $script:CloudflaredPath)) {
        throw "cloudflared 下载失败。请手动下载后放到 $script:CloudflaredPath"
    }
    return $script:CloudflaredPath
}

function Start-Detached {
    <#
        用 spawn_bg.py 在后台起一个进程，返回 PID（int）。
        Out/Err 是日志文件路径；环境变量用 -Env 传 K=V 数组。
    #>
    param(
        [Parameter(Mandatory = $true)][string]$FilePath,
        [Parameter()][string[]]$Arguments = @(),
        [Parameter()][string]$WorkingDirectory = $script:RepoRoot,
        [Parameter(Mandatory = $true)][string]$OutLog,
        [Parameter(Mandatory = $true)][string]$ErrLog,
        [Parameter()][string[]]$Env = @()
    )

    $python = Get-VenvPython
    $spawner = Join-Path $PSScriptRoot 'spawn_bg.py'
    $spawnArgs = @($spawner, '--cwd', $WorkingDirectory, '--out', $OutLog, '--err', $ErrLog)
    foreach ($pair in $Env) { $spawnArgs += @('--env', $pair) }
    $spawnArgs += '--'
    $spawnArgs += $FilePath
    $spawnArgs += $Arguments

    $pidText = & $python @spawnArgs
    if ($LASTEXITCODE -ne 0) {
        throw "启动 $FilePath 失败（spawn_bg.py 退出码 $LASTEXITCODE）"
    }
    $parsed = 0
    if (-not [int]::TryParse(($pidText | Select-Object -Last 1).Trim(), [ref]$parsed)) {
        throw "没能从 spawn_bg.py 拿到 PID，输出：$pidText"
    }
    return $parsed
}

function Stop-Detached {
    param([Parameter(Mandatory = $true)][int]$ProcessId)

    $process = Get-Process -Id $ProcessId -ErrorAction SilentlyContinue
    if ($null -eq $process) { return }
    try {
        $process.Kill()
        $process.WaitForExit(5000) | Out-Null
    } catch {
        Write-Warning "结束进程 $ProcessId 时出错：$($_.Exception.Message)"
    }
}

function Test-DetachedAlive {
    param([Parameter(Mandatory = $true)][int]$ProcessId)
    return [bool](Get-Process -Id $ProcessId -ErrorAction SilentlyContinue)
}

function Start-Tunnel {
    <#
        起一条快速隧道，返回 @{ ProcessId = ...; Url = ...; OutLog = ...; ErrLog = ... }。
        超时没抓到网址会杀掉子进程并抛错，不留孤儿进程。
    #>
    param(
        [Parameter(Mandatory = $true)][int]$Port,
        [int]$TimeoutSeconds = 60
    )

    $exe = Resolve-Cloudflared
    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    $outLog = Join-Path $script:TunnelLogDir "tunnel-$stamp.out.log"
    $errLog = Join-Path $script:TunnelLogDir "tunnel-$stamp.err.log"

    $tunnelId = Start-Detached -FilePath $exe `
        -Arguments @('tunnel', '--url', "http://127.0.0.1:$Port", '--no-autoupdate') `
        -OutLog $outLog -ErrLog $errLog

    Write-Host "隧道已启动（pid $tunnelId），等待分配网址…" -ForegroundColor Cyan

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    $url = $null
    while ((Get-Date) -lt $deadline) {
        Start-Sleep -Milliseconds 500
        if (-not (Test-DetachedAlive -ProcessId $tunnelId)) {
            break
        }
        foreach ($file in @($outLog, $errLog)) {
            if (-not (Test-Path $file)) { continue }
            $text = Get-Content $file -Raw -ErrorAction SilentlyContinue
            if (-not $text) { continue }
            $match = [regex]::Match($text, $script:UrlPattern)
            if ($match.Success) {
                $url = $match.Value
                break
            }
        }
        if ($url) { break }
    }

    if (-not $url) {
        Stop-Detached -ProcessId $tunnelId
        $tail = ''
        foreach ($file in @($errLog, $outLog)) {
            if (Test-Path $file) {
                $tail += (Get-Content $file -Tail 15 -ErrorAction SilentlyContinue) -join "`n"
            }
        }
        throw "隧道在 $TimeoutSeconds 秒内没有给出网址。日志尾部：`n$tail"
    }

    return [pscustomobject]@{
        ProcessId = $tunnelId
        Url       = $url
        OutLog    = $outLog
        ErrLog    = $errLog
    }
}

function Stop-Tunnel {
    param([Parameter(Mandatory = $true)]$Tunnel)
    Stop-Detached -ProcessId $Tunnel.ProcessId
}
