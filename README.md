# Better Codex App Custom Provider Support — Windows

[Deutsche Anleitung](README.de.md)

An experimental Windows adaptation of Keksuccino's custom provider patch for the ChatGPT/Codex desktop app. The patch adds a provider selector to the model menu so a **new task** can use a configured Codex model provider while the normal ChatGPT sign-in remains available for OpenAI models.

This tool builds a **separate, patched app copy**. It does not modify the installed app or produce a signed MSIX package. A copied Windows app may require its original package identity to launch. If the executable's ASAR integrity resource needs updating, that change invalidates its original digital signature. A successful patch run therefore does **not** establish that the copy will launch or that custom-provider requests will work on your installation.

> [!CAUTION]
> Provider selection is fixed when a task starts. Changing the selector in a running task does not move that task to another provider.

## Requirements

- Windows 10 or 11 and an installed ChatGPT/Codex desktop app with an Electron `app.asar`
- Python 3.9 or newer, available as `py` or `python`
- Node.js and `npx` on `PATH` (the tool uses `@electron/asar` to rebuild `app.asar`)
- Enough free disk space for an app copy, a backup, and temporary patch files

Windows Store/MSIX app directories, including `WindowsApps`, are treated as read-only sources. The output is a portable directory, not an installer or a repackaged MSIX. Launching that copy has not been verified across Windows package layouts. The patch also depends on internal JavaScript structures that can change with any app update.

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

If both checks pass, build the copy:

```powershell
py -3 .\patch_chatgpt_providers.py
```

If Python is installed without the `py` launcher, replace `py -3` with `python`. The default output location is `%LOCALAPPDATA%\Programs\Codex-Provider-Patch`; backups are stored under `%LOCALAPPDATA%\Codex Provider Patch Backups`. The command prints the exact paths it used.

Launch the desktop executable from the output directory to use the patched copy. In the 26.915 Owl build this is `ChatGPT.exe`; the original Start menu entry still opens the official installation. Creating the copy does not replace your shortcuts.

Use `--app` to select a source directory and `--output` to select a writable destination, for example:

```powershell
py -3 .\patch_chatgpt_providers.py --app "C:\Path\To\ChatGPT" --output "$env:LOCALAPPDATA\Programs\Codex-Provider-Patch"
```

Run `py -3 .\patch_chatgpt_providers.py --help` for all options. The tool checks the app layout and patch targets before writing the output. If a check fails, use the official app and wait for a patch update. Do not copy an older patched `app.asar` into a newer app release.

## Configure a custom Codex provider

Codex reads custom providers from `%USERPROFILE%\.codex\config.toml`, or from `%CODEX_HOME%\config.toml` when `CODEX_HOME` is set. Provider IDs such as `openrouter` are also used in the menu configuration below.

For example:

```toml
[model_providers.openrouter]
name = "OpenRouter"
base_url = "https://openrouter.ai/api/v1"
wire_api = "responses"
env_key = "OPENROUTER_API_KEY"
```

Set `OPENROUTER_API_KEY` in the Windows user environment or through a trusted secret manager before starting the app. Do not put an API key in `config.toml`, `desktop-model-providers.json`, a command line, or a committed file. If you use Codex's `[model_providers.openrouter.auth]` command configuration instead, remove `env_key`; these are alternate authentication methods. See the [Codex configuration reference](https://developers.openai.com/codex/config-advanced#custom-model-providers) for supported provider settings.

Leave the global `model_provider` unset if you want OpenAI and custom providers to coexist in the desktop app. The patch selects a provider when each new task starts.

## Make custom models available

Codex must know each model's metadata before it can appear in the model menu. A custom model catalog can be configured with `model_catalog_json`:

```powershell
New-Item -ItemType Directory -Force "$HOME\.codex\model-catalogs" | Out-Null
$catalog = codex debug models --bundled | Out-String
[System.IO.File]::WriteAllText("$HOME\.codex\model-catalogs\custom.json", $catalog, (New-Object System.Text.UTF8Encoding($false)))
```

Edit the top-level `models` array in `custom.json`. Copy an existing entry with similar capabilities and update its `slug`, display name, context window, modalities, reasoning levels, and tool support. The `slug` must be the exact model ID understood by the provider. Preserve other required fields and use the model's actual capabilities.

In `config.toml`, put `model_catalog_json` at the top level, **before any `[section]` headers**. Use an absolute Windows path. TOML literal strings avoid escaping backslashes:

```toml
model_catalog_json = 'C:\Users\YOUR_USERNAME\.codex\model-catalogs\custom.json'
```

Replace `YOUR_USERNAME` with your Windows user directory, or use the equivalent location under `CODEX_HOME`. Restart the app after changing the catalog. `codex debug models` shows the effective model catalog.

## Configure the provider menu

The tool creates `desktop-model-providers.json` in the effective Codex home directory. With default settings, the path is `%USERPROFILE%\.codex\desktop-model-providers.json`.

`--config` changes where the installer writes the JSON, not where the running app reads it. If you prepare a file elsewhere, copy it to the app's effective Codex home before use. Prefer the default location, or set the same `CODEX_HOME` for both the installer and the app.

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

App updates can change the JavaScript structures that the patch targets. Repeat `--check` and `--dry-run` against each new version before rebuilding the copy. Backups and the original installed app should be kept. To undo the modification, stop using the patched output directory and launch the official installation. If necessary, restore the output files from the backup directory printed by the tool.

When an Electron ASAR integrity resource is present, the patch verifies its original value and updates it in the copied executable. That edit cannot retain the executable's original digital signature. Builds without that resource leave their executables unchanged. Windows or app package checks may reject a modified copy, and this project does not bypass those checks.

## Verification

The port was checked on Windows against Codex package 26.915.4065.0: the full `--dry-run` extracted, patched, syntax-checked and repacked the real app archive, preserving its unpacked-file layout. All 13 regression tests passed, including generated JavaScript routing behavior and failed-publication rollback. Windows PE integrity updates were also round-tripped on a temporary executable copy.

Run the regression suite with `python -m unittest discover -s tests -v` (Node.js is needed for the JavaScript behavior test). GitHub Actions runs it on Windows with Python 3.9 and 3.12. App launch, signed-package installation and live custom-provider requests have **not** been verified.

## Origin and license

This Windows adaptation builds on Keksuccino's original macOS patch; the repository's Git history retains that implementation. The project is released under the [Unlicense](LICENSE).

This is an unofficial modification and is not affiliated with or supported by OpenAI. Use it at your own risk, and back up data you care about before patching.
