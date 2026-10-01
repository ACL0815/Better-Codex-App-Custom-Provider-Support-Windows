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
from patch_windows_26915 import (
    APP_SERVER_ENV_MAPPINGS_ANCHOR,
    WINDOWS_26915_LAYOUT_NAME,
)
from patch_windows_26928 import (
    APP_SERVER_ENV_MAPPINGS_ANCHOR as APP_SERVER_ENV_MAPPINGS_ANCHOR_26928,
    WINDOWS_26928_LAYOUT_NAME,
)


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
                    central_fixture = original_for_diff(central_diff)
                    if name == WINDOWS_26915_LAYOUT_NAME:
                        central_fixture += APP_SERVER_ENV_MAPPINGS_ANCHOR + "\n"
                    central.write_text(central_fixture, encoding="utf-8")
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

    def test_changed_26928_hunk_fails_closed_without_partial_edits(self) -> None:
        name, central_diff, picker_diff = patch.PATCH_VARIANTS[0]
        self.assertEqual(name, WINDOWS_26928_LAYOUT_NAME)
        with tempfile.TemporaryDirectory() as temporary:
            central = Path(temporary, "central.js")
            picker = Path(temporary, "picker.js")
            original_central = original_for_diff(central_diff).replace(
                "async prewarmThreadStart(", "async changedPrewarmThreadStart(", 1
            )
            original_picker = original_for_diff(picker_diff)
            central.write_text(original_central, encoding="utf-8")
            picker.write_text(original_picker, encoding="utf-8")
            with self.assertRaises(patch.PatchError):
                patch.apply_supported_patch_variant(central, picker)
            self.assertEqual(central.read_text(encoding="utf-8"), original_central)
            self.assertEqual(picker.read_text(encoding="utf-8"), original_picker)

    def test_26928_check_discovers_and_patches_separate_app_server_bundle(self) -> None:
        name, central_diff, picker_diff = patch.PATCH_VARIANTS[0]
        self.assertEqual(name, WINDOWS_26928_LAYOUT_NAME)
        with tempfile.TemporaryDirectory() as temporary:
            app = Path(temporary, "installed", "app")
            resources = app / "resources"
            resources.mkdir(parents=True)
            (resources / "app.asar").write_bytes(synthetic_asar({"files": {}}))

            def fake_run(command: list[str], **_kwargs: object) -> None:
                if "extract" not in command:
                    return
                extracted = Path(command[-1])
                web_assets = extracted / "webview" / "assets"
                main_assets = extracted / ".vite" / "build"
                web_assets.mkdir(parents=True)
                main_assets.mkdir(parents=True)
                (web_assets / "app-shared.js").write_text(
                    original_for_diff(central_diff) + "\nasync sendConfigReadRequest(\n",
                    encoding="utf-8",
                )
                (web_assets / "app-primary.js").write_text(
                    original_for_diff(picker_diff)
                    + "\ncomposer.intelligenceDropdown.tooltip\nmodelOptionsDisabled\n",
                    encoding="utf-8",
                )
                (web_assets / "unrelated.js").write_text("unrelated", encoding="utf-8")
                (main_assets / "application-network-startup.js").write_text(
                    APP_SERVER_ENV_MAPPINGS_ANCHOR_26928, encoding="utf-8"
                )
                (main_assets / "unrelated.js").write_text("unrelated", encoding="utf-8")

            original_override = patch.apply_process_model_catalog_override_26928
            overridden_sources: list[str] = []

            def record_override(source: str) -> str:
                result = original_override(source)
                overridden_sources.append(result)
                return result

            with mock_patch.object(patch.sys, "platform", "win32"), \
                 mock_patch.object(patch.shutil, "which", return_value="npx"), \
                 mock_patch.object(patch, "integrity_targets", return_value={}), \
                 mock_patch.object(patch, "contains_marker", return_value=False), \
                 mock_patch.object(patch, "run", side_effect=fake_run), \
                 mock_patch.object(
                     patch,
                     "apply_process_model_catalog_override_26928",
                     side_effect=record_override,
                 ) as override:
                patch.patch_app(
                    app,
                    Path(temporary, "unused-config.json"),
                    Path(temporary, "backups"),
                    overwrite_config=False,
                    check_only=True,
                )
            override.assert_called_once()
            self.assertIn(APP_SERVER_ENV_MAPPINGS_ANCHOR_26928, override.call_args.args[0])
            self.assertIn("CODEX_CUSTOM_PROVIDER_MODEL_CATALOG", overridden_sources[0])
            self.assertIn("model_catalog_json", overridden_sources[0])

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
            (source / "ChatGPT.exe").write_bytes(b"fixture executable")
            (output / "original.txt").write_text("keep me", encoding="utf-8")
            (output / "codex-provider-patch.json").write_text("{}", encoding="utf-8")
            patched.write_bytes(original_bytes + patch.PATCH_MARKER)
            original_rename = Path.rename

            def fail_stage_rename(path: Path, target: Path) -> Path:
                if path.name.startswith(".portable.stage-"):
                    raise OSError("simulated publish failure")
                return original_rename(path, target)

            with mock_patch.object(patch, "find_target_app_processes", return_value=[]), \
                 mock_patch.object(patch, "source_codex_cli_version", return_value="fixture-cli"), \
                 mock_patch.object(Path, "rename", fail_stage_rename):
                with self.assertRaisesRegex(OSError, "simulated publish failure"):
                    patch.install_portable(
                        source, output, backup_dir, patched, {}, WINDOWS_26928_LAYOUT_NAME
                    )

            self.assertEqual((output / "original.txt").read_text(encoding="utf-8"), "keep me")
            self.assertEqual((source / "resources" / "app.asar").read_bytes(), original_bytes)
            self.assertFalse(patched.exists())
            self.assertFalse(any(base.glob(".portable.stage-*")))

    def test_portable_copy_skips_only_replaced_top_level_asar(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            source = base / "installed"
            resources = source / "resources"
            unpacked = resources / "app.asar.unpacked"
            nested = resources / "nested"
            output = base / "portable"
            patched = base / "patched.asar"
            unpacked.mkdir(parents=True)
            nested.mkdir()
            original_asar = synthetic_asar({"files": {"original.js": {"size": 1}}})
            patched_asar = (
                synthetic_asar({"files": {"patched.js": {"size": 1}}}) + patch.PATCH_MARKER
            )
            (resources / "app.asar").write_bytes(original_asar)
            (unpacked / "native.node").write_bytes(b"preserve unpacked payload")
            (nested / "app.asar").write_bytes(b"preserve nested archive")
            (source / "ChatGPT.exe").write_bytes(b"fixture executable")
            patched.write_bytes(patched_asar)

            original_copytree = patch.shutil.copytree
            inspected_ignore = False

            def inspect_copytree(src: Path, dst: Path, *args: object, **kwargs: object) -> Path:
                nonlocal inspected_ignore
                ignore = kwargs.get("ignore")
                if Path(src) == source:
                    self.assertIsNotNone(ignore)
                    self.assertEqual(
                        ignore(str(resources), ["app.asar", "app.asar.unpacked", "nested"]),
                        {"app.asar"},
                    )
                    self.assertEqual(ignore(str(nested), ["app.asar"]), set())
                    inspected_ignore = True
                return original_copytree(src, dst, *args, **kwargs)

            with mock_patch.object(patch, "find_target_app_processes", return_value=[]), \
                 mock_patch.object(patch, "source_codex_cli_version", return_value="fixture-cli"), \
                 mock_patch.object(patch.shutil, "copytree", side_effect=inspect_copytree):
                patch.install_portable(
                    source,
                    output,
                    base / "backups",
                    patched,
                    {},
                    WINDOWS_26928_LAYOUT_NAME,
                )

            self.assertTrue(inspected_ignore)
            self.assertEqual((output / "resources" / "app.asar").read_bytes(), patched_asar)
            self.assertFalse(patched.exists())
            self.assertEqual((resources / "app.asar").read_bytes(), original_asar)
            self.assertEqual(
                (output / "resources" / "app.asar.unpacked" / "native.node").read_bytes(),
                b"preserve unpacked payload",
            )
            self.assertEqual(
                (output / "resources" / "nested" / "app.asar").read_bytes(),
                b"preserve nested archive",
            )

            cross_volume_patched = base / "cross-volume.asar"
            cross_volume_output = base / "cross-volume-portable"
            cross_volume_patched.write_bytes(patched_asar)
            original_stat = Path.stat

            def different_volume_stat(path: Path, *args: object, **kwargs: object):
                result = original_stat(path, *args, **kwargs)
                if path == cross_volume_patched:
                    values = list(result)
                    values[2] = result.st_dev + 1
                    return type(result)(values)
                return result

            original_copy2 = patch.shutil.copy2
            with mock_patch.object(patch, "find_target_app_processes", return_value=[]), \
                 mock_patch.object(patch, "source_codex_cli_version", return_value="fixture-cli"), \
                 mock_patch.object(Path, "stat", different_volume_stat), \
                 mock_patch.object(patch.shutil, "copy2", wraps=original_copy2) as copy2:
                patch.install_portable(
                    source,
                    cross_volume_output,
                    base / "cross-volume-backups",
                    cross_volume_patched,
                    {},
                    WINDOWS_26928_LAYOUT_NAME,
                )

            self.assertTrue(cross_volume_patched.exists())
            self.assertEqual(
                (cross_volume_output / "resources" / "app.asar").read_bytes(), patched_asar
            )
            self.assertTrue(any(call.args[0] == cross_volume_patched for call in copy2.call_args_list))

    def test_same_volume_payload_move_does_not_hide_replace_failures(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            source = base / "installed"
            (source / "resources").mkdir(parents=True)
            (source / "resources" / "app.asar").write_bytes(synthetic_asar({"files": {}}))
            (source / "ChatGPT.exe").write_bytes(b"fixture executable")
            patched = base / "patched.asar"
            patched.write_bytes(synthetic_asar({"files": {}}) + patch.PATCH_MARKER)
            original_replace = Path.replace

            def reject_payload_move(path: Path, target: Path) -> Path:
                if path == patched:
                    raise PermissionError("simulated same-volume move failure")
                return original_replace(path, target)

            original_copy2 = patch.shutil.copy2
            with mock_patch.object(patch, "find_target_app_processes", return_value=[]), \
                 mock_patch.object(Path, "replace", reject_payload_move), \
                 mock_patch.object(patch.shutil, "copy2", wraps=original_copy2) as copy2:
                with self.assertRaisesRegex(PermissionError, "same-volume move failure"):
                    patch.install_portable(
                        source,
                        base / "portable",
                        base / "backups",
                        patched,
                        {},
                        WINDOWS_26928_LAYOUT_NAME,
                    )

            self.assertTrue(patched.exists())
            self.assertFalse(copy2.called)
            self.assertFalse((base / "portable").exists())


if __name__ == "__main__":
    unittest.main()
