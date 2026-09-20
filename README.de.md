# Better Codex App Custom Provider Support für Windows

Diese Windows-Anpassung ergänzt das Modellmenü der Codex-Desktop-App um eine Provider-Auswahl für **neue Aufgaben**. Der normale ChatGPT-Login bleibt für OpenAI-Modelle verfügbar. Grundlage ist der ursprüngliche macOS-Patch von Keksuccino.

Der Installer erstellt eine **separate App-Kopie**. Die installierte Store-App bleibt unverändert. Es handelt sich um einen experimentellen Patch, nicht um ein signiertes Windows-Installationspaket. Ob eine kopierte App ohne ihre ursprüngliche Paketidentität startet, hängt von der App-Version ab.

Die Windows-spezifische Variante ist auf Codex **26.915.4065.0** zugeschnitten. Sie steuert neue **lokale Aufgaben**; Remote- und Cloud-Aufgaben behalten ihre bisherige Weiterleitung.

## Voraussetzungen

- Windows 10 oder 11
- Installierte Codex-App mit einem Electron-Archiv `resources\app.asar`
- Python ab Version 3.9 sowie Node.js mit `npx` im Suchpfad
- Freier Speicherplatz für temporäre Dateien, App-Kopie und Sicherung

## Verwendung

Lade das gesamte Repository herunter oder klone es. Öffne PowerShell im Repository-Ordner und führe zuerst die Prüfungen aus:

```powershell
py -3 .\patch_chatgpt_providers.py --check
py -3 .\patch_chatgpt_providers.py --dry-run
```

Die zweite Prüfung bearbeitet nur temporäre Dateien. Wenn sie erfolgreich ist, erstellt dieser Aufruf die gepatchte Kopie:

```powershell
py -3 .\patch_chatgpt_providers.py
```

Falls der Python-Launcher fehlt, verwende `python` statt `py -3`. Standardmäßig liegt die Ausgabe unter `%LOCALAPPDATA%\Programs\Codex-Provider-Patch`. Mit `--app` wählst du den Quellordner, mit `--output` das Ausgabeziel. Alle Optionen zeigt `--help`.

Starte anschließend die Desktop-EXE im Ausgabeordner. Beim Owl-Build 26.915 heißt sie `ChatGPT.exe`. Die vorhandene Startmenü-Verknüpfung öffnet weiterhin die offizielle Installation.

## Provider einrichten

Trage eigene Provider in `%USERPROFILE%\.codex\config.toml` ein. Wenn `CODEX_HOME` gesetzt ist, wird stattdessen dieses Verzeichnis verwendet. Beispiel:

```toml
[model_providers.openrouter]
name = "OpenRouter"
base_url = "https://openrouter.ai/api/v1"
wire_api = "responses"
env_key = "OPENROUTER_API_KEY"
```

Hinterlege den Schlüssel in der Benutzer-Umgebungsvariable `OPENROUTER_API_KEY` oder einem geeigneten Secret-Manager. Starte die App anschließend mit dieser Umgebung. Schlüssel gehören weder in das Repository noch in die Menü-Konfiguration.

Die Datei `desktop-model-providers.json` im Codex-Verzeichnis steuert die Menüeinträge und ordnet Modell-IDs den Providern zu. Ein eigener Provider muss unter derselben ID in `config.toml` stehen. Eigene Modelle benötigen außerdem passende Metadaten im Modellkatalog. Die vollständigen Beispiele findest du in der [englischen Anleitung](README.md).

Die Auswahl gilt beim Start einer Aufgabe. Sie ändert den Provider bestehender Aufgaben nicht. Änderungen an der Menü-Konfiguration erfordern keinen erneuten Patch.

## Updates und Rückkehr zur Original-App

Nach jedem App-Update erneut prüfen und eine neue Kopie erstellen. Unbekannte JavaScript-Strukturen führen zum Abbruch. Ein erfolgreicher Patch bestätigt noch keinen erfolgreichen App-Start oder Provider-Aufruf.

Zum Zurückwechseln starte die offizielle Installation. Sicherungen früherer Ausgaben liegen standardmäßig unter `%LOCALAPPDATA%\Codex Provider Patch Backups`. Falls Integritätsdaten in der EXE angepasst werden müssen, ist deren ursprüngliche digitale Signatur anschließend nicht mehr gültig.

Inoffizielles Projekt, nicht von OpenAI unterstützt. Es gilt die [Unlicense](LICENSE).
