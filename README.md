# Better Codex App Custom Provider Support — Windows

[Deutsche Anleitung](README.de.md)

An experimental Windows adaptation of Keksuccino's custom provider patch for the ChatGPT/Codex desktop app. The patch adds a provider selector to the model menu so a **new task** can use a configured Codex model provider while the normal ChatGPT sign-in remains available for OpenAI models.

This tool builds a **separate, patched app copy**. It does not modify the installed app. The Windows Owl build requires package identity: launching `ChatGPT.exe` directly fails with `process has no package identity`, even from the registered package directory. A second helper builds and registers a complete local MSIX under its **own** publisher identity. Its GUI starts through the package context as shown below; provider routing inside the app remains unverified.

> [!CAUTION]
> Provider selection is fixed when a task starts. Changing the selector in a running task does not move that task to another provider.

## Requirements

- Windows 10 or 11 and an installed ChatGPT/Codex desktop app with an Electron `app.asar`
- Python 3.9 or newer, available as `py` or `python`
- Node.js and `npx` on `PATH` (the tool uses `@electron/asar` to rebuild `app.asar`)
- Windows SDK x64 tools `makeappx.exe` and `signtool.exe` for building and signing the separate MSIX
- Enough free disk space for an app copy, a backup, and temporary patch files

Windows Store/MSIX app directories, including `WindowsApps`, are treated as read-only sources. The Python output is a staging directory. The helper packages that copy under a different identity; it does not change or re-sign the original installed package. The patch also depends on internal JavaScript structures that can change with any app update.

The Windows-specific patch targets Codex package **26.915.4065.0** (internal app version **26.915.31945**). It routes **local tasks only**; remote and cloud tasks retain their original routing. Earlier upstream exact-match layouts are retained, but are not separately certified for Windows. Other builds are accepted only if one complete supported layout matches.

## Build the patched copy

Download this repository as a ZIP and extract it, or clone it. Keep the Python files together. Open PowerShell in the repository folder. Check the detected installation before creating any output:

```powershell
py -3 .\patch_chatgpt_providers.py --check
```

Then validate the full patch in a temporary directory:

```powershell
py -3 .\patch_chatgpt_providers.py --dry-run
```

If both checks pass, create a separate Codex home for the custom-provider test and build the copy:

```powershell
New-Item -ItemType Directory -Force "$HOME\.codex-openrouter-test" | Out-Null
py -3 .\patch_chatgpt_providers.py --config "$HOME\.codex-openrouter-test\desktop-model-providers.json"
```

If Python is installed without the `py` launcher, replace `py -3` with `python`. The default output location is `%LOCALAPPDATA%\Programs\Codex-Provider-Patch`; backups are stored under `%LOCALAPPDATA%\Codex Provider Patch Backups`. The command prints the exact paths it used.

The output directory is a staging copy. In the 26.915 Owl build, starting its `ChatGPT.exe` without identity fails. Build and register the separate MSIX below; the original Start menu entry still opens the official installation.

Use `--app` to select a source directory and `--output` to select a writable destination, for example:

```powershell
py -3 .\patch_chatgpt_providers.py --app "C:\Path\To\ChatGPT" --output "$env:LOCALAPPDATA\Programs\Codex-Provider-Patch"
```

Run `py -3 .\patch_chatgpt_providers.py --help` for all options. The tool checks the app layout and patch targets before writing the output. If a check fails, use the official app and wait for a patch update. Do not copy an older patched `app.asar` into a newer app release.

## Build and register the local MSIX

The Owl build checks Windows package identity at startup. `Register-Codex-PatchIdentity.ps1` packs the complete staged app into a local MSIX with its **own** identity (`ACL0815.CodexProviderPatch`) and signs that package with a dedicated certificate. It retains the source executable's original signed bytes, including when it needs to restore a previously modified staging copy. It does not change the installed ChatGPT package or set global Developer Mode.

The helper needs the Windows SDK tools listed above. It stores the signing certificate under `CurrentUser/My` and its public certificate under `CurrentUser/TrustedPeople`. On this host, package deployment rejected current-user trust alone with `0x800B0109`. The opt-in `-AllowMachineTrust` switch requests Windows administrator consent to trust **only this dedicated public certificate** in `LocalMachine/TrustedPeople`. It does not add a root certificate. Signing and registration remain under the current user. A passing Python `--dry-run` only verifies patch construction.

To build and register the separate package after creating the staging copy, from this repository in PowerShell:

```powershell
.\Register-Codex-PatchIdentity.ps1 -AllowMachineTrust
```

The default staging path is `%LOCALAPPDATA%\Programs\Codex-Provider-Patch`. Use `-AppPath` for a custom directory; generated package files go under `%LOCALAPPDATA%\Codex Provider Patch Identity` by default (`-WorkPath` changes it). Review the certificate scope and Windows consent prompt before continuing. The helper does not launch the app. Once registered, start it **inside its package context**:

```powershell
$pkg = Get-AppxPackage -Name ACL0815.CodexProviderPatch
Invoke-CommandInDesktopPackage -PackageFamilyName $pkg.PackageFamilyName -AppId App -Command (Join-Path $pkg.InstallLocation 'app\ChatGPT.exe')
```

On the tested 26.915 Owl build, this command started a responsive window with GPU and renderer processes that stayed alive for more than 30 seconds. Starting the EXE directly, including from `$pkg.InstallLocation`, did not give it package identity. Do not add `-PreventBreakaway` to this basic launch command. This basic launch does not carry environment variables from the calling PowerShell into the packaged process. Use the provider launcher below when the app needs `OPENROUTER_API_KEY` or a custom `CODEX_HOME`.

## Configure a custom Codex provider

Keep the custom-provider setup in a separate home, for example `%USERPROFILE%\.codex-openrouter-test`. The packaged launcher sets `CODEX_HOME` and `CODEX_ELECTRON_USER_DATA_PATH` for that home; Codex then reads its `config.toml` and keeps a separate desktop profile and history. You may need to sign in within that profile. This leaves the normal `%USERPROFILE%\.codex` model preferences and catalog alone. Provider IDs such as `openrouter` are also used in the menu configuration below.

For example:

```toml
[model_providers.openrouter]
name = "OpenRouter"
base_url = "https://openrouter.ai/api/v1"
wire_api = "responses"
env_key = "OPENROUTER_API_KEY"
```

For the packaged app, save the API key as the only line of a private file outside this repository, such as `%USERPROFILE%\.codex\secrets\openrouter-api-key.txt`, and keep that file accessible only to your Windows user. The package-start command above does **not** inherit `OPENROUTER_API_KEY` or `CODEX_HOME` set in the parent PowerShell. The `Start-Codex-Provider.ps1` launcher reads the key **inside** the package context and sets the process environment before starting the app:

```powershell
.\Start-Codex-Provider.ps1 -KeyFile "$HOME\.codex\secrets\openrouter-api-key.txt" -CodexHome "$HOME\.codex-openrouter-test"
```

These are the launcher's default paths and may be omitted. The key stays under the normal user profile while `CODEX_HOME` and the desktop profile point to the isolated test home. Add `-CheckOnly` to validate the key file and installed package without launching the app or making an API request. The launcher uses a second process inside the package to set the environment; setting `$env:OPENROUTER_API_KEY` before the basic `Invoke-CommandInDesktopPackage` call is not sufficient.

Do not put the key in `config.toml`, `desktop-model-providers.json`, a command-line argument, or a committed file. If you use Codex's `[model_providers.openrouter.auth]` command configuration instead, remove `env_key`; these are alternate authentication methods. See the [Codex configuration reference](https://developers.openai.com/codex/config-advanced#custom-model-providers) for supported provider settings.

Leave `model_provider` unset in the isolated `config.toml` if OpenAI and custom providers should coexist in this app. The patch selects a provider when each new task starts. The provider menu's **Automatic** choice maps an already-selected model to a provider; it does not pick between Astra and Sol models.

## Make custom models available

Codex must know each model's metadata before it can appear in the model menu. Create a test catalog from the **current effective** model list, then add your custom model. Keep this override in the isolated home; a global `model_catalog_json` can replace the normal model list with a stale snapshot.

```powershell
New-Item -ItemType Directory -Force "$HOME\.codex-openrouter-test" | Out-Null
$catalog = codex debug models | Out-String
[System.IO.File]::WriteAllText("$HOME\.codex-openrouter-test\openrouter-models.json", $catalog, (New-Object System.Text.UTF8Encoding($false)))
```

Edit the top-level `models` array in `openrouter-models.json`. Copy an existing entry with similar capabilities and update its `slug`, display name, context window, modalities, reasoning levels, and tool support. The `slug` must be the exact model ID understood by the provider. Preserve other required fields and use the model's actual capabilities. Rebuild this isolated catalog when the normal app's model list changes.

In the isolated `config.toml`, put `model_catalog_json` at the top level, **before any `[section]` headers**. Use an absolute Windows path. TOML literal strings avoid escaping backslashes:

```toml
model_catalog_json = 'C:\Users\YOUR_USERNAME\.codex-openrouter-test\openrouter-models.json'
```

Replace `YOUR_USERNAME` with your Windows user directory. Restart the patched app after changing the catalog. `codex debug models` shows the normal effective catalog; launch that command with the isolated `CODEX_HOME` to inspect the test catalog.

## Configure the provider menu

The tool creates `desktop-model-providers.json` at the path selected by `--config`. In the example above it is `%USERPROFILE%\.codex-openrouter-test\desktop-model-providers.json`.

`--config` changes where the installer writes the JSON, not where the running app reads it. Keep that file in the same isolated home passed as `-CodexHome` to the launcher.

Example:

```json
{
  "version": 1,
  "default_provider": "openai",
  "providers": [
    {
      "id": "openai",
      "label": "ChatGPT / OpenAI",
      "description": "Uses your signed-in ChatGPT account"
    },
    {
      "id": "openrouter",
      "label": "OpenRouter",
      "description": "Uses [model_providers.openrouter] from config.toml"
    }
  ],
  "model_providers": {
    "moonshotai/kimi-k3": "openrouter"
  }
}
```

`providers` controls the menu entries. `model_providers` maps exact model slugs to provider IDs for Automatic mode. `default_provider` handles models with no explicit mapping. Every custom provider ID must have a matching `[model_providers.<id>]` section in `config.toml`. API keys do not belong in this JSON file.

The patched app reloads the menu file when the menu opens and before a new task starts, so editing this file does not require rebuilding the app copy.

## Updates and recovery

App updates can change the JavaScript structures that the patch targets. Repeat `--check` and `--dry-run` against each new version before rebuilding the copy. Backups and the original installed app should be kept. To undo the patch, remove the separate package registration and its certificate trust, then launch the official installation. Restore staging files from the backup directory if necessary. Merely deleting the staging directory leaves the package and certificate trust registered.

When an Electron ASAR integrity resource is present, the Python patch verifies its original value and updates it in the staging executable. That edit cannot retain the executable's original digital signature. The MSIX helper packages the original signed EXE bytes with the patched app resources and signs the **new package** using its dedicated local certificate. Builds without the ASAR integrity resource leave their staging executables unchanged.

## Verification

The port was checked on Windows against Codex package 26.915.4065.0: the full `--dry-run` extracted, patched, syntax-checked and repacked the real app archive, preserving its unpacked-file layout. All 13 regression tests passed, including generated JavaScript routing behavior and failed-publication rollback. Windows PE integrity updates were also round-tripped on a temporary executable copy.

Run the regression suite with `python -m unittest discover -s tests -v` (Node.js is needed for the JavaScript behavior test). GitHub Actions runs it on Windows with Python 3.9 and 3.12. The registered package's GUI, GPU, and renderer processes were observed responding for more than 30 seconds on the tested Owl build. A separate OpenRouter Responses API request succeeded. An OpenRouter task in the patched app and end-to-end provider routing have **not yet** been verified.

## Origin and license

This Windows adaptation builds on Keksuccino's original macOS patch; the repository's Git history retains that implementation. The project is released under the [Unlicense](LICENSE).

This is an unofficial modification and is not affiliated with or supported by OpenAI. Use it at your own risk, and back up data you care about before patching.
