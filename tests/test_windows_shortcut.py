"""Exercise shortcut publication only in isolated temporary directories."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch as mock_patch

import patch_chatgpt_providers as patch
from test_patch_safety import synthetic_asar
from test_windows_launcher import POWERSHELL, ps_literal

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(POWERSHELL, "Windows PowerShell is required")
class ShortcutTests(unittest.TestCase):
    def test_custom_path_and_updates_refresh_one_shortcut(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            desktop = root / "fixture desktop"
            desktop.mkdir()
            launcher = root / "fixture launcher.ps1"
            launcher.write_text("# fixture", encoding="utf-8")
            helper = ROOT / "Register-Codex-DesktopShortcut.ps1"
            expected = desktop / "Codex - OpenRouter-Test.lnk"
            for name in ("custom output", "updated output"):
                app = root / name / "ChatGPT.exe"
                app.parent.mkdir()
                app.write_bytes(b"fixture executable")
                result = subprocess.run([
                    POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                    str(helper), "-AppPath", str(app), "-LauncherPath", str(launcher),
                    "-DesktopPath", str(desktop),
                ], capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual(list(desktop.iterdir()), [expected])
                script = ("$s=New-Object -ComObject WScript.Shell; $l=$s.CreateShortcut("
                          + ps_literal(expected) + "); $l | Select-Object TargetPath,Arguments,WorkingDirectory,IconLocation | ConvertTo-Json -Compress")
                metadata = subprocess.run([POWERSHELL, "-NoProfile", "-Command", script],
                                          capture_output=True, text=True, check=True)
                link = json.loads(metadata.stdout)
                self.assertIn("WindowsPowerShell", link["TargetPath"])
                self.assertIn(str(app), link["Arguments"])
                self.assertIn(str(launcher), link["Arguments"])
                self.assertEqual(link["WorkingDirectory"], str(app.parent))
                self.assertEqual(link["IconLocation"], str(app) + ",0")
            before = expected.read_bytes()
            failure = subprocess.run([
                POWERSHELL, "-NoProfile", "-File", str(helper), "-AppPath", str(root / "missing.exe"),
                "-LauncherPath", str(launcher), "-DesktopPath", str(desktop),
            ], capture_output=True, text=True)
            self.assertNotEqual(failure.returncode, 0)
            self.assertEqual(expected.read_bytes(), before)

    def test_failed_runtime_replacement_preserves_previous_catalog(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            catalog = root / "runtime.json"
            catalog.write_text('{"models":[{"slug":"existing"}]}', encoding="utf-8")
            before = catalog.read_bytes()
            script = """
$ErrorActionPreference = 'Stop'
$tokens = $null; $errors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile(LAUNCHER, [ref]$tokens, [ref]$errors)
$function = $ast.Find({ param($node) $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq 'Write-JsonAtomic' }, $true)
Invoke-Expression $function.Extent.Text
$lock = [IO.File]::Open(CATALOG, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::None)
$failed = $false
try { Write-JsonAtomic CATALOG @{models=@(@{slug='replacement'})} } catch { $failed = $true } finally { $lock.Dispose() }
if (-not $failed) { throw 'Locked replacement unexpectedly succeeded' }
""".replace("LAUNCHER", ps_literal(ROOT / "Start-Codex-Provider.ps1")).replace("CATALOG", ps_literal(catalog))
            result = subprocess.run([POWERSHELL, "-NoProfile", "-Command", script],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(catalog.read_bytes(), before)
            self.assertEqual(list(root.iterdir()), [catalog])

    def test_source_update_during_staging_preserves_existing_output_and_shortcut(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "installed"
            (source / "resources").mkdir(parents=True)
            (source / "resources" / "app.asar").write_bytes(synthetic_asar({"files": {}}))
            executable = source / "ChatGPT.exe"
            executable.write_bytes(b"original executable")
            output = root / "portable"
            output.mkdir()
            (output / "previous.txt").write_bytes(b"previous output")
            (output / "codex-provider-patch.json").write_bytes(b"{}")
            payload = root / "patched.asar"
            payload.write_bytes(synthetic_asar({"files": {}}) + patch.PATCH_MARKER)
            copytree = patch.shutil.copytree
            def update_source(src, dst, *args, **kwargs):
                result = copytree(src, dst, *args, **kwargs)
                if Path(src) == source:
                    executable.write_bytes(b"updated executable")
                return result
            with mock_patch.object(patch, "find_target_app_processes", return_value=[]), \
                 mock_patch.object(patch, "source_codex_cli_version", return_value="0.160.0"), \
                 mock_patch.object(patch.shutil, "copytree", side_effect=update_source), \
                 mock_patch.object(patch.subprocess, "run") as shortcut:
                with self.assertRaises(patch.PatchError):
                    patch.install_portable(source, output, root / "backups", payload, {}, "fixture")
            shortcut.assert_not_called()
            self.assertEqual((output / "previous.txt").read_bytes(), b"previous output")
            self.assertEqual(set(path.name for path in output.iterdir()), {"previous.txt", "codex-provider-patch.json"})
            self.assertFalse(any(root.glob(".portable.stage-*")))
            self.assertFalse((root / "backups").exists())

    def test_successful_installer_copies_helpers_and_passes_custom_app_path(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            source = root / "installed"
            (source / "resources").mkdir(parents=True)
            (source / "resources" / "app.asar").write_bytes(synthetic_asar({"files": {}}))
            (source / "ChatGPT.exe").write_bytes(b"fixture executable")
            output = root / "custom portable"
            for _ in range(2):
                payload = root / "patched.asar"
                payload.write_bytes(synthetic_asar({"files": {}}) + patch.PATCH_MARKER)
                with mock_patch.object(patch, "find_target_app_processes", return_value=[]), \
                     mock_patch.object(patch, "source_codex_cli_version", return_value="0.160.0"), \
                     mock_patch.object(patch.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, "fixture link", "")) as run:
                    patch.install_portable(source, output, root / "backups", payload, {}, "fixture")
                command = run.call_args.args[0]
                self.assertEqual(command[command.index("-AppPath") + 1], str(output / "ChatGPT.exe"))
                self.assertEqual(command[command.index("-LauncherPath") + 1], str(output / "Start-Codex-Provider.ps1"))
                self.assertTrue((output / "Register-Codex-DesktopShortcut.ps1").is_file())
                self.assertTrue((output / "Start-Codex-Provider.ps1").is_file())


if __name__ == "__main__":
    unittest.main()
