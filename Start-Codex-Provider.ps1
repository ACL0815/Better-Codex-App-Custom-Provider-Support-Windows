param(
    [string]$AppPath = (Join-Path $env:LOCALAPPDATA 'Programs\Codex-Provider-Patch\ChatGPT.exe'),
    [string]$CodexHome = (Join-Path $env:USERPROFILE '.codex'),
    [string]$CatalogFile = (Join-Path $env:USERPROFILE '.codex-openrouter-test\openrouter-models.json'),
    [string]$RuntimeCatalogFile = (Join-Path $env:LOCALAPPDATA 'Codex Provider Patch\runtime-model-catalog.json'),
    [string]$KeyFile = (Join-Path $env:USERPROFILE '.codex\secrets\openrouter-api-key.txt'),
    [switch]$CheckOnly,
    [switch]$InPackage
)

$ErrorActionPreference = 'Stop'
$expectedPatchMarker = '__codexDesktopModelProvidersPatchV3'

function Get-Sha256([string]$Path) {
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

function Get-AsarHeaderSha256([string]$Path) {
    $stream = [IO.File]::OpenRead($Path)
    try {
        $reader = New-Object IO.BinaryReader($stream)
        $sizePayload = $reader.ReadUInt32()
        $headerPickleSize = $reader.ReadUInt32()
        if ($sizePayload -ne 4 -or $headerPickleSize -lt 8) { throw 'ungueltiger ASAR-Header' }
        $headerPickle = $reader.ReadBytes([int]$headerPickleSize)
        if ($headerPickle.Length -ne $headerPickleSize) { throw 'abgeschnittener ASAR-Header' }
        $headerPayloadSize = [BitConverter]::ToUInt32($headerPickle, 0)
        $headerStringSize = [BitConverter]::ToUInt32($headerPickle, 4)
        if ($headerPayloadSize -gt ($headerPickleSize - 4) -or $headerStringSize -gt ($headerPickle.Length - 8)) {
            throw 'ungueltige ASAR-Headergroesse'
        }
        $headerJson = New-Object byte[] $headerStringSize
        [Array]::Copy($headerPickle, 8, $headerJson, 0, $headerStringSize)
        [Text.Encoding]::UTF8.GetString($headerJson) | ConvertFrom-Json | Out-Null
        $sha = [Security.Cryptography.SHA256]::Create()
        try { return (($sha.ComputeHash($headerJson) | ForEach-Object { $_.ToString('x2') }) -join '') }
        finally { $sha.Dispose() }
    } catch {
        throw "Die ASAR-Integritaet konnte nicht gelesen werden: $($_.Exception.Message)"
    } finally {
        $stream.Dispose()
    }
}

function Test-FileContainsMarker([string]$Path, [string]$Marker) {
    $needle = [Text.Encoding]::ASCII.GetBytes($Marker)
    $stream = [IO.File]::OpenRead($Path)
    try {
        $buffer = New-Object byte[] (1024 * 1024 + $needle.Length - 1)
        $carry = 0
        while (($read = $stream.Read($buffer, $carry, $buffer.Length - $carry)) -gt 0) {
            $count = $carry + $read
            if ([Text.Encoding]::ASCII.GetString($buffer, 0, $count).IndexOf($Marker, [StringComparison]::Ordinal) -ge 0) { return $true }
            $carry = [Math]::Min($needle.Length - 1, $count)
            [Array]::Copy($buffer, $count - $carry, $buffer, 0, $carry)
        }
        return $false
    } finally {
        $stream.Dispose()
    }
}

function Read-JsonFile([string]$Path, [string]$Description) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { throw "$Description wurde nicht gefunden: $Path" }
    try { return (Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json) }
    catch { throw "$Description ist kein gueltiges JSON: $Path" }
}

function Merge-ModelCatalogs($BaseCatalog, $SupplementalCatalog) {
    $baseModels = @($BaseCatalog.models)
    $supplementalModels = @($SupplementalCatalog.models)
    if ($baseModels.Count -eq 0) { throw 'Der aktuelle Codex-Modellcache enthaelt keine Modelle.' }
    if ($supplementalModels.Count -eq 0) { throw 'Der ergaenzende Modellkatalog enthaelt keine Modelle.' }
    $baseSlugs = @{}
    foreach ($model in $baseModels) {
        $slug = [string]$model.slug
        if ([string]::IsNullOrWhiteSpace($slug) -or $baseSlugs.ContainsKey($slug)) { throw 'Der aktuelle Codex-Modellcache enthaelt leere oder doppelte Modell-Slugs.' }
        $baseSlugs[$slug] = $true
    }
    $supplementalSlugs = @{}
    $customModels = @()
    foreach ($model in $supplementalModels) {
        $slug = [string]$model.slug
        if ([string]::IsNullOrWhiteSpace($slug) -or $supplementalSlugs.ContainsKey($slug)) { throw 'Der ergaenzende Modellkatalog enthaelt leere oder doppelte Modell-Slugs.' }
        $supplementalSlugs[$slug] = $true
        if (-not $baseSlugs.ContainsKey($slug)) { $customModels += $model }
    }
    if ($customModels.Count -eq 0) { throw 'Der ergaenzende Modellkatalog enthaelt keine neuen Modell-Slugs.' }
    return [pscustomobject]@{
        Catalog = [pscustomobject]@{ models = @($baseModels + $customModels) }
        BaseCount = $baseModels.Count
        CustomCount = $customModels.Count
    }
}

function Write-JsonAtomic([string]$Path, $Value) {
    $directory = Split-Path $Path
    [IO.Directory]::CreateDirectory($directory) | Out-Null
    $temporary = Join-Path $directory ('.' + [IO.Path]::GetFileName($Path) + '.' + [guid]::NewGuid().ToString('N') + '.tmp')
    $backup = $temporary + '.previous'
    try {
        [IO.File]::WriteAllText($temporary, (($Value | ConvertTo-Json -Depth 100 -Compress) + "`n"), (New-Object Text.UTF8Encoding($false)))
        # PowerShell 5.1 converts a null backup argument into an invalid empty
        # path; a unique sibling backup keeps repeated catalog writes atomic.
        if (Test-Path -LiteralPath $Path) { [IO.File]::Replace($temporary, $Path, $backup) }
        else { [IO.File]::Move($temporary, $Path) }
    } finally {
        if (Test-Path -LiteralPath $temporary) { Remove-Item -LiteralPath $temporary -Force }
        if (Test-Path -LiteralPath $backup) { Remove-Item -LiteralPath $backup -Force }
    }
}

try {
    $sharedCodexHome = [IO.Path]::GetFullPath($CodexHome)
    $catalogPath = [IO.Path]::GetFullPath($CatalogFile)
    $runtimeCatalogPath = [IO.Path]::GetFullPath($RuntimeCatalogFile)
    $runtimeCatalogRoot = [IO.Path]::GetFullPath((Join-Path $env:LOCALAPPDATA 'Codex Provider Patch')).TrimEnd('\')
    if (-not $runtimeCatalogPath.StartsWith($runtimeCatalogRoot + '\', [StringComparison]::OrdinalIgnoreCase) -or
        [IO.Path]::GetExtension($runtimeCatalogPath) -ine '.json' -or $runtimeCatalogPath -ieq $catalogPath) {
        throw "Der Laufzeitkatalog muss eine eigene JSON-Datei unter $runtimeCatalogRoot sein."
    }
    $keyPath = [IO.Path]::GetFullPath($KeyFile)
    $appPath = [IO.Path]::GetFullPath($AppPath)
    $appRoot = Split-Path $appPath
    $patchManifestPath = Join-Path $appRoot 'codex-provider-patch.json'
    $patchedAsarPath = Join-Path $appRoot 'resources\app.asar'
    $originalPackage = Get-AppxPackage -Name 'OpenAI.Codex' | Select-Object -First 1
    if (-not $originalPackage) { throw 'Die originale OpenAI-Codex-App ist nicht installiert.' }
    if (-not (Test-Path -LiteralPath $appPath -PathType Leaf)) { throw 'Die externe gepatchte Codex-Kopie wurde nicht gefunden. Bitte den Windows-Patcher erneut ausfuehren.' }
    if (-not (Test-Path -LiteralPath $patchedAsarPath -PathType Leaf)) { throw 'Die gepatchte app.asar wurde nicht gefunden. Bitte den Windows-Patcher erneut ausfuehren.' }
    $patchManifest = Read-JsonFile $patchManifestPath 'Die Patch-Metadaten'
    if ([int]$patchManifest.format -ne 2) { throw 'Die Patch-Metadaten haben ein veraltetes Format. Bitte den Windows-Patcher erneut ausfuehren.' }
    if ([string]$patchManifest.layout -notmatch '^Windows Codex \d+\.\d+\.\d+\.\d+ Power Picker$') { throw 'Die Patch-Metadaten beschreiben kein unterstuetztes Windows-Layout.' }
    if ([string]$patchManifest.patch_marker -cne $expectedPatchMarker) { throw 'Die Patch-Metadaten enthalten nicht den erwarteten Patch-Marker.' }
    if ([string]$patchManifest.source_executable -cne 'ChatGPT.exe' -or [string]$patchManifest.executable -cne 'ChatGPT.exe') { throw 'Die Patch-Metadaten enthalten einen unerwarteten Programmdateinamen.' }
    $expectedSource = [IO.Path]::GetFullPath((Join-Path $originalPackage.InstallLocation 'app'))
    $recordedSource = [IO.Path]::GetFullPath([string]$patchManifest.source)
    if ($recordedSource.TrimEnd('\') -ine $expectedSource.TrimEnd('\') -or [string]$patchManifest.source_package_full_name -cne [string]$originalPackage.PackageFullName) {
        throw 'Die gepatchte Kopie gehoert nicht zur aktuell installierten Codex-Version. Bitte den Windows-Patcher erneut ausfuehren.'
    }
    $sourceExePath = Join-Path $expectedSource 'ChatGPT.exe'
    $sourceAsarPath = Join-Path $expectedSource 'resources\app.asar'
    if ((Get-Sha256 $sourceExePath) -cne [string]$patchManifest.source_executable_sha256 -or
        (Get-AsarHeaderSha256 $sourceAsarPath) -cne [string]$patchManifest.source_asar_header_sha256 -or
        (Get-Sha256 $appPath) -cne [string]$patchManifest.executable_sha256 -or
        (Get-AsarHeaderSha256 $patchedAsarPath) -cne [string]$patchManifest.asar_header_sha256 -or
        -not (Test-FileContainsMarker $patchedAsarPath $expectedPatchMarker)) {
        throw 'Die Patch-Integritaet ist ungueltig. Bitte den Windows-Patcher erneut ausfuehren.'
    }
    $sharedConfigPath = Join-Path $sharedCodexHome 'config.toml'
    if (-not (Test-Path -LiteralPath $sharedConfigPath -PathType Leaf)) { throw "Das gemeinsame Codex-Profil wurde nicht gefunden: $sharedCodexHome" }
    $sharedConfig = Get-Content -LiteralPath $sharedConfigPath -Raw
    if ($sharedConfig -match '(?m)^\s*model_catalog_json\s*=') { throw 'Die gemeinsame config.toml enthaelt model_catalog_json. Entferne diesen globalen Testkatalog zuerst, damit normale Codex-Starts weiter den aktuellen Standardkatalog verwenden.' }
    $baseCatalogPath = Join-Path $sharedCodexHome 'models_cache.json'
    $baseCatalog = Read-JsonFile $baseCatalogPath 'Der aktuelle Codex-Modellcache'
    $sourceCliVersion = [regex]::Match([string]$patchManifest.source_codex_cli_version, '^(\d+)\.(\d+)\.(\d+)$')
    $cacheCliVersion = [regex]::Match([string]$baseCatalog.client_version, '^(\d+)\.(\d+)\.(\d+)$')
    if (-not $sourceCliVersion.Success -or -not $cacheCliVersion.Success) {
        throw 'Die CLI-Version im Patch-Manifest oder Modellcache ist ungueltig. Bitte den Windows-Patcher erneut ausfuehren und den normalen Codex-Modellkatalog neu laden.'
    }
    if ([uint64]$sourceCliVersion.Groups[1].Value -ne [uint64]$cacheCliVersion.Groups[1].Value -or
        [uint64]$sourceCliVersion.Groups[2].Value -ne [uint64]$cacheCliVersion.Groups[2].Value -or
        [uint64]$cacheCliVersion.Groups[3].Value -lt [uint64]$sourceCliVersion.Groups[3].Value) {
        throw 'Der Modellcache passt nicht zur installierten Codex-Version. Starte Codex zuerst normal, bis der aktuelle Modellkatalog geladen wurde, beende die App und versuche es erneut.'
    }
    $supplementalCatalog = Read-JsonFile $catalogPath 'Der ergaenzende Modellkatalog'
    $mergedCatalog = Merge-ModelCatalogs $baseCatalog $supplementalCatalog
    $normalizedAppPath = $appPath.TrimEnd('\')
    $runningCodex = @(Get-CimInstance Win32_Process -Filter "Name='ChatGPT.exe' OR Name='Codex.exe'" | Where-Object {
        if (-not $_.ExecutablePath) { return $false }
        try { $processPath = [IO.Path]::GetFullPath([string]$_.ExecutablePath).TrimEnd('\') } catch { return $false }
        return ($processPath -ieq $normalizedAppPath -or $processPath -like '*\OpenAI.Codex_*\app\*' -or $processPath -like '*\Programs\Codex-Provider-Patch\*' -or $processPath -like '*\ACL0815.CodexProviderPatch_*\*')
    })
    if (-not $CheckOnly -and $runningCodex.Count -gt 0) { throw 'Bitte die laufende Codex-Desktop-App vollstaendig beenden und diesen Starter danach erneut oeffnen. Der Starter beendet keine Aufgaben automatisch.' }
    $testKey = $null
    if ($CheckOnly -or $InPackage) {
        if (-not (Test-Path -LiteralPath $keyPath -PathType Leaf)) { throw "Die OpenRouter-Key-Datei wurde nicht gefunden: $keyPath" }
        $testKey = [IO.File]::ReadAllText($keyPath).Trim()
        if ([string]::IsNullOrWhiteSpace($testKey) -or $testKey -eq 'HIER_DEINEN_OPENROUTER_API_KEY_EINFUEGEN') { throw 'Bitte zuerst den Platzhalter in .codex\secrets\openrouter-api-key.txt durch deinen OpenRouter API-Key ersetzen und speichern.' }
        if ($testKey -match '\s') { throw 'Die Key-Datei muss genau einen API-Key ohne Leerzeichen oder weitere Zeilen enthalten.' }
    }
    if ($CheckOnly) {
        $status = 'Konfiguration gueltig; Basis: {0}; benutzerdefiniert: {1}' -f $mergedCatalog.BaseCount, $mergedCatalog.CustomCount
        if ($runningCodex.Count -gt 0) { $status += '; Codex laeuft derzeit mit {0} Prozess(en) und muss vor dem Patch-Start normal beendet werden.' -f $runningCodex.Count }
        else { $status += '; Original-Paketidentitaet, gemeinsames Profil und Key-Datei sind startbereit.' }
        Write-Output $status
        exit 0
    }
    if (-not $InPackage) {
        $packageShell = Join-Path $env:WINDIR 'System32\WindowsPowerShell\v1.0\powershell.exe'
        $innerArgs = '-NoProfile -ExecutionPolicy Bypass -File "' + $PSCommandPath + '" -InPackage -AppPath "' + $appPath + '" -CodexHome "' + $sharedCodexHome + '" -CatalogFile "' + $catalogPath + '" -RuntimeCatalogFile "' + $runtimeCatalogPath + '" -KeyFile "' + $keyPath + '"'
        Invoke-CommandInDesktopPackage -PackageFamilyName $originalPackage.PackageFamilyName -AppId App -Command $packageShell -Args $innerArgs -PreventBreakaway
        exit 0
    }
    Write-JsonAtomic $runtimeCatalogPath $mergedCatalog.Catalog
    $env:OPENROUTER_API_KEY = $testKey
    $env:CODEX_HOME = $sharedCodexHome
    $env:CODEX_CUSTOM_PROVIDER_MODEL_CATALOG = $runtimeCatalogPath
    Start-Process -FilePath $appPath -WorkingDirectory $appRoot -WindowStyle Normal
} catch {
    if ($CheckOnly) { Write-Error $_.Exception.Message }
    else {
        Add-Type -AssemblyName System.Windows.Forms
        [Windows.Forms.MessageBox]::Show($_.Exception.Message, 'Codex - OpenRouter', 'OK', 'Information') | Out-Null
    }
    exit 1
}
