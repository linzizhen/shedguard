#requires -Version 5.1
<#
.SYNOPSIS
    shedguard 的 git flow 助手（纯 git 实现，不依赖 git-flow 扩展）。

.DESCRIPTION
    两条长期分支：main（可发布）/ develop（集成）。
    三条短期分支：feature/*、release/*、hotfix/*。

    用法示例：
        pwsh scripts/gitflow.ps1 feature-start -Name portrait-album-paging
        pwsh scripts/gitflow.ps1 feature-finish -Name portrait-album-paging
        pwsh scripts/gitflow.ps1 release-start -Version 0.2.0
        pwsh scripts/gitflow.ps1 release-finish -Version 0.2.0
        pwsh scripts/gitflow.ps1 hotfix-start -Version 0.1.1
        pwsh scripts/gitflow.ps1 hotfix-finish -Version 0.1.1
        pwsh scripts/gitflow.ps1 status
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true, Position = 0)]
    [ValidateSet('feature-start', 'feature-finish', 'release-start', 'release-finish',
        'hotfix-start', 'hotfix-finish', 'status')]
    [string]$Action,

    [Parameter(Position = 1)]
    [string]$Name,

    [Parameter()]
    [string]$Version
)

$ErrorActionPreference = 'Stop'
$MainBranch = 'main'
$DevelopBranch = 'develop'

function Invoke-Git {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Args)
    & git @Args
    if ($LASTEXITCODE -ne 0) {
        throw "git $($Args -join ' ') 失败（退出码 $LASTEXITCODE）"
    }
}

function Get-CurrentBranch {
    $branch = & git rev-parse --abbrev-ref HEAD
    if ($LASTEXITCODE -ne 0) { throw '无法读取当前分支' }
    return $branch.Trim()
}

function Assert-Clean {
    $dirty = & git status --porcelain
    if ($LASTEXITCODE -ne 0) { throw '无法读取工作区状态' }
    if ($dirty) {
        throw "工作区不干净，先提交或 stash：`n$($dirty -join "`n")"
    }
}

function Assert-Name { param([string]$Value, [string]$What)
    if (-not $Value) { throw "缺少 $What，例如 -Name my-change" }
    if ($Value -notmatch '^[a-z0-9][a-z0-9-]*$') {
        throw "$What 只能用小写字母、数字和短横线，例如 my-change"
    }
}

function Assert-Version { param([string]$Value)
    if (-not $Value) { throw '缺少 -Version，例如 0.2.0' }
    if ($Value -notmatch '^\d+\.\d+\.\d+$') { throw '-Version 必须是 0.2.0 这种三段式版本号' }
}

function Sync-From { param([string]$Branch)
    Invoke-Git switch $Branch
    & git rev-parse --verify --quiet "origin/$Branch" | Out-Null
    if ($LASTEXITCODE -eq 0) {
        Invoke-Git pull --ff-only origin $Branch
    } else {
        Write-Output "远端还没有 origin/$Branch，跳过拉取。"
    }
}

switch ($Action) {
    'status' {
        $current = Get-CurrentBranch
        Write-Output "当前分支：$current"
        Write-Output ''
        Invoke-Git branch -vv
    }

    'feature-start' {
        Assert-Name $Name 'Name'
        Assert-Clean
        Sync-From $DevelopBranch
        Invoke-Git switch -c "feature/$Name"
        Write-Output "已从 $DevelopBranch 切出 feature/$Name，完成后用 feature-finish 合并回去。"
    }

    'feature-finish' {
        Assert-Name $Name 'Name'
        Assert-Clean
        $branch = "feature/$Name"
        Invoke-Git switch $DevelopBranch
        Invoke-Git pull --ff-only origin $DevelopBranch
        Invoke-Git merge --no-ff $branch -m "merge: feature/$Name"
        Invoke-Git branch -d $branch
        Invoke-Git push origin $DevelopBranch
        Write-Output "feature/$Name 已合并进 $DevelopBranch 并推送。"
    }

    'release-start' {
        Assert-Version $Version
        Assert-Clean
        Sync-From $DevelopBranch
        Invoke-Git switch -c "release/$Version"
        Write-Output "已切出 release/$Version：只允许改版本号、文档与本次发布的修复，不再加功能。"
        Write-Output "记得同步改 app/app.json 的 version 与 server/pyproject.toml 的 version。"
    }

    'release-finish' {
        Assert-Version $Version
        Assert-Clean
        $branch = "release/$Version"
        Invoke-Git switch $MainBranch
        Invoke-Git pull --ff-only origin $MainBranch
        Invoke-Git merge --no-ff $branch -m "release: v$Version"
        Invoke-Git tag -a "v$Version" -m "v$Version"
        Invoke-Git switch $DevelopBranch
        Invoke-Git merge --no-ff $branch -m "merge: release/$Version 回到 $DevelopBranch"
        Invoke-Git branch -d $branch
        Invoke-Git push origin $MainBranch $DevelopBranch --tags
        Write-Output "v$Version 已发布：$MainBranch 与 $DevelopBranch 都已推送，标签已带上。"
    }

    'hotfix-start' {
        Assert-Version $Version
        Assert-Clean
        Sync-From $MainBranch
        Invoke-Git switch -c "hotfix/$Version"
        Write-Output "已从 $MainBranch 切出 hotfix/$Version：只修线上问题，不夹带新功能。"
    }

    'hotfix-finish' {
        Assert-Version $Version
        Assert-Clean
        $branch = "hotfix/$Version"
        Invoke-Git switch $MainBranch
        Invoke-Git pull --ff-only origin $MainBranch
        Invoke-Git merge --no-ff $branch -m "hotfix: v$Version"
        Invoke-Git tag -a "v$Version" -m "v$Version"
        Invoke-Git switch $DevelopBranch
        Invoke-Git merge --no-ff $branch -m "merge: hotfix/$Version 回到 $DevelopBranch"
        Invoke-Git branch -d $branch
        Invoke-Git push origin $MainBranch $DevelopBranch --tags
        Write-Output "热修 v$Version 已发布并回灌 $DevelopBranch。"
    }
}