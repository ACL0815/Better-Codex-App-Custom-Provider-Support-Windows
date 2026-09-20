#requires -Version 5.1
<#
.SYNOPSIS
Build and register a separate locally signed MSIX for the patched Windows app.
.DESCRIPTION
The official Codex package is left in place. Only the dedicated local signing
certificate can require elevation, and only with -AllowMachineTrust. Start the
app with package-aware activation. Set required environment variables inside
the activated wrapper, because activation does not inherit the caller's values.
#>
[CmdletBinding()]
param(
    [string]$AppPath = (Join-Path $env:LOCALAPPDATA 'Programs\Codex-Provider-Patch'),
    [string]$WorkPath = (Join-Path $env:LOCALAPPDATA 'Codex Provider Patch Identity'),
    [switch]$AllowMachineTrust
)

$ErrorActionPreference = 'Stop'
$packageName = 'ACL0815.CodexProviderPatch'
$publisher = 'CN=Codex Provider Patch Local Test'
$appId = 'App'
$appRoot = (Resolve-Path -LiteralPath $AppPath).Path.TrimEnd('\')
$exePath = Join-Path $appRoot 'ChatGPT.exe'
$patchMetadata = Join-Path $appRoot 'codex-provider-patch.json'
if ($appRoot -match '(?i)(^|\\)WindowsApps(\\|$)' -or -not (Test-Path -LiteralPath $patchMetadata)) {
    throw 'The target must be a separate copy created by the provider patch installer.'
}
if (-not (Test-Path -LiteralPath $exePath -PathType Leaf)) { throw "Missing copied executable: $exePath" }
$running = Get-CimInstance Win32_Process | Where-Object { $_.ExecutablePath -eq $exePath }
if ($running) { throw 'Close the patched app before registering its identity.' }

$sdkRoot = Join-Path ${env:ProgramFiles(x86)} 'Windows Kits\10\bin'
$sdk = Get-ChildItem -LiteralPath $sdkRoot -Directory |
    Where-Object { $_.Name -match '^10\.0\.\d+\.0$' } |
    Sort-Object { [version]$_.Name } -Descending |
    Where-Object {
        (Test-Path -LiteralPath (Join-Path $_.FullName 'x64\makeappx.exe')) -and
        (Test-Path -LiteralPath (Join-Path $_.FullName 'x64\signtool.exe'))
    } | Select-Object -First 1
if (-not $sdk) { throw 'Windows SDK x64 makeappx.exe and signtool.exe are required.' }
$sdkBin = Join-Path $sdk.FullName 'x64'
function Invoke-SdkTool([string]$Name, [string[]]$Arguments) {
    & (Join-Path $sdkBin $Name) @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Name failed with exit code $LASTEXITCODE" }
}

$installedOriginal = Get-AppxPackage -Name OpenAI.Codex | Select-Object -First 1
$originalIdentity = if ($installedOriginal) { $installedOriginal.PackageFullName } else { $null }
$existing = Get-AppxPackage -Name $packageName | Select-Object -First 1
if ($existing -and $existing.Publisher -ne $publisher) { throw 'An unrelated package already uses the patch package name.' }
if ($existing) {
    $installedExe = Join-Path $existing.InstallLocation 'app\ChatGPT.exe'
    if (Get-CimInstance Win32_Process | Where-Object { $_.ExecutablePath -eq $installedExe }) {
        throw 'Close the installed provider patch app before replacing its package.'
    }
}
$version = '1.0.0.0'
if ($existing) {
    $v = [version]$existing.Version
    if ($v.Revision -ge 65534) { throw 'Identity package revision exhausted.' }
    $version = '{0}.{1}.{2}.{3}' -f $v.Major,$v.Minor,$v.Build,($v.Revision+1)
}
$workRoot = [System.IO.Path]::GetFullPath($WorkPath)
if ($workRoot -match '(?i)(^|\\)WindowsApps(\\|$)') { throw 'WorkPath cannot be inside WindowsApps.' }
if ($workRoot.TrimEnd('\') -eq $appRoot -or $workRoot.StartsWith($appRoot + '\',[StringComparison]::OrdinalIgnoreCase)) {
    throw 'WorkPath must be outside the application copy so its build outputs cannot enter the package.'
}
New-Item -ItemType Directory -Path $workRoot -Force | Out-Null
$runRoot = Join-Path $workRoot ('identity-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '-' + [guid]::NewGuid().ToString('N').Substring(0,8))
$packageRoot = Join-Path $runRoot 'package'
New-Item -ItemType Directory -Path $packageRoot -Force | Out-Null
$backupExe = Join-Path $runRoot 'ChatGPT.before-registration.exe'
Copy-Item -LiteralPath $exePath -Destination $backupExe
$beforeHash = (Get-FileHash -LiteralPath $exePath -Algorithm SHA256).Hash
$sourceApp = (Get-Content -LiteralPath $patchMetadata -Raw | ConvertFrom-Json).source
$sourceExe = Join-Path $sourceApp 'ChatGPT.exe'
$sourceHash = (Get-FileHash -LiteralPath $sourceExe -Algorithm SHA256).Hash
$exeBytes = [System.IO.File]::ReadAllBytes($sourceExe)
if ($exeBytes.Length -lt 64) { throw 'The source executable is not a valid PE image.' }
$peOffset = [BitConverter]::ToInt32($exeBytes, 0x3C)
if ($peOffset -lt 0 -or $peOffset + 6 -gt $exeBytes.Length -or
    [BitConverter]::ToUInt32($exeBytes, $peOffset) -ne 0x00004550 -or
    [BitConverter]::ToUInt16($exeBytes, $peOffset + 4) -ne 0x8664) {
    throw 'This identity manifest supports only an x64 Windows source executable.'
}
$exeBytes = $null
$identityMetadataPath = Join-Path $appRoot 'codex-provider-identity.json'
$previousMetadata = if (Test-Path -LiteralPath $identityMetadataPath) {
    Get-Content -LiteralPath $identityMetadataPath -Raw | ConvertFrom-Json
} else { $null }
$pristineBackup = $backupExe
$restoreExeSource = $null
if ($beforeHash -ne $sourceHash) {
    # Migrate only the known earlier embedded-identity copy, never overwrite
    # arbitrary EXE edits. The saved original must match the installed source.
    if (-not $previousMetadata -or -not (Test-Path -LiteralPath $previousMetadata.executableBackup)) {
        throw 'The copied EXE differs from the source and has no verified original backup.'
    }
    if ((Get-FileHash -LiteralPath $previousMetadata.executableBackup -Algorithm SHA256).Hash -ne $sourceHash) {
        throw 'The original EXE backup does not match the installed source executable.'
    }
    $restoreExeSource = $previousMetadata.executableBackup
    $pristineBackup = $restoreExeSource
}

$assetsName = 'ProviderIdentityAssets'
$assetsSource = Join-Path (Split-Path -Parent $sourceApp) 'assets'
$assetFiles = @('icon.png','Square44x44Logo.png','Square150x150Logo.png')
foreach ($asset in $assetFiles) {
    if (-not (Test-Path -LiteralPath (Join-Path $assetsSource $asset))) { throw "Missing source identity logo: $asset" }
}
$manifest = @"
<?xml version="1.0" encoding="utf-8"?>
<Package xmlns="http://schemas.microsoft.com/appx/manifest/foundation/windows10"
 xmlns:uap="http://schemas.microsoft.com/appx/manifest/uap/windows10"
 xmlns:desktop6="http://schemas.microsoft.com/appx/manifest/desktop/windows10/6"
 xmlns:rescap="http://schemas.microsoft.com/appx/manifest/foundation/windows10/restrictedcapabilities"
 IgnorableNamespaces="uap desktop6 rescap">
 <Identity Name="$packageName" Publisher="$publisher" Version="$version" ProcessorArchitecture="x64" />
 <Properties><DisplayName>Codex Provider Patch</DisplayName><PublisherDisplayName>Local Codex Provider Patch</PublisherDisplayName><Logo>assets\icon.png</Logo><desktop6:RegistryWriteVirtualization>disabled</desktop6:RegistryWriteVirtualization><desktop6:FileSystemWriteVirtualization>disabled</desktop6:FileSystemWriteVirtualization></Properties>
 <Resources><Resource Language="en-US" /></Resources>
 <Dependencies><TargetDeviceFamily Name="Windows.Desktop" MinVersion="10.0.19041.0" MaxVersionTested="10.0.26100.0" /></Dependencies>
 <Capabilities><rescap:Capability Name="runFullTrust" /><rescap:Capability Name="unvirtualizedResources" /><Capability Name="internetClient" /></Capabilities>
 <Applications><Application Id="$appId" Executable="app\ChatGPT.exe" EntryPoint="Windows.FullTrustApplication">
  <uap:VisualElements DisplayName="Codex Provider Patch" Description="Local custom-provider copy" BackgroundColor="transparent" Square150x150Logo="assets\Square150x150Logo.png" Square44x44Logo="assets\Square44x44Logo.png" />
 </Application></Applications>
</Package>
"@
$manifestPath = Join-Path $packageRoot 'AppxManifest.xml'
[System.IO.File]::WriteAllText($manifestPath,$manifest,(New-Object System.Text.UTF8Encoding($false)))
$packagePath = Join-Path $runRoot 'CodexProviderPatch.msix'
# A mapping packs the full application without duplicating its payload in a
# staging directory. Only this generated manifest defines Windows integration.
$mapping = New-Object System.Collections.Generic.List[string]
$mapping.Add('[Files]')
$mapping.Add(('"{0}" "AppxManifest.xml"' -f $manifestPath))
foreach ($asset in $assetFiles) {
    $mapping.Add(('"{0}" "assets\{1}"' -f (Join-Path $assetsSource $asset),$asset))
}
foreach ($file in Get-ChildItem -LiteralPath $appRoot -File -Recurse) {
    $relative = $file.FullName.Substring($appRoot.Length + 1)
    if ($relative -in @('AppxManifest.xml','codex-provider-identity.json','codex-provider-patch.json') -or
        $relative.StartsWith($assetsName + '\',[StringComparison]::OrdinalIgnoreCase)) { continue }
    $fileSource = if ($relative -eq 'ChatGPT.exe' -and $restoreExeSource) { $restoreExeSource } else { $file.FullName }
    $mapping.Add(('"{0}" "app\{1}"' -f $fileSource,$relative))
}
$mappingPath = Join-Path $runRoot 'package-mapping.txt'
[System.IO.File]::WriteAllLines($mappingPath,$mapping,(New-Object System.Text.UTF8Encoding($false)))
Invoke-SdkTool -Name 'makeappx.exe' -Arguments @('pack','/o','/f',$mappingPath,'/p',$packagePath)

$cert = $null
$createdCert = $false
$addedTrust = $false
$addedMachineTrust = $false
$copiedExe = $false
$registered = $false
$removedPrevious = $false
$trustHelper = Join-Path $runRoot 'Set-PatchCertificateTrust.ps1'
$trustHelperText = @'
#requires -Version 5.1
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$CertificatePath,
    [Parameter(Mandatory=$true)][ValidatePattern('^[0-9A-Fa-f]{40}$')][string]$ExpectedThumbprint,
    [Parameter(Mandatory=$true)][ValidateSet('Import','Remove')][string]$Action
)
$ErrorActionPreference='Stop'
try {
    $cert=Get-PfxCertificate -FilePath $CertificatePath
    if ($cert.Thumbprint -ne $ExpectedThumbprint -or $cert.Subject -ne 'CN=Codex Provider Patch Local Test') {
        throw 'Certificate fingerprint or subject does not match the approved patch certificate.'
    }
    if ($cert.HasPrivateKey) { throw 'The trust helper accepts public certificates only.' }
    $codeSigning=@($cert.EnhancedKeyUsageList | Where-Object { $_.ObjectId -eq '1.3.6.1.5.5.7.3.3' })
    if ($codeSigning.Count -ne 1) { throw 'The certificate does not have the Code Signing EKU.' }
    $target='Cert:\LocalMachine\TrustedPeople\'+$ExpectedThumbprint
    if ($Action -eq 'Import') {
        Import-Certificate -FilePath $CertificatePath -CertStoreLocation Cert:\LocalMachine\TrustedPeople | Out-Null
        if (-not (Test-Path -LiteralPath $target)) { throw 'Machine certificate trust could not be verified.' }
    } elseif (Test-Path -LiteralPath $target) {
        $existing=Get-Item -LiteralPath $target
        if ($existing.Subject -ne $cert.Subject -or $existing.Thumbprint -ne $cert.Thumbprint) {
            throw 'The existing certificate differs from the approved patch certificate.'
        }
        Remove-Item -LiteralPath $target
    }
    exit 0
} catch {
    $_ | Out-String | Write-Error
    exit 1
}
'@
[System.IO.File]::WriteAllText($trustHelper,$trustHelperText,(New-Object System.Text.UTF8Encoding($false)))
function Invoke-MachineCertificateTrust([string]$Action) {
    # Only this dedicated public certificate helper is elevated. Package signing,
    # registration, and the app process continue as the original desktop user.
    $helperArguments=@('-NoLogo','-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass',
        '-File',('"'+$trustHelper+'"'),'-CertificatePath',('"'+$publicCertificate+'"'),
        '-ExpectedThumbprint',$cert.Thumbprint,'-Action',$Action)
    $helperProcess=Start-Process -FilePath (Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe') `
        -ArgumentList $helperArguments -Verb RunAs -WindowStyle Hidden -Wait -PassThru
    if ($helperProcess.ExitCode -ne 0) { throw "Certificate trust helper failed with exit code $($helperProcess.ExitCode)." }
}
try {
    $cert = Get-ChildItem -LiteralPath Cert:\CurrentUser\My -CodeSigningCert |
        Where-Object { $_.Subject -eq $publisher -and $_.HasPrivateKey -and $_.NotAfter -gt (Get-Date).AddDays(7) } |
        Sort-Object NotAfter -Descending | Select-Object -First 1
    if (-not $cert) {
        $cert = New-SelfSignedCertificate -Type CodeSigningCert -Subject $publisher `
            -CertStoreLocation Cert:\CurrentUser\My -KeyAlgorithm RSA -KeyLength 2048 `
            -HashAlgorithm SHA256 -KeyExportPolicy NonExportable -NotAfter (Get-Date).AddYears(2)
        $createdCert = $true
    }
    $publicCertificate = Join-Path $runRoot 'CodexProviderPatch.cer'
    Export-Certificate -Cert $cert -FilePath $publicCertificate | Out-Null
    $trustedPath = 'Cert:\CurrentUser\TrustedPeople\' + $cert.Thumbprint
    if (-not (Test-Path -LiteralPath $trustedPath)) {
        Import-Certificate -FilePath $publicCertificate -CertStoreLocation Cert:\CurrentUser\TrustedPeople | Out-Null
        $addedTrust = $true
    }
    $machinePath = 'Cert:\LocalMachine\TrustedPeople\' + $cert.Thumbprint
    if ($AllowMachineTrust) {
        if (-not (Test-Path -LiteralPath $machinePath)) {
            Write-Host 'Windows consent is required to trust this one local test certificate in LocalMachine\TrustedPeople.'
            try { Invoke-MachineCertificateTrust -Action 'Import' }
            finally { $addedMachineTrust = Test-Path -LiteralPath $machinePath }
        }
    }
    Invoke-SdkTool -Name 'signtool.exe' -Arguments @('sign','/fd','SHA256','/sha1',$cert.Thumbprint,'/s','My',$packagePath)
    if ((Get-FileHash -LiteralPath $exePath -Algorithm SHA256).Hash -ne $beforeHash) { throw 'The target EXE changed during preparation.' }
    if ($restoreExeSource) {
        Copy-Item -LiteralPath $restoreExeSource -Destination $exePath -Force
        $copiedExe = $true
    }
    if ((Get-FileHash -LiteralPath $exePath -Algorithm SHA256).Hash -ne $sourceHash) {
        throw 'The executable must remain byte-identical to the original signed application.'
    }
    if ($existing) {
        if (-not $previousMetadata -or -not (Test-Path -LiteralPath $previousMetadata.identityPackage)) {
            throw 'The previous local package installer is needed for rollback before replacing this package.'
        }
        $current = Get-AppxPackage -Name $packageName | Select-Object -First 1
        if ($current.PackageFullName -ne $existing.PackageFullName -or $current.Publisher -ne $publisher) {
            throw 'The local package changed during preparation.'
        }
        Remove-AppxPackage -Package $existing.PackageFullName
        $removedPrevious = $true
    }
    Add-AppxPackage -Path $packagePath
    $package = Get-AppxPackage -Name $packageName | Select-Object -First 1
    if (-not $package -or $package.Publisher -ne $publisher -or $package.Version.ToString() -ne $version) {
        throw 'The requested identity package could not be verified after registration.'
    }
    $registered = $true
    $originalNow = Get-AppxPackage -Name OpenAI.Codex | Select-Object -First 1
    if ($originalIdentity -and $originalNow.PackageFullName -ne $originalIdentity) { throw 'The official package identity changed unexpectedly.' }
    $result = [ordered]@{
        format=1; status='registered'; packageName=$packageName; packageFullName=$package.PackageFullName
        packageFamilyName=$package.PackageFamilyName; appId=$appId; externalLocation=$appRoot
        certificateSubject=$publisher; certificateThumbprint=$cert.Thumbprint
        certificateStores=@('CurrentUser\My','CurrentUser\TrustedPeople') + $(if (Test-Path -LiteralPath $machinePath) { @('LocalMachine\TrustedPeople') } else { @() })
        machineCertificateThumbprint=$(if (Test-Path -LiteralPath $machinePath) { $cert.Thumbprint } else { $null })
        machineTrustAddedThisRun=$addedMachineTrust; certificateTrustHelper=$trustHelper
        publicCertificate=$publicCertificate
        executableBackup=$pristineBackup; previousExecutableBackup=$backupExe
        activationMethod='packageExecutable'; installedAppPath=(Join-Path $package.InstallLocation 'app')
        launchMethod='Invoke-CommandInDesktopPackage'
        launchCommand=("Invoke-CommandInDesktopPackage -PackageFamilyName '{0}' -AppId '{1}' -Command '{2}'" -f $package.PackageFamilyName,$appId,(Join-Path $package.InstallLocation 'app\ChatGPT.exe'))
        identityPackage=$packagePath; officialPackage=$originalIdentity
        executableSha256=(Get-FileHash -LiteralPath $exePath -Algorithm SHA256).Hash
    }
    $resultJson = $result | ConvertTo-Json -Depth 5
    [System.IO.File]::WriteAllText((Join-Path $appRoot 'codex-provider-identity.json'),$resultJson,(New-Object System.Text.UTF8Encoding($false)))
    Write-Output $resultJson
    Write-Host ('Launch with package identity: ' + $result.launchCommand)
    Write-Host 'Set required environment variables inside the activated launcher wrapper; package activation does not inherit the caller environment.'
} catch {
    if (-not $registered) {
        if ($copiedExe) { Copy-Item -LiteralPath $backupExe -Destination $exePath -Force }
        if ($removedPrevious) {
            try {
                if ($previousMetadata.activationMethod -eq 'packageExecutable') {
                    Add-AppxPackage -Path $previousMetadata.identityPackage
                } else {
                    Add-AppxPackage -Path $previousMetadata.identityPackage -ExternalLocation $appRoot
                }
            } catch {
                Write-Warning ('Previous package reinstall failed. Its saved installer is: ' + $previousMetadata.identityPackage)
            }
        }
        if ($addedMachineTrust -and $cert) {
            try { Invoke-MachineCertificateTrust -Action 'Remove' }
            catch {
                Write-Warning ('Automatic removal needs administrator consent. Remove only this certificate: Cert:\LocalMachine\TrustedPeople\' + $cert.Thumbprint)
                Write-Warning ('Elevated cleanup: & "' + $trustHelper + '" -CertificatePath "' + $publicCertificate + '" -ExpectedThumbprint ' + $cert.Thumbprint + ' -Action Remove')
            }
        }
        if ($addedTrust -and $cert) { Remove-Item -LiteralPath ('Cert:\CurrentUser\TrustedPeople\' + $cert.Thumbprint) }
        if ($createdCert -and $cert) { Remove-Item -LiteralPath ('Cert:\CurrentUser\My\' + $cert.Thumbprint) }
    }
    throw
}
