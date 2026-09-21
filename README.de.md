# Better Codex App Custom Provider Support für Windows

Diese Windows-Anpassung ergänzt das Modellmenü der Codex-Desktop-App um eine Provider-Auswahl für **neue lokale Aufgaben**. Grundlage ist der ursprüngliche macOS-Patch von Keksuccino.

Der Patcher erstellt eine separate App-Kopie und lässt die installierte Store-App unverändert. Der Starter führt die externe Kopie unter der Identität des installierten Originalpakets `OpenAI.Codex` aus. Dadurch verwendet sie dasselbe Codex-Verzeichnis und denselben virtualisierten Desktop-Profilpfad wie die offizielle App. Modellkatalog und API-Schlüssel gelten nur für diesen gestarteten Prozess.

> [!CAUTION]
> Die Provider-Auswahl wird beim Start einer Aufgabe festgelegt. Eine laufende Aufgabe wechselt ihren Provider nicht nachträglich.

Die Windows-spezifische Variante ist auf Codex **26.915.4065.0** zugeschnitten. Remote- und Cloud-Aufgaben behalten ihre bisherige Weiterleitung.

## Voraussetzungen

- Windows 10 oder 11
- Installierte Codex-App mit `resources\app.asar`
- Python ab Version 3.9
- Node.js mit `npx` im Suchpfad
- Freier Speicherplatz für App-Kopie, Sicherung und temporäre Dateien

## Gepatchte Kopie erstellen

Lade das gesamte Repository herunter oder klone es. Öffne PowerShell im Repository-Ordner:

```powershell
py -3 .\patch_chatgpt_providers.py --check
py -3 .\patch_chatgpt_providers.py --dry-run
py -3 .\patch_chatgpt_providers.py
```

Falls der Python-Launcher fehlt, verwende `python` statt `py -3`. Die Ausgabe liegt standardmäßig unter `%LOCALAPPDATA%\Programs\Codex-Provider-Patch`; Sicherungen liegen unter `%LOCALAPPDATA%\Codex Provider Patch Backups`. Für den Start mit gemeinsamem Profil muss `--app` auf den `app`-Ordner des aktuell installierten `OpenAI.Codex`-Pakets zeigen. Der Starter vergleicht diese Quelle mit `codex-provider-patch.json` und lehnt Kopien aus beliebigen anderen Quellen ab. Alle Patcher-Optionen zeigt `--help`.

Ein eigenes `--output`-Ziel ist möglich. Übergib dann dessen EXE an den Starter:

```powershell
py -3 .\patch_chatgpt_providers.py --output "D:\Apps\Codex-Provider-Patch"
.\Start-Codex-Provider.ps1 -AppPath "D:\Apps\Codex-Provider-Patch\ChatGPT.exe" -CheckOnly
```

Starte `ChatGPT.exe` im Ausgabeordner nicht direkt: Der Owl-Build beendet sich dann mit `process has no package identity`. Verwende den Starter im nächsten Abschnitt. Die normale Startmenü-Verknüpfung öffnet weiterhin die offizielle App.

## Mit gemeinsamer Anmeldung und Historie starten

Beende die offizielle Codex-App vollständig. Prüfe dann die Konfiguration und starte die gepatchte Kopie:

```powershell
.\Start-Codex-Provider.ps1 -CheckOnly
.\Start-Codex-Provider.ps1
```

Der Starter beendet selbst keine Prozesse. Er verweigert den Start, solange die offizielle App, eine ältere lokal paketierte Variante oder eine weitere portable Kopie läuft. Außerdem prüft er das installierte `OpenAI.Codex`-Paket, die Herkunft der gepatchten Kopie, gemeinsame Konfiguration, Modellkatalog und Schlüsseldatei.

Der äußere Starter wechselt mit `Invoke-CommandInDesktopPackage` in den Kontext des **Originalpakets**. Dort setzt ein zweiter PowerShell-Prozess `OPENROUTER_API_KEY`, das gemeinsame `CODEX_HOME` und den nur für diesen Prozess geltenden `CODEX_CUSTOM_PROVIDER_MODEL_CATALOG`, bevor er die externe EXE startet. Setze `CODEX_ELECTRON_USER_DATA_PATH` nicht: Die Original-Paketidentität soll den Profilpfad der offiziellen App auswählen.

Eine frühere Projektversion installierte ein eigenes Paket namens `ACL0815.CodexProviderPatch`. Dieser Legacy-Weg bleibt für bestehende Installationen über `Register-Codex-PatchIdentity.ps1` verfügbar, liegt aber in einer anderen Windows-Profildomäne. Für gemeinsame Anmeldung und Historie ist er nicht mehr der empfohlene Weg. Du musst das alte Paket vor einem Test nicht löschen oder neu bauen; beende es lediglich vollständig.

## Provider einrichten

Trage den Provider in der normalen Datei `%USERPROFILE%\.codex\config.toml` ein. Setze dort **kein** globales `model_catalog_json`.

```toml
[model_providers.openrouter]
name = "OpenRouter"
base_url = "https://openrouter.ai/api/v1"
wire_api = "responses"
env_key = "OPENROUTER_API_KEY"
```

Speichere den API-Schlüssel als einzige Zeile in `%USERPROFILE%\.codex\secrets\openrouter-api-key.txt` und beschränke den Zugriff auf deinen Windows-Benutzer. Schlüssel gehören weder in `config.toml`, `desktop-model-providers.json`, das Repository noch in Kommandozeilenparameter.

Die Standardpfade des Starters sind:

- `-AppPath`: `%LOCALAPPDATA%\Programs\Codex-Provider-Patch\ChatGPT.exe`
- `-CodexHome`: `%USERPROFILE%\.codex`
- `-CatalogFile`: `%USERPROFILE%\.codex-openrouter-test\openrouter-models.json`
- `-KeyFile`: `%USERPROFILE%\.codex\secrets\openrouter-api-key.txt`

Du kannst sie explizit angeben:

```powershell
.\Start-Codex-Provider.ps1 -AppPath "$env:LOCALAPPDATA\Programs\Codex-Provider-Patch\ChatGPT.exe" -CodexHome "$HOME\.codex" -CatalogFile "$HOME\.codex-openrouter-test\openrouter-models.json" -KeyFile "$HOME\.codex\secrets\openrouter-api-key.txt"
```

## Eigenes Modell verfügbar machen

Erstelle den Zusatzkatalog aus der **aktuellen effektiven** Modellliste:

```powershell
New-Item -ItemType Directory -Force "$HOME\.codex-openrouter-test" | Out-Null
$catalog = codex debug models | Out-String
[System.IO.File]::WriteAllText("$HOME\.codex-openrouter-test\openrouter-models.json", $catalog, (New-Object System.Text.UTF8Encoding($false)))
```

Ergänze im obersten `models`-Array einen Eintrag für das Provider-Modell. Kopiere dafür ein Modell mit ähnlichen Fähigkeiten und passe `slug`, Anzeigename, Kontextfenster, Modalitäten, Reasoning-Stufen und Werkzeugunterstützung an. Der `slug` muss exakt der Modell-ID des Providers entsprechen.

Verweise aus der gemeinsamen `config.toml` **nicht** auf diese Datei. Der Starter übergibt sie nur dem gepatchten App-Server-Prozess. Ein globaler statischer Katalog ersetzt dagegen die normale Modellliste und kann veraltete oder unerwünschte Modelle anzeigen.

`%USERPROFILE%\.codex\desktop-model-providers.json` steuert die Provider-Menüeinträge und ordnet Modell-IDs den Providern zu. „Automatic“ ordnet einem bereits gewählten Modell den Provider zu; es entscheidet nicht zwischen Astra und Sol. Änderungen an dieser JSON-Datei erfordern keinen erneuten Patch.

## Updates und Rückkehr zur Original-App

Nach jedem App-Update erneut `--check` und `--dry-run` ausführen und die Kopie neu erstellen. Zum Zurückwechseln beendest du die gepatchte Kopie und startest die offizielle App über das Startmenü. Nutzer des Legacy-Pakets können dessen Registrierung und eigenes Zertifikatsvertrauen später separat entfernen.

## Verifikation

Für Codex 26.915.4065.0 wurden der vollständige Dry Run, die Patch-Erstellung, 14 unittest-Regressionstests und zwei Starter-Prüfungen erfolgreich ausgeführt. Die externe gepatchte EXE startete unter der exakten Original-Paketidentität und ihr App-Server lief an. Eine getrennte Anfrage an die OpenRouter Responses API war ebenfalls erfolgreich.

Noch offen sind ein Neustart mit der bestehenden angemeldeten GUI-Sitzung, die sichtbare gemeinsame Historie sowie eine vollständige OpenRouter-Aufgabe innerhalb der gepatchten App. Diese Punkte werden daher nicht als bestätigt dargestellt.

Inoffizielles Projekt, nicht von OpenAI unterstützt. Es gilt die [Unlicense](LICENSE).
