[CmdletBinding()]
param([string]$OutputDirectory, [switch]$Verify, [string]$PythonwPath)
$ErrorActionPreference = 'Stop'
$sourceRoot = Split-Path -Parent $PSScriptRoot
if (-not $OutputDirectory) { $OutputDirectory = Join-Path $sourceRoot 'build\native' }
$out = [IO.Path]::GetFullPath($OutputDirectory)
New-Item -ItemType Directory -Path $out -Force | Out-Null
$vswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio\Installer\vswhere.exe'
$vsRoot = & $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
if (-not $vsRoot) { throw 'Visual Studio C++ Build Tools and Windows SDK are required.' }
$vcVersion = (Get-Content -LiteralPath (Join-Path $vsRoot 'VC\Auxiliary\Build\Microsoft.VCToolsVersion.default.txt')).Trim()
$vc = Join-Path $vsRoot "VC\Tools\MSVC\$vcVersion"
$sdk = Join-Path ${env:ProgramFiles(x86)} 'Windows Kits\10'
$sdkVersion = (Get-ChildItem -LiteralPath (Join-Path $sdk 'Include') -Directory | Sort-Object Name -Descending | Select-Object -First 1).Name
$cl = Join-Path $vc 'bin\Hostx64\x64\cl.exe'
$env:INCLUDE = "$vc\include;$sdk\Include\$sdkVersion\ucrt;$sdk\Include\$sdkVersion\um;$sdk\Include\$sdkVersion\shared"
$env:LIB = "$vc\lib\x64;$sdk\Lib\$sdkVersion\ucrt\x64;$sdk\Lib\$sdkVersion\um\x64"
& $cl /nologo /LD /O2 /MT /W4 /DUNICODE /D_UNICODE (Join-Path $sourceRoot 'native\bootstrap.c') "/Fo$out\bootstrap.obj" /link "/OUT:$out\dwmapi.dll" "/IMPLIB:$out\dwmapi.lib" kernel32.lib
if ($LASTEXITCODE -ne 0) { throw 'Native bootstrap compilation failed.' }
if ($Verify) {
    if (-not $PythonwPath) { $PythonwPath = (Get-Command pythonw.exe).Source }
    $hostRoot = Join-Path $out 'test-host'
    $companion = Join-Path $hostRoot 'Mods\lllucky'
    New-Item -ItemType Directory -Path $companion -Force | Out-Null
    Copy-Item -LiteralPath (Join-Path $out 'dwmapi.dll') -Destination (Join-Path $hostRoot 'dwmapi.dll') -Force
    $ini = "[lllucky]`r`nPythonw=$PythonwPath`r`n[environment]`r`nWGPU_BACKEND=lllucky-test`r`nWOW_ROGUE_SAVE=X:\lllucky-test\characters.txt`r`n"
    [IO.File]::WriteAllText((Join-Path $companion 'bootstrap.ini'), $ini, [Text.Encoding]::Unicode)
    [IO.File]::WriteAllText((Join-Path $companion 'headless.py'), 'from pathlib import Path; Path(__file__).with_name("started.flag").write_text("ok")', [Text.Encoding]::ASCII)
    $marker = Join-Path $companion 'started.flag'
    if (Test-Path -LiteralPath $marker) { Remove-Item -LiteralPath $marker }
    & $cl /nologo /O2 /MT /W4 /DUNICODE /D_UNICODE (Join-Path $sourceRoot 'native\test_host.c') "/Fo$out\test_host.obj" "/Fe$hostRoot\AzerothSurvivors.exe" /link (Join-Path $out 'dwmapi.lib') kernel32.lib
    if ($LASTEXITCODE -ne 0) { throw 'Native test host compilation failed.' }
    $oldBackend = $env:WGPU_BACKEND; $oldSave = $env:WOW_ROGUE_SAVE
    try {
        Remove-Item Env:WGPU_BACKEND -ErrorAction SilentlyContinue
        Remove-Item Env:WOW_ROGUE_SAVE -ErrorAction SilentlyContinue
        & (Join-Path $hostRoot 'AzerothSurvivors.exe')
        if ($LASTEXITCODE -ne 0) { throw "Native autostart test failed: $LASTEXITCODE" }
    } finally { $env:WGPU_BACKEND = $oldBackend; $env:WOW_ROGUE_SAVE = $oldSave }
}
Write-Host "Native bootstrap built: $out\dwmapi.dll"
