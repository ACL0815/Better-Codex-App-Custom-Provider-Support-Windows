from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = (ROOT / "Start-Codex-Provider.ps1").read_text(encoding="utf-8")


class WindowsLauncherTests(unittest.TestCase):
    def test_launcher_uses_shared_state_and_original_package_identity(self) -> None:
        self.assertIn("Join-Path $env:USERPROFILE '.codex'", LAUNCHER)
        self.assertIn("[string]$AppPath", LAUNCHER)
        self.assertIn("Get-AppxPackage -Name 'OpenAI.Codex'", LAUNCHER)
        self.assertIn("Programs\\Codex-Provider-Patch\\ChatGPT.exe", LAUNCHER)
        self.assertIn("-PackageFamilyName $originalPackage.PackageFamilyName", LAUNCHER)
        self.assertIn("-AppPath \"' + $appPath", LAUNCHER)
        self.assertIn("-PreventBreakaway", LAUNCHER)
        self.assertNotIn("CODEX_ELECTRON_USER_DATA_PATH", LAUNCHER)


    def test_launcher_scopes_catalog_and_guards_concurrent_processes(self) -> None:
        self.assertIn("CODEX_CUSTOM_PROVIDER_MODEL_CATALOG", LAUNCHER)
        self.assertIn(".codex-openrouter-test\\openrouter-models.json", LAUNCHER)
        self.assertIn("model_catalog_json", LAUNCHER)
        self.assertIn("$runningCodex.Count -gt 0", LAUNCHER)
        guard = LAUNCHER.index("$runningCodex.Count -gt 0")
        start = LAUNCHER.index("Start-Process -FilePath $appPath")
        self.assertLess(guard, start)


if __name__ == "__main__":
    unittest.main()
