# Better Codex App Custom Provider Support — Windows

[Deutsche Anleitung](README.de.md)

An experimental Windows adaptation of Keksuccino's custom provider patch for the ChatGPT/Codex desktop app. The patch adds a provider selector to the model menu so a **new task** can use a configured Codex model provider while the normal ChatGPT sign-in remains available for OpenAI models.

This tool builds a **separate, patched app copy**. It does not modify the installed app. The launcher runs that external copy in the original `OpenAI.Codex` package context, while the model catalog override and API key apply only to that process. `CODEX_HOME` remains `%USERPROFILE%\.codex`, and the original package context selects the same durable desktop profile location used by the official app.

> [!CAUTION]
> Provider selection is fixed when a task starts. Changing the selector in a running task does not move that task to another provider.

## Requirements

- Windows 10 or 11 and an installed ChatGPT/Codex desktop app with an Electron `app.asar`
- Python 3.9 or newer, available as `py` or `python`
- Node.js and `npx` on `PATH` (the tool uses `@electron/asar` to rebuild `app.asar`)
- Enough free disk space for an app copy, a backup, and temporary patch files

Windows Store/MSIX app directories, including `WindowsApps`, are treated as read-only sources. The output is a writable external copy. The launcher validates that it was created from the currently installed package before starting it. The patch also depends on internal JavaScript structures that can change with any app update.

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

Do not start `ChatGPT.exe` directly: the Owl build exits with `process has no package identity`. Use `Start-Codex-Provider.ps1` below. The original Start menu entry continues to open the official installation.

For the shared-profile launcher, the patch source must be the `app` directory of the currently installed `OpenAI.Codex` package. The launcher verifies this against `codex-provider-patch.json`; copies built from arbitrary sources are rejected. You may choose another writable `--output` directory, but must then pass its executable to the launcher with `-AppPath`:

```powershell
py -3 .\patch_chatgpt_providers.py --output "D:\Apps\Codex-Provider-Patch"
.\Start-Codex-Provider.ps1 -AppPath "D:\Apps\Codex-Provider-Patch\ChatGPT.exe" -CheckOnly
```

Run `py -3 .\patch_chatgpt_providers.py --help` for all options. The tool checks the app layout and patch targets before writing the output. If a check fails, use the official app and wait for a patch update. Do not copy an older patched `app.asar` into a newer app release.

## Launch with the original package identity

Close the official app completely, then run:

```powershell
.\Start-Codex-Provider.ps1 -CheckOnly
.\Start-Codex-Provider.ps1
```

The launcher never terminates app processes itself. It refuses to start while the official app, an older locally packaged copy, or another portable copy is running. It validates the installed `OpenAI.Codex` package, the external patched copy and its source metadata, the shared Codex configuration, model catalog, and key file.

The outer launcher enters the original package context with `Invoke-CommandInDesktopPackage`. A second PowerShell process inside that context sets `OPENROUTER_API_KEY`, the shared `CODEX_HOME`, and the process-only `CODEX_CUSTOM_PROVIDER_MODEL_CATALOG`, then starts the external patched EXE. Do not set `CODEX_ELECTRON_USER_DATA_PATH`: the original package identity must select the official app's virtualized desktop profile location.

An earlier version of this project installed a separate package named `ACL0815.CodexProviderPatch`. That route remains available for existing installations through `Register-Codex-PatchIdentity.ps1`, but it uses a different Windows profile domain and is not the recommended shared-history path. You do not need to rebuild or delete that package before testing the new launcher; simply close it.

## Configure a custom Codex provider

Keep the provider definition in the normal `%USERPROFILE%\.codex\config.toml`, but do not set a global `model_catalog_json`. The launcher uses the same Codex home and adds the custom catalog only to the patched app-server process. Provider IDs such as `openrouter` are also used in the menu configuration below.

For example:

```toml
[model_providers.openrouter]
name = "OpenRouter"
base_url = "https://openrouter.ai/api/v1"
wire_api = "responses"
env_key = "OPENROUTER_API_KEY"
```

Save the API key as the only line of `%USERPROFILE%\.codex\secrets\openrouter-api-key.txt` and keep that file accessible only to your Windows user. The launcher reads the key inside the original package context:

```powershell
.\Start-Codex-Provider.ps1 -KeyFile "$HOME\.codex\secrets\openrouter-api-key.txt" -CodexHome "$HOME\.codex" -CatalogFile "$HOME\.codex-openrouter-test\openrouter-models.json"
```

`-AppPath` defaults to `%LOCALAPPDATA%\Programs\Codex-Provider-Patch\ChatGPT.exe`; the other paths above are also defaults and may be omitted. Add `-CheckOnly` to validate them without launching the app or making an API request. Setting `$env:OPENROUTER_API_KEY` before calling `Invoke-CommandInDesktopPackage` is not sufficient because that command does not inherit the caller's environment.

Do not put the key in `config.toml`, `desktop-model-providers.json`, a command-line argument, or a committed file. If you use Codex's `[model_providers.openrouter.auth]` command configuration instead, remove `env_key`; these are alternate authentication methods. See the [Codex configuration reference](https://developers.openai.com/codex/config-advanced#custom-model-providers) for supported provider settings.

Leave `model_provider` unset if OpenAI and custom providers should coexist. The patch selects a provider when each new task starts. The provider menu's **Automatic** choice maps an already-selected model to a provider; it does not pick between Astra and Sol models.

## Make custom models available

Codex must know each model's metadata before it can appear in the model menu. Create a catalog from the **current effective** model list, then add your custom model. The launcher passes it only to the patched process; do not add `model_catalog_json` to the shared `config.toml`, because a static global catalog replaces the normal model list.

```powershell
New-Item -ItemType Directory -Force "$HOME\.codex-openrouter-test" | Out-Null
$catalog = codex debug models | Out-String
[System.IO.File]::WriteAllText("$HOME\.codex-openrouter-test\openrouter-models.json", $catalog, (New-Object System.Text.UTF8Encoding($false)))
```

Edit the top-level `models` array in `openrouter-models.json`. Copy an existing entry with similar capabilities and update its `slug`, display name, context window, modalities, reasoning levels, and tool support. The `slug` must be the exact model ID understood by the provider. Preserve other required fields and use the model's actual capabilities. Rebuild this supplemental catalog when the normal app's model list changes.

Do not reference this file from the shared `config.toml`. Pass another path with the launcher's `-CatalogFile` option when needed.

## Configure the provider menu

The tool creates `%USERPROFILE%\.codex\desktop-model-providers.json` by default.

`--config` changes where the installer writes the JSON, not where the running app reads it. When using a custom path, place the final file in the shared Codex home.

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

App updates can change the JavaScript structures that the patch targets. Repeat `--check` and `--dry-run` against each new version before rebuilding the copy. To return to the official app, close the patched copy and use the normal Start menu entry. Existing users of the legacy `ACL0815.CodexProviderPatch` package may remove its package registration and dedicated certificate trust separately when they no longer need it.

When an Electron ASAR integrity resource is present, the Python patch verifies its original value and updates it in the copied executable. That edit cannot retain the copy's original digital signature; the installed official executable remains untouched. The tested original-package launch accepted the external copy. The separate signing certificate is relevant only to the legacy local-MSIX route.

## Verification

The port was checked on Windows against Codex package 26.915.4065.0: the full `--dry-run` extracted, patched, syntax-checked and repacked the real app archive, preserving its unpacked-file layout. All 14 unittest regressions and two launcher checks passed, covering process-only catalog injection, launcher path validation, generated JavaScript routing behavior, and failed-publication rollback. Windows PE integrity updates were also round-tripped on a temporary executable copy.

Run the regression suite with `python -m unittest discover -s tests -v` (Node.js is needed for the JavaScript behavior tests). The external patched EXE started successfully under the exact original package identity and launched its app-server. A separate OpenRouter Responses API request succeeded. Restarting against the user's existing signed-in GUI profile and confirming shared history, an OpenRouter task in the app, and end-to-end provider routing remain to be verified.

## Origin and license

This Windows adaptation builds on Keksuccino's original macOS patch; the repository's Git history retains that implementation. The project is released under the [Unlicense](LICENSE).

This is an unofficial modification and is not affiliated with or supported by OpenAI. Use it at your own risk, and back up data you care about before patching.
