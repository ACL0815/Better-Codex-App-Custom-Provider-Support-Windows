"""Exact source edits for Windows Codex 26.930.3930.0.

The local routing, prewarm and picker behavior is inherited from 26.928;
every bundler rename below is checked before exact source hunks are applied.
"""
from __future__ import annotations

from patch_windows_26928 import build_windows_26928_variant, MODEL_CATALOG_ENV

WINDOWS_26930_LAYOUT_NAME = "Windows Codex 26.930.3930.0 Power Picker"
APP_SERVER_ENV_MAPPINGS_ANCHOR = (
    "Es=[{configKey:`chatgpt_base_url`,envVar:`CODEX_APP_SERVER_CHATGPT_BASE_URL`},"
    "{configKey:`openai_base_url`,envVar:`CODEX_APP_SERVER_OPENAI_BASE_URL`}]"
)


def _replace(source: str, old: str, new: str, expected: int = 1) -> str:
    count = source.count(old)
    if count != expected:
        raise RuntimeError(f"26.930 patch anchor changed: {old!r} ({count} matches)")
    return source.replace(old, new)


def apply_process_model_catalog_override_26930(source: str) -> str:
    return _replace(source, APP_SERVER_ENV_MAPPINGS_ANCHOR,
        APP_SERVER_ENV_MAPPINGS_ANCHOR[:-1] +
        ",{configKey:`model_catalog_json`,envVar:" + f"`{MODEL_CATALOG_ENV}`" + "}]")


def build_windows_26930_variant(central_base: str, picker_base: str) -> tuple[str, str, str]:
    _, central, picker = build_windows_26928_variant(central_base, picker_base)
    for old, new, expected in (
        ("await IW(", "await uJ(", 2),
        ("function _un(e)", "function Psn(e)", 2),
        ("let t = $St(e);", "let t = TSt(e);", 2),
        ("var vun, yun, bun, xun, Sun, Cun, wun, Tun, Eun, Dun, Oun, kun, Aun;",
         "var Fsn, Isn, Lsn, Rsn, zsn, Bsn, Vsn, Hsn, Usn, Wsn, Gsn, Ksn, qsn;", 2),
        ("!uN(this.hostId)", "!eP(this.hostId)", 2),
        ("r = oun(`thread/start`", "r = Tsn(`thread/start`", 2),
    ):
        central = _replace(central, old, new, expected)
    for old, new, expected in (
        ("await Qr(", "await Pc(", 2),
        ("_W.", "cW.", 13),
        ("bd.", "Pf.", 5),
        ("function X0e(e)", "function K2e(e)", 2),
        ("Z0e.c", "q2e.c", 2),
        ("t[56] !== pe || t[57] !== be || t[58] !== xe", "t[56] !== he || t[57] !== Se || t[58] !== Ce", 2),
        ("Se = { beforeModels: pe, defaultOption: be, options: xe }", "we = { beforeModels: he, defaultOption: Se, options: Ce }", 1),
        ("Se = {\n", "we = {\n", 1),
        ("{}), pe]", "{}), he]", 1),
        ("defaultOption: be,", "defaultOption: Se,", 1),
        ("options: xe,", "options: Ce,", 1),
        ("var Z0e, _W;", "var q2e, cW;", 1),
        ("var Z0e, _W, CodexProviderPatchReact;", "var q2e, cW, CodexProviderPatchReact;", 1),
        ("function vW()", "function lW()", 2),
        ("return (vW = e(() =>", "return (lW = e(() =>", 2),
        ("Z0e = Z()", "q2e = Q()", 2),
        ("CodexProviderPatchReact = ig()", "CodexProviderPatchReact = _h()", 1),
    ):
        picker = _replace(picker, old, new, expected)
    return WINDOWS_26930_LAYOUT_NAME, central, picker
