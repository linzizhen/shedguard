#requires -Version 5.1
<#
.SYNOPSIS
    起一条 cloudflared 快速隧道，把本机服务端暴露成一个 https 网址。

.DESCRIPTION
    只做隧道这一件事，服务端要自己先起好。日常演示请用 serve-public.ps1（它会串起来）。

    用法：
        .\scripts\tunnel.cmd -Port 8010
        .\scripts\tunnel.cmd -Port 8010 -TimeoutSeconds 90

    网址每次启动都不一样（免费快速隧道的特性），Ctrl+C 结束。
#>
[CmdletBinding()]
param(
    [Parameter()][int]$Port = 8010,
    [Parameter()][int]$TimeoutSeconds = 60
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'tunnel-lib.ps1')

$tunnel = $null
try {
    $tunnel = Start-Tunnel -Port $Port -TimeoutSeconds $TimeoutSeconds
    Write-Host ''
    Write-Host '  公网网址：' -NoNewline
    Write-Host $tunnel.Url -ForegroundColor Green
    Write-Host ''
    Write-Host '  把这个网址发到手机上打开即可（不需要填任何服务器地址）。' -ForegroundColor Gray
    Write-Host '  这个链接等于家门钥匙，别公开发。按 Ctrl+C 结束。' -ForegroundColor Yellow
    Write-Host ''
    while (Test-DetachedAlive -ProcessId $tunnel.ProcessId) {
        Start-Sleep -Seconds 2
    }
    Write-Warning '隧道进程已退出，检查日志：'
    if (Test-Path $tunnel.ErrLog) {
        Get-Content $tunnel.ErrLog -Tail 15
    }
} finally {
    if ($tunnel) {
        Stop-Tunnel -Tunnel $tunnel
        Write-Host '隧道已关闭。' -ForegroundColor Gray
    }
}
