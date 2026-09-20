"""Offline regression tests: no installed application or processes are touched."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch as mock_patch

import patch_chatgpt_providers as patch


def original_for_diff(diff: str) -> str:
    """Build an unmodified fixture from the exact old side of every hunk."""
    hunks = patch.parse_hunks(diff)
    return "\nfixture boundary between hunks\n".join(
        "\n".join(line[1:] for line in hunk if line[0] in " -")
        for hunk in hunks
    ) + "\n"


def synthetic_asar(header: dict) -> bytes:
    header_json = json.dumps(header).encode("utf-8")
    padding = b"\x00" * ((4 - len(header_json) % 4) % 4)
    header_pickle = struct.pack("<II", 4 + len(header_json) + len(padding), len(header_json)) + header_json + padding
    return struct.pack("<II", 4, len(header_pickle)) + header_pickle


class PatchSafetyTests(unittest.TestCase):
    def test_every_supported_layout_patches_offline_fixture(self) -> None:
        for name, central_diff, picker_diff in patch.PATCH_VARIANTS:
            with self.subTest(layout=name):
                with tempfile.TemporaryDirectory() as temporary:
                    central = Path(temporary, "central.js")
                    picker = Path(temporary, "picker.js")
                    central.write_text(original_for_diff(central_diff), encoding="utf-8")
                    picker.write_text(original_for_diff(picker_diff), encoding="utf-8")
                    self.assertEqual(patch.apply_supported_patch_variant(central, picker), name)
                    self.assertIn(patch.PATCH_MARKER.decode(), central.read_text(encoding="utf-8"))
                    self.assertIn("codexPicker", picker.read_text(encoding="utf-8"))

    def test_unsupported_layout_preserves_both_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            central = Path(temporary, "central.js")
            picker = Path(temporary, "picker.js")
            central.write_text("unsupported central\n", encoding="utf-8")
            picker.write_text("unsupported picker\n", encoding="utf-8")
            with self.assertRaises(patch.PatchError):
                patch.apply_supported_patch_variant(central, picker)
            self.assertEqual(central.read_text(encoding="utf-8"), "unsupported central\n")
            self.assertEqual(picker.read_text(encoding="utf-8"), "unsupported picker\n")

    def test_repeated_hunk_is_rejected(self) -> None:
        diff = "@@ -1,1 +1,1 @@\n-old\n+new"
        with self.assertRaisesRegex(patch.PatchError, "matched 2 times"):
            patch.render_unified_diff("old\nold\n", diff, "fixture.js")

    def test_asar_header_hash_and_truncated_header(self) -> None:
        header_json = json.dumps({"files": {"index.js": {"size": 0}}}).encode()
        archive = synthetic_asar({"files": {"index.js": {"size": 0}}})
        with tempfile.TemporaryDirectory() as temporary:
            asar = Path(temporary, "app.asar")
            asar.write_bytes(archive)
            self.assertEqual(patch.asar_header_hash(asar), hashlib.sha256(header_json).hexdigest())
            asar.write_bytes(archive[:-1])
            with self.assertRaises(patch.PatchError):
                patch.asar_header_hash(asar)

    def test_asar_pack_retains_unpacked_entries(self) -> None:
        header = {"files": {
            "node_modules": {"files": {
                "native": {"unpacked": True, "files": {"addon.node": {"size": 2}}},
                "loose.node": {"unpacked": True, "size": 1},
            }},
            "index.js": {"size": 1},
        }}
        with tempfile.TemporaryDirectory() as temporary:
            original = Path(temporary, "original.asar")
            original.write_bytes(synthetic_asar(header))
            command = patch.asar_pack_command(Path("src"), Path("out.asar"), original)
            self.assertEqual(command[-4:], [
                "--unpack-dir", "node_modules/native",
                "--unpack", "loose.node",
            ])

    def test_existing_config_survives_validation_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            config = Path(temporary, "desktop-model-providers.json")
            data = copy.deepcopy(patch.DEFAULT_PROVIDER_CONFIG)
            data["model_providers"]["sample/model"] = "missing"
            original = json.dumps(data)
            config.write_text(original, encoding="utf-8")
            with self.assertRaises(patch.PatchError):
                patch.ensure_provider_config(config, overwrite=False)
            self.assertEqual(config.read_text(encoding="utf-8"), original)

    def test_bundle_discovery_rejects_ambiguous_matches(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            assets = Path(temporary)
            for name in ("one.js", "two.js"):
                Path(assets, name).write_text("required token\n", encoding="utf-8")
            with self.assertRaisesRegex(patch.PatchError, "found 2"):
                patch.unique_candidate(assets, ("required token",), "test role")

    def test_marker_spanning_read_boundary_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            asar = Path(temporary, "app.asar")
            marker = patch.PATCH_MARKER
            asar.write_bytes(b"x" * (4 * 1024 * 1024 - 3) + marker[:3] + marker[3:])
            self.assertTrue(patch.contains_marker(asar))

    def test_pe_integrity_payload_validation(self) -> None:
        entries = [{"file": "resources\\app.asar", "alg": "sha256", "value": "a" * 64}]
        self.assertEqual(
            patch.parse_pe_asar_integrity_payload(json.dumps(entries).encode("utf-8")),
            entries,
        )
        invalid_payloads = (
            b"not json",
            b"{}",
            b"[{}]",
            json.dumps([{**entries[0], "alg": "md5"}]).encode("utf-8"),
            json.dumps([{**entries[0], "value": "bad"}]).encode("utf-8"),
        )
        for payload in invalid_payloads:
            with self.subTest(payload=payload), self.assertRaises(patch.PatchError):
                patch.parse_pe_asar_integrity_payload(payload)

    def test_windows_app_discovery_uses_existing_asar(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            local = Path(temporary, "Local")
            programs = Path(temporary, "Program Files")
            expected = local / "Programs" / "Codex"
            (expected / "resources").mkdir(parents=True)
            (expected / "resources" / "app.asar").write_bytes(b"fixture")
            environment = {
                "LOCALAPPDATA": str(local),
                "ProgramFiles": str(programs),
                "USERPROFILE": temporary,
            }
            with mock_patch.dict("os.environ", environment, clear=True):
                self.assertEqual(patch.discover_app(), expected.resolve())

    def test_output_safety_rejects_source_and_nested_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            source = base / "installed"
            output = base / "portable"
            backup = base / "backups"
            patch.ensure_safe_output(source, output, backup)
            bad_paths = (
                (source, backup),
                (source / "child", backup),
                (output, output / "backups"),
                (output, source / "backup"),
            )
            for candidate_output, candidate_backup in bad_paths:
                with self.subTest(output=candidate_output, backup=candidate_backup):
                    with self.assertRaises(patch.PatchError):
                        patch.ensure_safe_output(source, candidate_output, candidate_backup)

    def test_portable_publish_rolls_back_existing_output_on_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            source = base / "installed"
            output = base / "portable"
            backup_dir = base / "backups"
            patched = base / "patched.asar"
            (source / "resources").mkdir(parents=True)
            (output / "resources").mkdir(parents=True)
            original_bytes = synthetic_asar({"files": {}})
            (source / "resources" / "app.asar").write_bytes(original_bytes)
            (output / "original.txt").write_text("keep me", encoding="utf-8")
            (output / "codex-provider-patch.json").write_text("{}", encoding="utf-8")
            patched.write_bytes(original_bytes + patch.PATCH_MARKER)
            original_rename = Path.rename

            def fail_stage_rename(path: Path, target: Path) -> Path:
                if path.name.startswith(".portable.stage-"):
                    raise OSError("simulated publish failure")
                return original_rename(path, target)

            with mock_patch.object(patch, "find_target_app_processes", return_value=[]), \
                 mock_patch.object(Path, "rename", fail_stage_rename):
                with self.assertRaisesRegex(OSError, "simulated publish failure"):
                    patch.install_portable(source, output, backup_dir, patched, {})

            self.assertEqual((output / "original.txt").read_text(encoding="utf-8"), "keep me")
            self.assertEqual((source / "resources" / "app.asar").read_bytes(), original_bytes)
            self.assertFalse(any(base.glob(".portable.stage-*")))


if __name__ == "__main__":
    unittest.main()
