<#
.SYNOPSIS
    將外掛部署到 GIMP 的 plug-ins 資料夾。
#>
[CmdletBinding()]
param(
    [string]$GimpDir  = 'D:\Software\GIMP 3',
    [switch]$System,
    [string]$UserVersion = ''
)

$ErrorActionPreference = 'Stop'

$Root = $PSScriptRoot
if (-not $Root) { $Root = (Get-Location).Path }

$dll = Join-Path $Root 'out\film-halftone.exe'
if (-not (Test-Path $dll)) { throw "找不到外掛：$dll`n請先執行 build.ps1" }

if ($System) {
    $plugRoot = Join-Path $GimpDir 'lib\gimp\3.0\plug-ins'
} else {
    # GIMP 3.x 的使用者設定目錄版本號可能與安裝目錄不同
    # （例如安裝目錄為 lib/gimp/3.0，使用者目錄則為 Roaming/GIMP/3.2）
    if (-not $UserVersion) {
        $roaming = Join-Path $env:APPDATA 'GIMP'
        if (Test-Path $roaming) {
            $found = Get-ChildItem $roaming -Directory |
                     Sort-Object Name -Descending |
                     Where-Object { $_.Name -match '^3\.' } |
                     Select-Object -First 1
            if ($found) { $UserVersion = $found.Name }
        }
        if (-not $UserVersion) { $UserVersion = '3.2' }
    }
    $plugRoot = Join-Path $env:APPDATA "GIMP\$UserVersion\plug-ins"
}

# GIMP 要求每個外掛位於自己的子目錄中，否則會被跳過
# （訊息：「外掛插件必須安裝在子目錄中」）
$target = Join-Path $plugRoot 'film-halftone'

if (-not (Test-Path $target)) { New-Item -ItemType Directory -Path $target -Force | Out-Null }

$dest = Join-Path $target 'film-halftone.exe'

# GIMP 執行中會鎖住外掛執行檔，此時覆寫會失敗。
# 先偵測並明確報錯，不要靜默跳過後還印出「部署完成」。
$running = Get-Process -Name 'gimp-3.2', 'gimp-console-3.2' -ErrorAction SilentlyContinue
if ($running) {
    Write-Warning '偵測到 GIMP 仍在執行中，檔案可能已被鎖住。'
    Write-Warning '若部署失敗，請完全關閉 GIMP 後重新執行本腳本。'
}

try {
    Copy-Item $dll $dest -Force -ErrorAction Stop
}
catch {
    Write-Host "`n部署失敗：$($_.Exception.Message)" -ForegroundColor Red
    exit 1
}

# 部署後驗證：以雜湊比對確認目標與來源完全一致。
# 只要不一致就代表沒更新成功，絕不可宣稱部署完成。
$srcHash = (Get-FileHash $dll -Algorithm SHA256).Hash
$dstHash = (Get-FileHash $dest -Algorithm SHA256).Hash

if ($srcHash -ne $dstHash) {
    Write-Host "`n部署驗證失敗：目標檔與來源檔雜湊不符" -ForegroundColor Red
    Write-Host "  來源 $srcHash ($dll)" -ForegroundColor Red
    Write-Host "  目標 $dstHash ($dest)" -ForegroundColor Red
    exit 1
}

Write-Host '=== 部署完成（已驗證雜湊一致） ===' -ForegroundColor Green
Write-Host "  來源 : $dll"
Write-Host "  目標 : $dest"
Write-Host ''
Write-Host '請重新啟動 GIMP，然後使用：' -ForegroundColor Cyan
Write-Host '  濾鏡 → 開發 → 膠片顆粒半調網點…' -ForegroundColor Cyan
