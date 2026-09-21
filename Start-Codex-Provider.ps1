param(
    [string]$AppPath = (Join-Path $env:LOCALAPPDATA 'Programs\Codex-Provider-Patch\ChatGPT.exe'),
    [string]$CodexHome = (Join-Path $env:USERPROFILE '.codex'),
    [string]$CatalogFile = (Join-Path $env:USERPROFILE '.codex-openrouter-test\openrouter-models.json'),
    [string]$KeyFile = (Join-Path $env:USERPROFILE '.codex\secrets\openrouter-api-key.txt'),
    [switch]$CheckOnly,
    [switch]$InPackage
)
$ErrorActionPreference = 'Stop'
try {
    $sharedCodexHome = [IO.Path]::GetFullPath($CodexHome)
    $catalogPath = [IO.Path]::GetFullPath($CatalogFile)
    $keyPath = [IO.Path]::GetFullPath($KeyFile)
    $appPath = [IO.Path]::GetFullPath($AppPath)
    $patchManifestPath = Join-Path (Split-Path $appPath) 'codex-provider-patch.json'
    $originalPackage = Get-AppxPackage -Name 'OpenAI.Codex'
    if (-not $originalPackage) { throw 'Die originale OpenAI-Codex-App ist nicht installiert.' }
    if (-not (Test-Path -LiteralPath $appPath)) { throw 'Die externe gepatchte Codex-Kopie wurde nicht gefunden. Bitte den Windows-Patcher erneut ausfuehren.' }
    if (-not (Test-Path -LiteralPath $patchManifestPath)) { throw 'Die Patch-Metadaten fehlen. Eine unbekannte App-Kopie wird nicht gestartet.' }
    $patchManifest = Get-Content -LiteralPath $patchManifestPath -Raw | ConvertFrom-Json
    $expectedSource = [IO.Path]::GetFullPath((Join-Path $originalPackage.InstallLocation 'app'))
    $recordedSource = [IO.Path]::GetFullPath([string]$patchManifest.source)
    if ($recordedSource.TrimEnd('\') -ine $expectedSource.TrimEnd('\')) {
        throw 'Die gepatchte Kopie gehoert nicht zur aktuell installierten Codex-Version. Bitte den Windows-Patcher erneut ausfuehren.'
    }
    $sharedConfigPath = Join-Path $sharedCodexHome 'config.toml'
    if (-not (Test-Path -LiteralPath $sharedConfigPath)) { throw "Das gemeinsame Codex-Profil wurde nicht gefunden: $sharedCodexHome" }
    $sharedConfig = Get-Content -LiteralPath $sharedConfigPath -Raw
    if ($sharedConfig -match '(?m)^\s*model_catalog_json\s*=') {
        throw 'Die gemeinsame config.toml enthaelt model_catalog_json. Entferne diesen globalen Testkatalog zuerst, damit normale Codex-Starts weiter den aktuellen Standardkatalog verwenden.'
    }
    if (-not (Test-Path -LiteralPath $catalogPath)) { throw "Der OpenRouter-Modellkatalog wurde nicht gefunden: $catalogPath" }
    try { $catalog = Get-Content -LiteralPath $catalogPath -Raw | ConvertFrom-Json }
    catch { throw "Der OpenRouter-Modellkatalog ist kein gueltiges JSON: $catalogPath" }
    if (-not $catalog.models -or @($catalog.models).Count -eq 0) { throw 'Der OpenRouter-Modellkatalog enthaelt keine Modelle.' }
    $testKey = [IO.File]::ReadAllText($keyPath).Trim()
    if ([string]::IsNullOrWhiteSpace($testKey) -or $testKey -eq 'HIER_DEINEN_OPENROUTER_API_KEY_EINFUEGEN') {
        throw 'Bitte zuerst den Platzhalter in .codex\secrets\openrouter-api-key.txt durch deinen OpenRouter API-Key ersetzen und speichern.'
    }
    if ($testKey -match '\s') { throw 'Die Key-Datei muss genau einen API-Key ohne Leerzeichen oder weitere Zeilen enthalten.' }
    $runningCodex = @(Get-CimInstance Win32_Process -Filter "Name='ChatGPT.exe' OR Name='Codex.exe'" |
        Where-Object { $_.ExecutablePath -and (
            $_.ExecutablePath -like '*\OpenAI.Codex_*\app\*' -or
            $_.ExecutablePath -like '*\Programs\Codex-Provider-Patch\*' -or
            $_.ExecutablePath -like '*\ACL0815.CodexProviderPatch_*\*'
        ) })
    if ($CheckOnly) {
        if ($runningCodex.Count -gt 0) { Write-Output ('Konfiguration gueltig; Codex laeuft derzeit mit {0} Prozess(en). Fuer den Patch-Start muss die App zuerst normal beendet werden.' -f $runningCodex.Count) }
        else { Write-Output 'Konfiguration gueltig; Original-Paketidentitaet, gemeinsame Historie, Modellkatalog und Key-Datei sind startbereit.' }
        exit 0
    }
    if ($runningCodex.Count -gt 0) { throw 'Bitte die laufende Codex-Desktop-App vollstaendig beenden und diesen Starter danach erneut oeffnen. Der Starter beendet keine Aufgaben automatisch.' }
    if (-not $InPackage) {
        $packageShell = Join-Path $env:WINDIR 'System32\WindowsPowerShell\v1.0\powershell.exe'
        $innerArgs = '-NoProfile -ExecutionPolicy Bypass -File "' + $PSCommandPath +
            '" -InPackage -AppPath "' + $appPath +
            '" -CodexHome "' + $sharedCodexHome +
            '" -CatalogFile "' + $catalogPath +
            '" -KeyFile "' + $keyPath + '"'
        Invoke-CommandInDesktopPackage -PackageFamilyName $originalPackage.PackageFamilyName -AppId App -Command $packageShell -Args $innerArgs -PreventBreakaway
        exit 0
    }
    $previousKey = $env:OPENROUTER_API_KEY
    $previousHome = $env:CODEX_HOME
    $previousCatalog = $env:CODEX_CUSTOM_PROVIDER_MODEL_CATALOG
    try {
        $env:OPENROUTER_API_KEY = $testKey
        $env:CODEX_HOME = $sharedCodexHome
        $env:CODEX_CUSTOM_PROVIDER_MODEL_CATALOG = $catalogPath
        Start-Process -FilePath $appPath -WorkingDirectory (Split-Path $appPath) -WindowStyle Normal
    } finally {
        $env:OPENROUTER_API_KEY = $previousKey
        $env:CODEX_HOME = $previousHome
        $env:CODEX_CUSTOM_PROVIDER_MODEL_CATALOG = $previousCatalog
        $testKey = $null
    }
} catch {
    if ($CheckOnly) { Write-Error $_.Exception.Message }
    else {
        Add-Type -AssemblyName System.Windows.Forms
        [Windows.Forms.MessageBox]::Show($_.Exception.Message, 'Codex - OpenRouter', 'OK', 'Information') | Out-Null
    }
    exit 1
}
