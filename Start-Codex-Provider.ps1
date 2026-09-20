param(
    [string]$CodexHome = (Join-Path $env:USERPROFILE '.codex-openrouter-test'),
    [string]$KeyFile = (Join-Path $env:USERPROFILE '.codex\secrets\openrouter-api-key.txt'),
    [switch]$CheckOnly,
    [switch]$InPackage
)
$ErrorActionPreference = 'Stop'
try {
    $codexTestHome = [IO.Path]::GetFullPath($CodexHome)
    $keyPath = [IO.Path]::GetFullPath($KeyFile)
    $package = Get-AppxPackage -Name 'ACL0815.CodexProviderPatch'
    if (-not $package) {
        throw 'Die Windows-Test-App ist noch nicht registriert. Bitte zuerst Register-Codex-PatchIdentity.ps1 ausfuehren.'
    }
    $appPath = Join-Path $package.InstallLocation 'app\ChatGPT.exe'
    if (-not (Test-Path -LiteralPath $appPath)) {
        throw 'Die installierte Test-App wurde nicht gefunden.'
    }
    $testKey = [IO.File]::ReadAllText($keyPath).Trim()
    if ([string]::IsNullOrWhiteSpace($testKey) -or $testKey -eq 'HIER_DEINEN_OPENROUTER_API_KEY_EINFUEGEN') {
        throw 'Bitte zuerst den Platzhalter in .codex\secrets\openrouter-api-key.txt durch deinen OpenRouter API-Key ersetzen und speichern.'
    }
    if ($testKey -match '\s') {
        throw 'Die Key-Datei muss genau einen API-Key ohne Leerzeichen oder weitere Zeilen enthalten.'
    }
    if ($CheckOnly) {
        Write-Output 'App vorhanden; Key-Datei ist ausgefuellt. Kein API-Aufruf und kein App-Start ausgefuehrt.'
        exit 0
    }
    $runningCodex = @(Get-CimInstance Win32_Process -Filter "Name='ChatGPT.exe' OR Name='Codex.exe'" |
        Where-Object { $_.ExecutablePath -and ($_.ExecutablePath -like '*\OpenAI.Codex_*\app\*' -or $_.ExecutablePath -like '*\Programs\Codex-Provider-Patch\*' -or $_.ExecutablePath -like '*\ACL0815.CodexProviderPatch_*\*') })
    if ($runningCodex.Count -gt 0) {
        throw 'Bitte die laufende Codex-Desktop-App vollstaendig beenden und diesen Starter danach erneut oeffnen. Der Starter beendet keine Aufgaben automatisch.'
    }
    if (-not $InPackage) {
        $packageShell = Join-Path $env:WINDIR 'System32\WindowsPowerShell\v1.0\powershell.exe'
        Invoke-CommandInDesktopPackage -PackageFamilyName $package.PackageFamilyName -AppId App -Command $packageShell -Args ('-NoProfile -ExecutionPolicy Bypass -File "' + $PSCommandPath + '" -InPackage -CodexHome "' + $codexTestHome + '" -KeyFile "' + $keyPath + '"') -PreventBreakaway
        exit 0
    }
    $previousKey = $env:OPENROUTER_API_KEY
    $previousHome = $env:CODEX_HOME
    $previousProfile = $env:CODEX_ELECTRON_USER_DATA_PATH
    try {
        $env:OPENROUTER_API_KEY = $testKey
        $env:CODEX_HOME = $codexTestHome
        $env:CODEX_ELECTRON_USER_DATA_PATH = Join-Path $codexTestHome 'desktop-profile'
        Start-Process -FilePath $appPath -WorkingDirectory (Split-Path $appPath) -WindowStyle Normal
    } finally {
        $env:OPENROUTER_API_KEY = $previousKey
        $env:CODEX_HOME = $previousHome
        $env:CODEX_ELECTRON_USER_DATA_PATH = $previousProfile
        $testKey = $null
    }
} catch {
    if ($CheckOnly) {
        Write-Error $_.Exception.Message
    } else {
        Add-Type -AssemblyName System.Windows.Forms
        [Windows.Forms.MessageBox]::Show($_.Exception.Message, 'Codex - OpenRouter-Test', 'OK', 'Information') | Out-Null
    }
    exit 1
}
