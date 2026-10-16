<#
.SYNOPSIS
    編譯絲網印刷膠片顆粒半調網點外掛。

.DESCRIPTION
    自動探測 GIMP 安裝路徑、編譯器與相依標頭檔，產生 film-halftone.dll。
    若 glib/cairo/pango 等開發標頭檔不存在，會提示執行 fetch-deps.ps1。
#>
[CmdletBinding()]
param(
    [string]$GimpDir   = 'D:\Software\GIMP 3',
    [string]$Compiler  = 'D:\mingw64\bin\gcc.exe',
    [string]$DepsDir   = '',
    [string]$OutDir    = ''
)

$ErrorActionPreference = 'Stop'

$Root = $PSScriptRoot
if (-not $Root) { $Root = Split-Path -Parent $MyInvocation.MyCommand.Path }
if (-not $Root) { $Root = (Get-Location).Path }

if (-not $DepsDir) { $DepsDir = Join-Path $Root 'deps' }
if (-not $OutDir)  { $OutDir  = Join-Path $Root 'out' }

function Assert-Exists($path, $hint) {
    if (-not (Test-Path $path)) {
        throw "找不到 $hint：$path`n請先執行 fetch-deps.ps1 下載相依標頭檔。"
    }
}

# --- 檢查工具鏈 ---
Assert-Exists $Compiler          'C 編譯器'
Assert-Exists $GimpDir           'GIMP 安裝目錄'

$inc = Join-Path $GimpDir 'include'
Assert-Exists (Join-Path $inc 'gimp-3.0\libgimp\gimp.h') 'GIMP 開發標頭檔'
Assert-Exists (Join-Path $GimpDir 'lib\pkgconfig\gimp-3.0.pc') 'GIMP pkgconfig'

# --- 相依標頭檔（自 deps 取得） ---
$deps = Resolve-Path $DepsDir
$depInc = Join-Path $deps 'ucrt64\include'

$includes = @(
    (Join-Path $inc 'gimp-3.0'),
    (Join-Path $inc 'gegl-0.4'),
    (Join-Path $inc 'babl-0.1'),
    (Join-Path $depInc 'glib-2.0'),
    (Join-Path $depInc 'cairo'),
    (Join-Path $depInc 'gdk-pixbuf-2.0'),
    (Join-Path $depInc 'pango-1.0'),
    (Join-Path $depInc 'harfbuzz'),
    $depInc,
    (Join-Path $deps 'ucrt64\lib\glib-2.0\include')
)

foreach ($p in $includes) { Assert-Exists $p '相依標頭檔' }

# --- 輸出目錄 ---
if (-not (Test-Path $OutDir)) { New-Item -ItemType Directory -Path $OutDir -Force | Out-Null }

$src = Join-Path $Root 'src\film-halftone.c'
Assert-Exists $src '外掛原始碼'

$dll = Join-Path $OutDir 'film-halftone.exe'

Write-Host '=== 編譯絲網印刷膠片顆粒半調網點外掛 ===' -ForegroundColor Cyan
Write-Host "  原始碼 : $src"
Write-Host "  輸出   : $dll"
Write-Host ''

# GIMP 3.x 的外掛以獨立執行檔（.exe）形式載入，不是 DLL。
# GIMP_MAIN() 會產生 WinMain/main 進入點，由 gimp_main() 接手 IPC。
#
# -mwindows 一定要加：未指定時 MinGW 會連結 console 子系統，
# GIMP 啟動外掛時 Windows 就會額外開一個黑色終端視窗。
$args = @(
    '-O2'
    '-Wall'
    '-mwindows'
    '-o', $dll
    $src
)

foreach ($p in $includes) { $args += "-I$p" }

$glibLib = Join-Path $deps 'ucrt64\lib'
$gimpLib = Join-Path $GimpDir 'lib'
$gimpBin = Join-Path $GimpDir 'bin'

# 直接以 GIMP 實際使用的 DLL 作為連結輸入，確保 ABI 與執行時完全一致。
# （MSYS2 套件只提供標頭檔，沒有匯入庫；改用 -l: 直接指定 DLL 亦可。）
$args += @(
    "-L$gimpLib"
    '-lgimp-3.0'
    '-lgegl-0.4'
    '-lbabl-0.1'
    "-L$gimpBin"
    '-l:libglib-2.0-0.dll'
    '-l:libgobject-2.0-0.dll'
    '-l:libgio-2.0-0.dll'
    '-l:libgmodule-2.0-0.dll'
    '-l:libcairo-2.dll'
    '-l:libpango-1.0-0.dll'
    '-l:libgdk_pixbuf-2.0-0.dll'
    '-lm'
)

& $Compiler @args

if ($LASTEXITCODE -ne 0) {
    Write-Host "`n編譯失敗（退出碼 $LASTEXITCODE）" -ForegroundColor Red
    exit $LASTEXITCODE
}

Write-Host "`n編譯成功！" -ForegroundColor Green
Get-Item $dll | Select-Object Name, Length, LastWriteTime | Format-Table -AutoSize
