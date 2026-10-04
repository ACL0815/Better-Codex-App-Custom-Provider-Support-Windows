# Better Codex App Custom Provider Support für Windows

Diese Windows-Anpassung ergänzt das Modellmenü der Codex-Desktop-App um eine Provider-Auswahl für **neue lokale Aufgaben**. Grundlage ist der ursprüngliche macOS-Patch von Keksuccino.

Der Patcher erstellt eine separate App-Kopie und lässt die installierte Store-App unverändert. Der Starter führt die externe Kopie unter der Identität des installierten Originalpakets `OpenAI.Codex` aus. Dadurch verwendet sie dasselbe Codex-Verzeichnis und denselben virtualisierten Desktop-Profilpfad wie die offizielle App. Modellkatalog und API-Schlüssel gelten nur für diesen gestarteten Prozess.

> [!CAUTION]
> Die Provider-Auswahl wird beim Start einer Aufgabe festgelegt. Eine laufende Aufgabe wechselt ihren Provider nicht nachträglich.

Die aktuelle Windows-spezifische Variante ist auf Codex **26.930.3930.0** zugeschnitten (interne App-Version **26.930.31730**). Die früheren Windows-Layouts für 26.928.3736.0 und 26.915.4065.0 bleiben enthalten. Remote- und Cloud-Aufgaben behalten ihre bisherige Weiterleitung.

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

Jede erfolgreiche Installation oder Aktualisierung erstellt beziehungsweise erneuert **Codex - OpenRouter-Test** auf deinem Windows-Desktop, auch bei Umleitung nach OneDrive. Die Verknüpfung verwendet Windows PowerShell 5.1 und den mitinstallierten Starter samt genauem App-Pfad. Sie funktioniert auch nach Verschieben dieses Repositorys. Den API-Schlüssel liest der Starter beim Start aus der lokalen Schlüsseldatei. `--check` und `--dry-run` ändern keine Desktop-Verknüpfung. Beende Codex vollständig, öffne die Verknüpfung und erstelle eine neue lokale Aufgabe; wähle für ein konfiguriertes Custom-Modell OpenRouter oder Automatic. Die normalen Modelle bleiben verfügbar.

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

Der Starter beendet selbst keine Prozesse. Er verweigert den Start, solange die offizielle App, eine ältere lokal paketierte Variante oder die gewählte portable Kopie läuft. Bevor er die Schlüsseldatei liest, prüft er das installierte `OpenAI.Codex`-Paket, EXE- und ASAR-Hashes, Patchmarker, Herkunftsmetadaten, gemeinsame Konfiguration und Modellkataloge. `-CheckOnly` führt diese Prüfungen und den Katalog-Merge nur im Arbeitsspeicher aus.

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
- `-RuntimeCatalogFile`: `%LOCALAPPDATA%\Codex Provider Patch\runtime-model-catalog.json`
- `-KeyFile`: `%USERPROFILE%\.codex\secrets\openrouter-api-key.txt`

Du kannst sie explizit angeben:

```powershell
.\Start-Codex-Provider.ps1 -AppPath "$env:LOCALAPPDATA\Programs\Codex-Provider-Patch\ChatGPT.exe" -CodexHome "$HOME\.codex" -CatalogFile "$HOME\.codex-openrouter-test\openrouter-models.json" -KeyFile "$HOME\.codex\secrets\openrouter-api-key.txt"
```

## Eigenes Modell verfügbar machen

Lege einen Zusatzkatalog mit einem passenden Modell als Vorlage an:

```powershell
New-Item -ItemType Directory -Force "$HOME\.codex-openrouter-test" | Out-Null
$cache = Get-Content "$HOME\.codex\models_cache.json" -Raw | ConvertFrom-Json
$template = $cache.models | Where-Object slug -eq 'gpt-5.5' | Select-Object -First 1
$supplement = [ordered]@{ models = @($template) } | ConvertTo-Json -Depth 100
[System.IO.File]::WriteAllText("$HOME\.codex-openrouter-test\openrouter-models.json", $supplement, (New-Object System.Text.UTF8Encoding($false)))
```

Passe den kopierten Eintrag im obersten `models`-Array an: `slug`, Anzeigename, Kontextfenster, Modalitäten, Reasoning-Stufen und Werkzeugunterstützung. Der `slug` muss exakt der Modell-ID des Providers entsprechen; Slugs im Zusatzkatalog müssen eindeutig sein.

Verweise aus der gemeinsamen `config.toml` **nicht** auf diese Datei. Der Starter liest bei jedem Start den kontobezogenen `%USERPROFILE%\.codex\models_cache.json`, behält dessen aktuelle Metadaten und ergänzt ausschließlich dort noch nicht vorhandene Slugs. Gleiche Slugs verwenden stets die normalen Metadaten. Den daraus abgeleiteten Laufzeitkatalog schreibt er erst beim tatsächlichen Start atomisch in die eigene Datei unter `%LOCALAPPDATA%\Codex Provider Patch`; `-CheckOnly` verändert keine Datei.

Fehlt `models_cache.json`, ist die Datei ungültig, älter als die Patch-Version der mitgelieferten CLI oder stammt sie aus einer anderen CLI-Major/Minor-Linie, bricht der Starter ab. Einen neueren Patch-Level derselben CLI-Linie akzeptiert er. Starte bei einem Fehler die offizielle App normal, bis sie den aktuellen Modellkatalog geladen hat, beende sie vollständig und versuche es erneut. Der Starter führt selbst weder `codex debug models` noch eine Aktualisierung von Anmeldung oder Cache aus.

`%USERPROFILE%\.codex\desktop-model-providers.json` steuert die Provider-Menüeinträge und ordnet Modell-IDs den Providern zu. „Automatic“ ordnet einem bereits gewählten Modell den Provider zu; es entscheidet nicht zwischen Astra und Sol. Änderungen an dieser JSON-Datei erfordern keinen erneuten Patch.

## Updates und Rückkehr zur Original-App

Nach jedem App-Update erneut `--check` und `--dry-run` ausführen und die Kopie neu erstellen. Zum Zurückwechseln beendest du die gepatchte Kopie und startest die offizielle App über das Startmenü. Nutzer des Legacy-Pakets können dessen Registrierung und eigenes Zertifikatsvertrauen später separat entfernen.

## Verifikation

Codex 26.930.3930.0 bestand die vollständige Quell-Kompatibilitätsprüfung und Patch-Erstellung samt JavaScript-Syntaxprüfung, unverändertem Unpacked-Dateilayout, Manifest-Hashes und Windows-PE-Integrität. Alle 34 Offline-Regressionstests bestanden, darunter wiederholte Desktop-Verknüpfungserstellung, atomare Katalog-Aktualisierung, fehlgeschlagene Ersetzungen und Quellenänderungen während der Installation. `-CheckOnly` des mitinstallierten Starters war mit 10 Standardmodellen und 1 Custom-Modell erfolgreich und schrieb keinen Laufzeitkatalog.

Die Desktop-Verknüpfung wurde ohne Öffnen geprüft. Die laufende GUI-Sitzung blieb geöffnet; die neue Kopie wurde nicht gestartet. Gemeinsame Anmeldung, sichtbare Historie und eine vollständige OpenRouter-Aufgabe in diesem Build bleiben bis zum bewussten Start über die Verknüpfung nach Beenden von Codex ungeprüft.

Inoffizielles Projekt, nicht von OpenAI unterstützt. Es gilt die [Unlicense](LICENSE).
