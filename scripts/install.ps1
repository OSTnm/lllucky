[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [Parameter(Mandatory = $true)][string]$GameDir,
    [string]$PythonwPath
)
$ErrorActionPreference = 'Stop'
$gameRoot = (Resolve-Path -LiteralPath $GameDir).Path
if (-not (Test-Path -LiteralPath (Join-Path $gameRoot 'AzerothSurvivors.exe'))) {
    throw 'GameDir must contain AzerothSurvivors.exe.'
}
if (Get-Process -Name AzerothSurvivors -ErrorAction SilentlyContinue) {
    throw 'Close the game before installing or updating lllucky.'
}
if (-not $PythonwPath) {
    $pythonCommand = Get-Command pythonw.exe -ErrorAction SilentlyContinue
    if (-not $pythonCommand) { throw '64-bit Python 3.10+ is required. Pass -PythonwPath if it is not on PATH.' }
    $PythonwPath = $pythonCommand.Source
}
$pythonw = (Resolve-Path -LiteralPath $PythonwPath).Path
$pythonConsole = Join-Path (Split-Path -Parent $pythonw) 'python.exe'
if (Test-Path -LiteralPath $pythonConsole) {
    $pythonBits = & $pythonConsole -c 'import struct; print(struct.calcsize(chr(80)) * 8)'
    if ($LASTEXITCODE -ne 0 -or $pythonBits.Trim() -ne '64') { throw '64-bit Python is required.' }
}
$sourceRoot = Split-Path -Parent $PSScriptRoot
$addonSource = Join-Path $sourceRoot 'addon\lllucky'
$backendSource = Join-Path $sourceRoot 'backend'
$backendFiles = @('memory_backend.py', 'worker.py', 'headless.py')
foreach ($file in $backendFiles) {
    if (-not (Test-Path -LiteralPath (Join-Path $backendSource $file))) { throw "Missing source: $file" }
}
$addonTarget = Join-Path $gameRoot 'benilla-config\AddOns\lllucky'
$backendTarget = Join-Path $gameRoot 'Mods\lllucky'
if ($PSCmdlet.ShouldProcess($gameRoot, 'Install lllucky addon, companion and launcher')) {
    New-Item -ItemType Directory -Path $addonTarget, $backendTarget -Force | Out-Null
    Copy-Item -LiteralPath (Join-Path $addonSource 'lllucky.toc'), (Join-Path $addonSource 'lllucky.lua') -Destination $addonTarget
    foreach ($file in $backendFiles) {
        Copy-Item -LiteralPath (Join-Path $backendSource $file) -Destination $backendTarget
    }
    # Remove only a launcher line belonging to an older lllucky/LuckyControl installation.
    # Keep all Vulkan, GPU, save-path and other user settings.
    $vulkan = Join-Path $gameRoot 'Start-Azeroth-Vulkan.cmd'
    if (Test-Path -LiteralPath $vulkan) {
        $byteEncoding = [Text.Encoding]::GetEncoding(28591)
        $old = $byteEncoding.GetString([IO.File]::ReadAllBytes($vulkan))
        $pattern = '(?im)^start\s+""\s+"[^"\r\n]*pythonw\.exe"\s+"%~dp0Mods\\(?:LuckyControl|lllucky)\\headless\.py"\s*\r?\n'
        $clean = [regex]::Replace($old, $pattern, '')
        if ($clean -ne $old) {
            $backup = Join-Path $backendTarget 'launcher-before-install.cmd'
            if (-not (Test-Path -LiteralPath $backup)) { Copy-Item -LiteralPath $vulkan -Destination $backup }
            [IO.File]::WriteAllBytes($vulkan, $byteEncoding.GetBytes($clean))
        }
    }
    $launcher = @"
@echo off
setlocal
cd /d "%~dp0"
start "" "$pythonw" "%~dp0Mods\lllucky\headless.py"
if exist "%~dp0Start-Azeroth-Vulkan.cmd" (
  call "%~dp0Start-Azeroth-Vulkan.cmd"
) else (
  start "" "%~dp0AzerothSurvivors.exe"
)
endlocal
"@
    $launcher = $launcher -replace '\r?\n', "`r`n"
    [IO.File]::WriteAllText((Join-Path $gameRoot 'Start-Azeroth-lllucky.cmd'), $launcher, [Text.Encoding]::Default)
    Write-Host 'Installed. Start the game with Start-Azeroth-lllucky.cmd, enable lllucky in AddOns, and enter /lllucky.'
}
