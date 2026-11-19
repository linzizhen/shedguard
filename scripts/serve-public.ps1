#requires -Version 5.1
<#
.SYNOPSIS
    一键把 shedguard 变成「一个能发给别人打开的网址」。

.DESCRIPTION
    串起四步：构建前端（必要时）→ 起服务端 → 等健康检查 → 起隧道并打印网址。
    Ctrl+C 会同时停掉隧道与服务端，不留孤儿进程。

    用法：
        .\scripts\serve-public.cmd
        .\scripts\serve-public.cmd -Port 8020 -Rebuild
        .\scripts\serve-public.cmd -SkipTunnel        # 只在本机/局域网看

    为什么要显式设限流：公网暴露后任何人都能建匿名账号、上传图片，
    默认值是 0（关闭），只在演示脚本里设成每分钟 60 次。
#>
[CmdletBinding()]
param(
    [Parameter()][int]$Port = 8010,
    [Parameter()][switch]$Rebuild,
    [Parameter()][switch]$SkipTunnel,
    [Parameter()][int]$RateLimitPerMinute = 60
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'tunnel-lib.ps1')

$repoRoot = Split-Path -Parent $PSScriptRoot
$appDir = Join-Path $repoRoot 'app'
$distIndex = Join-Path $appDir 'dist\index.html'
$serverDir = Join-Path $repoRoot 'server'
$python = Get-VenvPython

function Build-Web {
    Write-Host '正在构建前端（约 1–3 分钟）…' -ForegroundColor Cyan
    Push-Location $appDir
    try {
        & npm.cmd run build:web
        if ($LASTEXITCODE -ne 0) {
            throw "前端构建失败（退出码 $LASTEXITCODE）"
        }
    } finally {
        Pop-Location
    }
    if (-not (Test-Path $distIndex)) {
        throw "构建结束但没找到 $distIndex"
    }
}

function Wait-Health {
    param([int]$TimeoutSeconds = 60)
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    $url = "http://127.0.0.1:$Port/healthz"
    while ((Get-Date) -lt $deadline) {
        try {
            $response = Invoke-RestMethod -Uri $url -TimeoutSec 3 -ErrorAction Stop
            if ($response.status -eq 'ok') { return }
        } catch {
            # 服务端还没起来，继续等
        }
        Start-Sleep -Milliseconds 500
    }
    throw "服务端在 $TimeoutSeconds 秒内没有通过健康检查（$url）"
}

if ($Rebuild -or -not (Test-Path $distIndex)) {
    Build-Web
} else {
    Write-Host "复用已有前端构建产物：$distIndex（要重建加 -Rebuild）" -ForegroundColor Gray
}

$serverPid = $null
$tunnel = $null
try {
    Write-Host "正在启动服务端（端口 $Port）…" -ForegroundColor Cyan
    $serverLog = Join-Path $repoRoot ".tmp\server-public-$Port.log"
    $serverErr = Join-Path $repoRoot ".tmp\server-public-$Port.err.log"
    $serverPid = Start-Detached -FilePath $python `
        -Arguments @('-m', 'shedguard_server') `
        -WorkingDirectory $serverDir `
        -OutLog $serverLog -ErrLog $serverErr `
        -Env @(
            "PYTHONPATH=$(Join-Path $serverDir 'src')",
            'SHEDGUARD_HOST=127.0.0.1',
            "SHEDGUARD_PORT=$Port",
            "SHEDGUARD_RATE_LIMIT_PER_MINUTE=$RateLimitPerMinute"
        )

    Wait-Health -TimeoutSeconds 90
    Write-Host '服务端已就绪。' -ForegroundColor Green

    if ($SkipTunnel) {
        Write-Host ''
        Write-Host '  本机地址：' -NoNewline
        Write-Host "http://127.0.0.1:$Port" -ForegroundColor Green
        Write-Host ''
        Write-Host '  按 Ctrl+C 结束。' -ForegroundColor Gray
        while (Test-DetachedAlive -ProcessId $serverPid) {
            Start-Sleep -Seconds 2
        }
    } else {
        $tunnel = Start-Tunnel -Port $Port -TimeoutSeconds 60
        Write-Host ''
        Write-Host '  公网网址：' -NoNewline
        Write-Host $tunnel.Url -ForegroundColor Green
        Write-Host ''
        Write-Host '  把这个网址发到手机上打开即可（不需要填任何服务器地址）。' -ForegroundColor Gray
        Write-Host '  这个链接等于家门钥匙，别公开发。按 Ctrl+C 结束。' -ForegroundColor Yellow
        Write-Host ''
        while ((Test-DetachedAlive -ProcessId $serverPid) -and
               (Test-DetachedAlive -ProcessId $tunnel.ProcessId)) {
            Start-Sleep -Seconds 2
        }
        if (-not (Test-DetachedAlive -ProcessId $serverPid)) {
            Write-Warning '服务端已退出，日志尾部：'
            if (Test-Path $serverErr) { Get-Content $serverErr -Tail 20 }
            if (Test-Path $serverLog) { Get-Content $serverLog -Tail 20 }
        }
    }
} finally {
    if ($tunnel) { Stop-Tunnel -Tunnel $tunnel }
    if ($serverPid) { Stop-Detached -ProcessId $serverPid }
    Write-Host '已全部关闭。' -ForegroundColor Gray
}
