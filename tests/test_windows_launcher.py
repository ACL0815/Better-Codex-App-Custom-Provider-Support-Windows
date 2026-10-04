from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / "Start-Codex-Provider.ps1"
POWERSHELL = shutil.which("powershell")
PATCH_MARKER = b"__codexDesktopModelProvidersPatchV3"


def synthetic_asar() -> bytes:
    header_json = json.dumps({"files": {"index.js": {"size": 0}}}).encode()
    padding = b"\0" * ((4 - len(header_json) % 4) % 4)
    header = struct.pack("<II", 4 + len(header_json) + len(padding), len(header_json)) + header_json + padding
    return struct.pack("<II", 4, len(header)) + header + PATCH_MARKER


def asar_header_hash(path: Path) -> str:
    raw = path.read_bytes()
    header_size = struct.unpack("<I", raw[4:8])[0]
    header = raw[8 : 8 + header_size]
    string_size = struct.unpack("<I", header[4:8])[0]
    return hashlib.sha256(header[8 : 8 + string_size]).hexdigest()


def ps_literal(value: Path | str) -> str:
    return "'" + str(value).replace("'", "''") + "'"


class LauncherFixture:
    def __init__(
        self,
        root: Path,
        *,
        source_version: str = "0.159.2",
        cache_version: str = "0.159.2",
    ) -> None:
        self.root = root
        self.install = root / "installed"
        self.source = self.install / "app"
        self.output = root / "custom output"
        self.home = root / "codex home"
        self.app = self.output / "ChatGPT.exe"
        self.local_app_data = root / "local app data"
        self.runtime = self.local_app_data / "Codex Provider Patch" / "runtime-model-catalog.json"
        self.catalog = root / "supplemental.json"
        self.key = root / "key.txt"
        for directory in (self.source / "resources", self.output / "resources", self.home):
            directory.mkdir(parents=True)
        (self.source / "ChatGPT.exe").write_bytes(b"source executable")
        (self.source / "resources" / "app.asar").write_bytes(synthetic_asar())
        self.app.write_bytes(b"patched executable")
        (self.output / "resources" / "app.asar").write_bytes(synthetic_asar())
        (self.home / "config.toml").write_text("[model_providers.openrouter]\nname='OpenRouter'\n", encoding="utf-8")
        base_models = [
            {"slug": "gpt-existing", "display_name": "Current metadata"},
            {"slug": "gpt-6-luna"},
            {"slug": "gpt-6-sol"},
            {"slug": "gpt-6.1-sol"},
        ]
        (self.home / "models_cache.json").write_text(
            json.dumps({"client_version": cache_version, "models": base_models}), encoding="utf-8"
        )
        self.catalog.write_text(
            json.dumps({"models": [
                {"slug": "gpt-existing", "display_name": "Stale metadata must lose"},
                {"slug": "custom/model", "display_name": "Custom"},
            ]}),
            encoding="utf-8",
        )
        self.key.write_text("fixture-api-key", encoding="utf-8")
        manifest = {
            "format": 2,
            "layout": "Windows Codex 26.928.3736.0 Power Picker",
            "patch_marker": PATCH_MARKER.decode(),
            "source": str(self.source),
            "source_package_full_name": "OpenAI.Codex_fixture",
            "source_codex_cli_version": source_version,
            "source_executable": "ChatGPT.exe",
            "executable": "ChatGPT.exe",
            "source_executable_sha256": hashlib.sha256((self.source / "ChatGPT.exe").read_bytes()).hexdigest(),
            "source_asar_header_sha256": asar_header_hash(self.source / "resources" / "app.asar"),
            "executable_sha256": hashlib.sha256(self.app.read_bytes()).hexdigest(),
            "asar_header_sha256": asar_header_hash(self.output / "resources" / "app.asar"),
        }
        (self.output / "codex-provider-patch.json").write_text(json.dumps(manifest), encoding="utf-8")

    def snapshot(self) -> dict[str, str]:
        return {
            str(path.relative_to(self.root)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in self.root.rglob("*") if path.is_file() and path.name != "wrapper.ps1"
        }

    def run(self, *, check_only: bool, running_path: Path | None = None) -> subprocess.CompletedProcess[str]:
        wrapper = self.root / "wrapper.ps1"
        process_output = (
            f"[pscustomobject]@{{ ExecutablePath = {ps_literal(running_path)} }}"
            if running_path is not None else "return"
        )
        mode = "-CheckOnly" if check_only else "-InPackage"
        wrapper.write_text(
            f"""
Import-Module (Join-Path $env:WINDIR 'System32/WindowsPowerShell/v1.0/Modules/Microsoft.PowerShell.Utility/Microsoft.PowerShell.Utility.psd1')
$env:LOCALAPPDATA = {ps_literal(self.local_app_data)}
function global:Get-AppxPackage {{ param($Name) [pscustomobject]@{{ InstallLocation = {ps_literal(self.install)}; PackageFullName = 'OpenAI.Codex_fixture' }} }}
function global:Get-CimInstance {{ param($ClassName, $Filter) {process_output} }}
function global:Start-Process {{ param($FilePath, $WorkingDirectory, $WindowStyle) Write-Output ('FAKE-START:' + $FilePath) }}
& {ps_literal(LAUNCHER)} {mode} -AppPath {ps_literal(self.app)} -CodexHome {ps_literal(self.home)} -CatalogFile {ps_literal(self.catalog)} -RuntimeCatalogFile {ps_literal(self.runtime)} -KeyFile {ps_literal(self.key)}
""",
            encoding="utf-8",
        )
        return subprocess.run(
            [POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(wrapper)],
            text=True, capture_output=True, check=False,
        )


@unittest.skipUnless(POWERSHELL, "Windows PowerShell is required")
class WindowsLauncherTests(unittest.TestCase):
    def test_check_only_detects_running_custom_app_path_without_writing(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = LauncherFixture(Path(temporary))
            before = fixture.snapshot()
            result = fixture.run(check_only=True, running_path=fixture.app)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("Basis: 4; benutzerdefiniert: 1", result.stdout)
            self.assertIn("Codex laeuft derzeit mit 1 Prozess", result.stdout)
            self.assertEqual(fixture.snapshot(), before)
            self.assertFalse(fixture.runtime.exists())

    def test_check_only_accepts_newer_cache_patch_version_without_writing(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = LauncherFixture(
                Path(temporary), source_version="0.159.2", cache_version="0.159.3"
            )
            before = fixture.snapshot()
            result = fixture.run(check_only=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("Basis: 4; benutzerdefiniert: 1", result.stdout)
            self.assertEqual(fixture.snapshot(), before)
            self.assertFalse(fixture.runtime.exists())

    def test_check_only_rejects_different_cache_minor_without_writing(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = LauncherFixture(
                Path(temporary), source_version="0.159.2", cache_version="0.160.0"
            )
            before = fixture.snapshot()
            result = fixture.run(check_only=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Modellcache passt nicht", result.stderr)
            self.assertEqual(fixture.snapshot(), before)
            self.assertFalse(fixture.runtime.exists())

    def test_inner_launch_merges_current_models_and_preserves_base_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = LauncherFixture(Path(temporary))
            result = fixture.run(check_only=False)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("FAKE-START:", result.stdout)
            runtime = json.loads(fixture.runtime.read_text(encoding="utf-8"))
            by_slug = {model["slug"]: model for model in runtime["models"]}
            self.assertEqual(
                set(by_slug), {"gpt-existing", "gpt-6-luna", "gpt-6-sol", "gpt-6.1-sol", "custom/model"}
            )
            self.assertEqual(by_slug["gpt-existing"]["display_name"], "Current metadata")
            self.assertEqual(by_slug["custom/model"]["display_name"], "Custom")

    def test_repeated_inner_launch_refreshes_existing_runtime_catalog(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = LauncherFixture(Path(temporary))
            first = fixture.run(check_only=False)
            self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
            fixture.catalog.write_text(
                json.dumps({"models": [{"slug": "replacement/model"}]}), encoding="utf-8"
            )
            second = fixture.run(check_only=False)
            self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
            runtime = json.loads(fixture.runtime.read_text(encoding="utf-8"))
            slugs = {model["slug"] for model in runtime["models"]}
            self.assertEqual(slugs, {"gpt-existing", "gpt-6-luna", "gpt-6-sol", "gpt-6.1-sol", "replacement/model"})
            self.assertNotIn("custom/model", slugs)
            self.assertEqual(list(fixture.runtime.parent.iterdir()), [fixture.runtime])
            before = fixture.runtime.read_bytes()
            fixture.catalog.write_text("invalid JSON", encoding="utf-8")
            failed = fixture.run(check_only=True)
            self.assertNotEqual(failed.returncode, 0)
            self.assertEqual(fixture.runtime.read_bytes(), before)
            self.assertEqual(list(fixture.runtime.parent.iterdir()), [fixture.runtime])

    def test_check_only_rejects_modified_portable_copy_before_writing(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = LauncherFixture(Path(temporary))
            fixture.app.write_bytes(b"modified after manifest creation")
            before = fixture.snapshot()
            result = fixture.run(check_only=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Patch-Integritaet ist ungueltig", result.stderr)
            self.assertEqual(fixture.snapshot(), before)
            self.assertFalse(fixture.runtime.exists())

    def test_check_only_rejects_duplicate_custom_slugs_without_writing(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = LauncherFixture(Path(temporary))
            fixture.catalog.write_text(
                json.dumps({"models": [{"slug": "custom/model"}, {"slug": "custom/model"}]}),
                encoding="utf-8",
            )
            before = fixture.snapshot()
            result = fixture.run(check_only=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("doppelte Modell-Slugs", result.stderr)
            self.assertEqual(fixture.snapshot(), before)
            self.assertFalse(fixture.runtime.exists())


if __name__ == "__main__":
    unittest.main()
