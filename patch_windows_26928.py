"""Exact source edits for Windows Codex 26.928.3736.0."""

from __future__ import annotations


WINDOWS_26928_LAYOUT_NAME = "Windows Codex 26.928.3736.0 Power Picker"
MODEL_CATALOG_ENV = "CODEX_CUSTOM_PROVIDER_MODEL_CATALOG"
APP_SERVER_ENV_MAPPINGS_ANCHOR = (
    "Ts=[{configKey:`chatgpt_base_url`,envVar:`CODEX_APP_SERVER_CHATGPT_BASE_URL`},"
    "{configKey:`openai_base_url`,envVar:`CODEX_APP_SERVER_OPENAI_BASE_URL`}]"
)


def apply_process_model_catalog_override_26928(source: str) -> str:
    """Pass an optional per-process model catalog to the 26.928 app server."""
    old = APP_SERVER_ENV_MAPPINGS_ANCHOR
    new = old[:-1] + (
        ",{configKey:`model_catalog_json`,envVar:"
        f"`{MODEL_CATALOG_ENV}`}}]"
    )
    return _replace_once(source, old, new)


def _replace_once(source: str, old: str, new: str) -> str:
    count = source.count(old)
    if count != 1:
        raise RuntimeError(f"26.928 patch anchor changed: {old!r} ({count} matches)")
    return source.replace(old, new)


def _hunk(old: str, new: str) -> str:
    old_lines = old.strip("\n").splitlines()
    new_lines = new.strip("\n").splitlines()
    return (
        f"@@ -1,{len(old_lines)} +1,{len(new_lines)} @@\n"
        + "\n".join("-" + line for line in old_lines)
        + "\n"
        + "\n".join("+" + line for line in new_lines)
        + "\n"
    )


def _first_hunk_additions(diff: str) -> str:
    first_hunk = diff.split("\n@@", 1)[0]
    return "\n".join(line[1:] for line in first_hunk.splitlines() if line.startswith("+"))


def build_windows_26928_variant(central_base: str, picker_base: str) -> tuple[str, str, str]:
    central_helpers = _first_hunk_additions(central_base)
    if not central_helpers.startswith("}\nfunction codexProviderRoutingFallback() {"):
        raise RuntimeError("Original central helper insertion changed")
    central_helpers = central_helpers[2:] + "\n}"
    central_helpers = _replace_once(central_helpers, "await Xe(`codex-home`", "await IW(`codex-home`")
    central_helpers = _replace_once(central_helpers, "await Xe(`read-file`", "await IW(`read-file`")
    central_helpers = _replace_once(
        central_helpers,
        "async function codexPatchAppServerParams(e, t) {",
        "async function codexPatchAppServerParams(e, t, hostId = `local`) {\n"
        "  if (hostId !== `local`) return t;",
    )

    prewarm_before = """          let p = Date.now(),
            m = null,
            h = null;
          try {
            (f.canUsePrewarmedThread &&"""
    prewarm_after = """          let p = Date.now(),
            m = null,
            h = null;
          let codexExpectedProvider =
            this.params.hostId === `local`
              ? await codexProviderForThreadStart({
                  model: e.collaborationMode?.settings.model ?? null,
                })
              : null;
          try {
            (f.canUsePrewarmedThread &&"""
    predicate_before = """                  f.requiresThreadReferences
                    ? (e) =>
                        this.params.getThreadReferencesSupported(Z(e.thread.id))
                    : void 0,"""
    predicate_after = """                  (e) =>
                    (codexExpectedProvider == null ||
                      e.thread.modelProvider === codexExpectedProvider) &&
                    (!f.requiresThreadReferences ||
                      this.params.getThreadReferencesSupported(Z(e.thread.id))),"""
    central_anchor = """function _un(e) {
  if (`data` in e) return e;
  let t = $St(e);
  return t == null ? e : { ...e, data: t };
}
var vun, yun, bun, xun, Sun, Cun, wun, Tun, Eun, Dun, Oun, kun, Aun;"""
    central_insert = central_anchor.replace("\nvar vun,", "\n" + central_helpers + "\nvar vun,")
    send_before = """        async sendRequest(e, t, n) {
          if (this.dispatchMessage == null)
            throw Error(
              `AppServerRequestClient is missing a message dispatcher`,
            );
          return e === `config/read`"""
    send_after = send_before.replace(
        "          return e === `config/read`",
        "          t = await codexPatchAppServerParams(e, t, this.hostId);\n"
        "          return e === `config/read`",
    )
    extension_before = """        async sendAppServerExtensionRequest(e, t, n) {
          if (this.dispatchMessage == null)
            throw Error(
              `AppServerRequestClient is missing a message dispatcher`,
            );
          if (!uN(this.hostId))
            throw Error(
              `User-message admission requires the durable Electron host`,
            );
          return this.enqueueRequest(e, t, {"""
    extension_after = extension_before.replace(
        "          return this.enqueueRequest(e, t, {",
        "          t = await codexPatchAppServerParams(e, t, this.hostId);\n"
        "          return this.enqueueRequest(e, t, {",
    )
    warm_before = """        async prewarmThreadStart(e, t) {
          if (this.dispatchMessage == null)
            throw Error(
              `AppServerRequestClient is missing a message dispatcher`,
            );
          let n = t?.priority ?? `critical`,
            r = oun(`thread/start`, t?.source),"""
    warm_after = warm_before.replace(
        "          let n = t?.priority ?? `critical`,",
        "          e = await codexPatchAppServerParams(`thread/start`, e, this.hostId);\n"
        "          let n = t?.priority ?? `critical`,",
    )
    central_diff = "".join(
        _hunk(old, new)
        for old, new in (
            (prewarm_before, prewarm_after),
            (predicate_before, predicate_after),
            (central_anchor, central_insert),
            (send_before, send_after),
            (extension_before, extension_after),
            (warm_before, warm_after),
        )
    )

    picker_helpers = _first_hunk_additions(picker_base)
    if not picker_helpers.startswith("function codexPickerProviderRoutingFallback() {"):
        raise RuntimeError("Original picker helper insertion changed")
    for old, new in (
        ("await ye(`codex-home`", "await Qr(`codex-home`"),
        ("await ye(`read-file`", "await Qr(`read-file`"),
        ("`Provider for new tasks`", "`Provider for new local tasks`"),
    ):
        picker_helpers = _replace_once(picker_helpers, old, new)
    for old, new, expected in (("FO.", "_W.", 10), ("zy.", "bd.", 5)):
        if picker_helpers.count(old) != expected:
            raise RuntimeError(f"Original picker alias changed: {old!r}")
        picker_helpers = picker_helpers.replace(old, new)
    if picker_helpers.count("RightIcon: a ===") != 2 or picker_helpers.count(" ? ct : void 0") != 2:
        raise RuntimeError("Original picker selected-icon expressions changed")
    picker_helpers = picker_helpers.replace("RightIcon: a ===", "rightText: a ===")
    picker_helpers = picker_helpers.replace(" ? ct : void 0", " ? `✓` : void 0")

    picker_anchor = """function X0e(e) {
  let t = (0, Z0e.c)(131),"""
    advanced_before = """  t[56] !== pe || t[57] !== be || t[58] !== xe
    ? ((Se = { beforeModels: pe, defaultOption: be, options: xe }),"""
    advanced_after = """  t[56] !== pe || t[57] !== be || t[58] !== xe
    ? ((Se = {
        beforeModels: (0, _W.jsxs)(_W.Fragment, {
          children: [(0, _W.jsx)(CodexCustomProviderPickerSection, {}), pe],
        }),
        defaultOption: be,
        options: xe,
      }),"""
    react_before = """var Z0e, _W;
function vW() {
  return (vW = e(() => {
    ((Z0e = Z()),"""
    react_after = """var Z0e, _W, CodexProviderPatchReact;
function vW() {
  return (vW = e(() => {
    ((Z0e = Z()),
      (CodexProviderPatchReact = ig()),"""
    picker_diff = "".join(
        _hunk(old, new)
        for old, new in (
            (picker_anchor, picker_helpers + "\n" + picker_anchor),
            (advanced_before, advanced_after),
            (react_before, react_after),
        )
    )
    return (WINDOWS_26928_LAYOUT_NAME, central_diff, picker_diff)
