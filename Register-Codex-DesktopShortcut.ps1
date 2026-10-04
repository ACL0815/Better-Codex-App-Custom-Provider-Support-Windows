[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$AppPath,
    [string]$LauncherPath = (Join-Path $PSScriptRoot 'Start-Codex-Provider.ps1'),
    [string]$DesktopPath = [Environment]::GetFolderPath('Desktop')
)

$ErrorActionPreference = 'Stop'
$app = [IO.Path]::GetFullPath($AppPath)
$launcher = [IO.Path]::GetFullPath($LauncherPath)
if (-not (Test-Path -LiteralPath $app -PathType Leaf)) { throw "Die gepatchte App wurde nicht gefunden: $app" }
if (-not (Test-Path -LiteralPath $launcher -PathType Leaf)) { throw "Der Provider-Starter wurde nicht gefunden: $launcher" }
if ([string]::IsNullOrWhiteSpace($DesktopPath)) { throw 'Windows konnte den Desktop-Ordner nicht ermitteln.' }
$desktop = [IO.Path]::GetFullPath($DesktopPath)
if (-not (Test-Path -LiteralPath $desktop -PathType Container)) { throw "Der Desktop-Ordner wurde nicht gefunden: $desktop" }
$shellPath = Join-Path $env:WINDIR 'System32\WindowsPowerShell\v1.0\powershell.exe'
$shortcutPath = Join-Path $desktop 'Codex - OpenRouter-Test.lnk'
$temporary = Join-Path $desktop ('.codex-openrouter-' + [guid]::NewGuid().ToString('N') + '.lnk')
$backup = $temporary + '.previous'
$arguments = '-NoProfile -ExecutionPolicy Bypass -File "' + $launcher + '" -AppPath "' + $app + '"'
$shell = $null
$shortcut = $null
try {
    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($temporary)
    $shortcut.TargetPath = $shellPath
    $shortcut.Arguments = $arguments
    $shortcut.WorkingDirectory = Split-Path $app
    $shortcut.IconLocation = $app + ',0'
    $shortcut.Description = 'Codex mit OpenRouter und gemeinsamem Codex-Profil starten'
    $shortcut.Save()
    [Runtime.InteropServices.Marshal]::FinalReleaseComObject($shortcut) | Out-Null
    $shortcut = $null
    if (Test-Path -LiteralPath $shortcutPath -PathType Leaf) {
        # Windows PowerShell 5.1 coerces a null backup argument to an invalid
        # empty path. Use a unique sibling backup for the atomic replacement.
        [IO.File]::Replace($temporary, $shortcutPath, $backup)
    } else {
        [IO.File]::Move($temporary, $shortcutPath)
    }
    Write-Output $shortcutPath
} finally {
    if ($null -ne $shortcut) { [Runtime.InteropServices.Marshal]::FinalReleaseComObject($shortcut) | Out-Null }
    if ($null -ne $shell) { [Runtime.InteropServices.Marshal]::FinalReleaseComObject($shell) | Out-Null }
    if (Test-Path -LiteralPath $temporary -PathType Leaf) { Remove-Item -LiteralPath $temporary -Force }
    if (Test-Path -LiteralPath $backup -PathType Leaf) { Remove-Item -LiteralPath $backup -Force }
}
