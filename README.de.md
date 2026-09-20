# Better Codex App Custom Provider Support für Windows

Diese Windows-Anpassung ergänzt das Modellmenü der Codex-Desktop-App um eine Provider-Auswahl für **neue Aufgaben**. Der normale ChatGPT-Login bleibt für OpenAI-Modelle verfügbar. Grundlage ist der ursprüngliche macOS-Patch von Keksuccino.

Der Installer erstellt eine **separate App-Kopie** als Zwischenstand. Die installierte Store-App bleibt unverändert. Beim Owl-Build scheitert ein direkter Start der `ChatGPT.exe` mit `process has no package identity`, auch im registrierten Paketordner. Ein zweites Skript erstellt daraus ein vollständiges, lokal signiertes MSIX-Paket mit eigener Publisher-Identität. Der Start im Paketkontext ist geprüft; die Provider-Weiterleitung innerhalb der App noch nicht.

Die Windows-spezifische Variante ist auf Codex **26.915.4065.0** zugeschnitten. Sie steuert neue **lokale Aufgaben**; Remote- und Cloud-Aufgaben behalten ihre bisherige Weiterleitung.

## Voraussetzungen

- Windows 10 oder 11
- Installierte Codex-App mit einem Electron-Archiv `resources\app.asar`
- Python ab Version 3.9 sowie Node.js mit `npx` im Suchpfad
- Windows-SDK-Werkzeuge `makeappx.exe` und `signtool.exe` in der x64-Version zum Bauen und Signieren des separaten MSIX
- Freier Speicherplatz für temporäre Dateien, App-Kopie und Sicherung

## Verwendung

Lade das gesamte Repository herunter oder klone es. Öffne PowerShell im Repository-Ordner und führe zuerst die Prüfungen aus:

```powershell
py -3 .\patch_chatgpt_providers.py --check
py -3 .\patch_chatgpt_providers.py --dry-run
```

Die zweite Prüfung bearbeitet nur temporäre Dateien. Lege anschließend ein separates Codex-Verzeichnis an und erstelle die gepatchte Kopie mit der Provider-Konfiguration dort:

```powershell
New-Item -ItemType Directory -Force "$HOME\.codex-openrouter-test" | Out-Null
py -3 .\patch_chatgpt_providers.py --config "$HOME\.codex-openrouter-test\desktop-model-providers.json"
```

Falls der Python-Launcher fehlt, verwende `python` statt `py -3`. Standardmäßig liegt die Ausgabe unter `%LOCALAPPDATA%\Programs\Codex-Provider-Patch`. Mit `--app` wählst du den Quellordner, mit `--output` das Ausgabeziel. Alle Optionen zeigt `--help`.

Der Ausgabeordner ist eine Zwischenstufe. Beim Owl-Build benötigt die App eine eigene Paketidentität; erstelle und registriere dazu das separate MSIX wie unten beschrieben. Die vorhandene Startmenü-Verknüpfung öffnet weiterhin die offizielle Installation.

## Eigenes MSIX erstellen und registrieren

`Register-Codex-PatchIdentity.ps1` verpackt die gesamte vorbereitete App als MSIX mit der **eigenen** Identität `ACL0815.CodexProviderPatch` und signiert dieses Paket mit einem gesonderten Zertifikat. Die Originalbytes der signierten Quell-EXE bleiben erhalten; eine zuvor veränderte Zwischenkopie wird gegebenenfalls daraus wiederhergestellt. Das installierte ChatGPT-Paket bleibt unverändert, und der globale Entwicklermodus wird nicht aktiviert.

Das Signaturzertifikat liegt unter `CurrentUser/My`, sein öffentlicher Teil unter `CurrentUser/TrustedPeople`. Auf diesem Rechner lehnte Windows allein das benutzerbezogene Vertrauen mit `0x800B0109` ab. Der optionale Schalter `-AllowMachineTrust` fordert die Windows-Administratorzustimmung an, um **nur dieses öffentliche Zertifikat** unter `LocalMachine/TrustedPeople` zu vertrauen. Das Skript fügt kein Stammzertifikat hinzu; Signatur und Paketregistrierung erfolgen weiterhin für den aktuellen Benutzer.

Nach Erstellung der Zwischenkopie baust und registrierst du im Repository-Ordner das separate Paket mit PowerShell:

```powershell
.\Register-Codex-PatchIdentity.ps1 -AllowMachineTrust
```

Standardmäßig liegt die Zwischenkopie unter `%LOCALAPPDATA%\Programs\Codex-Provider-Patch`; `-AppPath` wählt einen anderen Ordner. Die erzeugten Paketdateien liegen standardmäßig unter `%LOCALAPPDATA%\Codex Provider Patch Identity` (`-WorkPath` ändert das). Das Skript startet die App nicht. Nach erfolgreicher Registrierung startest du sie **im eigenen Paketkontext**:

```powershell
$pkg = Get-AppxPackage -Name ACL0815.CodexProviderPatch
Invoke-CommandInDesktopPackage -PackageFamilyName $pkg.PackageFamilyName -AppId App -Command (Join-Path $pkg.InstallLocation 'app\ChatGPT.exe')
```

Beim getesteten Owl-Build 26.915 öffnete der Befehl ein reagierendes Fenster; GPU- und Renderer-Prozesse blieben länger als 30 Sekunden aktiv. Ein direkter EXE-Start auch aus `$pkg.InstallLocation` liefert keine Paketidentität. Füge diesem einfachen Startbefehl kein `-PreventBreakaway` hinzu. Er übernimmt außerdem keine Umgebungsvariablen der aufrufenden PowerShell in den Paketprozess. Für `OPENROUTER_API_KEY` und ein eigenes `CODEX_HOME` nutze den Provider-Starter unten. Lies vor der Windows-Zustimmung die Auswirkungen des Zertifikatsvertrauens. Entferne später die eigene Paketregistrierung und das Zertifikatsvertrauen wieder, wenn du die Kopie nicht mehr nutzt.

## Provider einrichten

Trage eigene Provider in `%USERPROFILE%\.codex-openrouter-test\config.toml` ein. Der Paket-Starter setzt `CODEX_HOME` und `CODEX_ELECTRON_USER_DATA_PATH` für dieses isolierte Verzeichnis. Die Test-App führt damit ein eigenes Desktop-Profil mit separatem Verlauf; gegebenenfalls musst du dich dort anmelden. Die normale Konfiguration unter `%USERPROFILE%\.codex` und deren Modellauswahl bleiben unberührt. Beispiel:

```toml
[model_providers.openrouter]
name = "OpenRouter"
base_url = "https://openrouter.ai/api/v1"
wire_api = "responses"
env_key = "OPENROUTER_API_KEY"
```

Speichere den API-Schlüssel als einzige Zeile in einer privaten Datei außerhalb dieses Repositorys, beispielsweise `%USERPROFILE%\.codex\secrets\openrouter-api-key.txt`. Erlaube nur deinem Windows-Benutzer Zugriff darauf. Der einfache Paketstart oben übernimmt `OPENROUTER_API_KEY` und `CODEX_HOME` **nicht** aus der Eltern-PowerShell. `Start-Codex-Provider.ps1` liest den Schlüssel **im Paketkontext** und setzt die Umgebung vor dem App-Start:

```powershell
.\Start-Codex-Provider.ps1 -KeyFile "$HOME\.codex\secrets\openrouter-api-key.txt" -CodexHome "$HOME\.codex-openrouter-test"
```

Diese Pfade sind die Vorgaben des Starters und können weggelassen werden. Der Schlüssel bleibt im normalen Benutzerprofil, während `CODEX_HOME` und das Desktop-Profil auf das isolierte Testverzeichnis zeigen. Mit `-CheckOnly` prüfst du die Datei und das registrierte Paket ohne App-Start oder API-Aufruf. Der Schlüssel gehört weder in das Repository noch in `config.toml`, die Menü-Konfiguration oder einen Kommandozeilenparameter.

Die Datei `desktop-model-providers.json` im **isolierten** Codex-Verzeichnis steuert die Menüeinträge und ordnet Modell-IDs den Providern zu. Ein eigener Provider muss unter derselben ID in dessen `config.toml` stehen. Eigene Modelle benötigen außerdem passende Metadaten im Modellkatalog. Erstelle diesen aus der aktuellen effektiven Modellliste und setze `model_catalog_json` nur in der isolierten Konfiguration. Ein globaler statischer Katalog kann die normale Modellliste durch einen veralteten Stand ersetzen. Die vollständigen Beispiele findest du in der [englischen Anleitung](README.md).

Die Auswahl gilt beim Start einer Aufgabe. Sie ändert den Provider bestehender Aufgaben nicht. „Automatic“ im Provider-Menü ordnet einem bereits gewählten Modell dessen Provider zu; es entscheidet nicht zwischen Astra und Sol. Änderungen an der Menü-Konfiguration erfordern keinen erneuten Patch.

## Updates und Rückkehr zur Original-App

Nach jedem App-Update erneut prüfen und eine neue Kopie erstellen. Unbekannte JavaScript-Strukturen führen zum Abbruch. Der GUI-Start ist für den getesteten Owl-Build belegt. Eine getrennte Anfrage an die OpenRouter Responses API war erfolgreich; eine OpenRouter-Aufgabe in der gepatchten App und die vollständige Provider-Weiterleitung sind noch ungeprüft.

Zum Zurückwechseln entferne die gesonderte Paketregistrierung und das Zertifikatsvertrauen; starte dann die offizielle Installation. Das Löschen des Ausgabeordners allein entfernt beides nicht. Sicherungen früherer Ausgaben liegen standardmäßig unter `%LOCALAPPDATA%\Codex Provider Patch Backups`. Wenn der Python-Patch Integritätsdaten in der Zwischenkopie der EXE ändert, wird deren ursprüngliche Signatur ungültig. Das MSIX-Skript verpackt stattdessen die ursprünglichen signierten EXE-Bytes und signiert das **neue Paket** mit dem lokalen Zertifikat.

Inoffizielles Projekt, nicht von OpenAI unterstützt. Es gilt die [Unlicense](LICENSE).
