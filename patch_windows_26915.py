"""Exact source edits for Windows Codex 26.915.4065.0.

Only short integration anchors are embedded here. The shared provider helpers
come from the original patch, and no complete proprietary bundle is distributed.
The installer requires every old block to match exactly once before writing.
"""

from __future__ import annotations


WINDOWS_26915_LAYOUT_NAME = "Windows Codex 26.915.4065.0 Power Picker"
MODEL_CATALOG_ENV = "CODEX_CUSTOM_PROVIDER_MODEL_CATALOG"
APP_SERVER_ENV_MAPPINGS_ANCHOR = (
    "QZ=[{configKey:`chatgpt_base_url`,envVar:`CODEX_APP_SERVER_CHATGPT_BASE_URL`},"
    "{configKey:`openai_base_url`,envVar:`CODEX_APP_SERVER_OPENAI_BASE_URL`}]"
)


def apply_process_model_catalog_override(source: str) -> str:
    """Pass an optional per-process catalog to the bundled app server."""
    old = APP_SERVER_ENV_MAPPINGS_ANCHOR
    new = old[:-1] + (
        ",{configKey:`model_catalog_json`,envVar:"
        f"`{MODEL_CATALOG_ENV}`}}]"
    )
    return _replace_once(source, old, new)


def _replace_once(source: str, old: str, new: str) -> str:
    count = source.count(old)
    if count != 1:
        raise RuntimeError(f"26.915 patch anchor changed: {old!r} ({count} matches)")
    return source.replace(old, new)


def _hunk(old: str, new: str) -> str:
    """Encode an exact replacement in the installer's unified-hunk format."""
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


def build_windows_26915_variant(central_base: str, picker_base: str) -> tuple[str, str, str]:
    central_helpers = _first_hunk_additions(central_base)
    if not central_helpers.startswith("}\nfunction codexProviderRoutingFallback() {"):
        raise RuntimeError("Original central helper insertion changed")
    central_helpers = central_helpers[2:] + "\n}"
    central_helpers = _replace_once(central_helpers, "await Xe(`codex-home`", "await Wv(`codex-home`")
    central_helpers = _replace_once(central_helpers, "await Xe(`read-file`", "await Wv(`read-file`")
    central_helpers = _replace_once(
        central_helpers,
        "async function codexPatchAppServerParams(e, t) {",
        "async function codexPatchAppServerParams(e, t, hostId = `local`) {\n"
        "  if (hostId !== `local`) return t;",
    )

    # In this build prewarming is owned by a manager RPC, not the old webview
    # clear-prewarmed-threads command. Compare the actual warmed provider with
    # the latest choice before consuming it, retaining the reference predicate.
    prewarm_before = """          let f = Date.now(),
            p = null,
            m = null;
          try {
            (d.canUsePrewarmedThread &&"""
    prewarm_after = """          let f = Date.now(),
            p = null,
            m = null;
          let codexExpectedProvider =
            this.params.hostId === `local`
              ? await codexProviderForThreadStart({
                  model: e.collaborationMode?.settings.model ?? null,
                })
              : null;
          try {
            (d.canUsePrewarmedThread &&"""
    predicate_before = """                  d.requiresThreadReferences
                    ? (e) =>
                        this.params.getThreadReferencesSupported(
                          ti(e.thread.id),
                        )
                    : void 0,"""
    predicate_after = """                  (e) =>
                    (codexExpectedProvider == null ||
                      e.thread.modelProvider === codexExpectedProvider) &&
                    (!d.requiresThreadReferences ||
                      this.params.getThreadReferencesSupported(ti(e.thread.id))),"""
    central_anchor = """function ben(e) {
  if (`data` in e) return e;
  let t = je(e);
  return t == null ? e : { ...e, data: t };
}
var xen, Sen, Cen, wen, Ten, Een, Den, Oen, ken, Aen, jen, Men, Nen;"""
    central_insert = central_anchor.replace(
        "\nvar xen,", "\n" + central_helpers + "\nvar xen,"
    )
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
          if (!Vr(this.hostId))
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
            r = len(`thread/start`, t?.source),"""
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
        ("await ye(`codex-home`", "await g_(`codex-home`"),
        ("await ye(`read-file`", "await g_(`read-file`"),
        ("`Provider for new tasks`", "`Provider for new local tasks`"),
    ):
        picker_helpers = _replace_once(picker_helpers, old, new)
    for old, new, expected in (("FO.", "r3.", 10), ("zy.", "jg.", 5), (" ? ct :", " ? Nd :", 2)):
        if picker_helpers.count(old) != expected:
            raise RuntimeError(f"Original picker alias changed: {old!r}")
        picker_helpers = picker_helpers.replace(old, new)

    picker_anchor = """function eXe(e) {
  let t = (0, tXe.c)(89),"""
    # Advanced/Power Picker already exposes beforeModels, so no changes to its
    # React compiler cache layout or private submenu implementation are needed.
    advanced_before = """      t[80] !== H || t[81] !== _e || t[82] !== ve
        ? ((ye = { beforeModels: H, defaultOption: _e, options: ve }),"""
    advanced_after = """      t[80] !== H || t[81] !== _e || t[82] !== ve
        ? ((ye = {
            beforeModels: (0, r3.jsxs)(r3.Fragment, {
              children: [(0, r3.jsx)(CodexCustomProviderPickerSection, {}), H],
            }),
            defaultOption: _e,
            options: ve,
          }),"""
    classic_before = """                    labelOnly: ee,
                    children: [
                      (0, r3.jsx)(jg.Title, {"""
    classic_after = """                    labelOnly: ee,
                    children: [
                      (0, r3.jsx)(CodexCustomProviderPickerSection, {}),
                      (0, r3.jsx)(jg.Title, {"""
    react_before = """var tXe, r3;
function i3() {
  return (i3 = e(() => {
    ((tXe = q()),"""
    react_after = """var tXe, r3, CodexProviderPatchReact;
function i3() {
  return (i3 = e(() => {
    ((tXe = q()),
      (CodexProviderPatchReact = X()),"""
    picker_diff = "".join(
        _hunk(old, new)
        for old, new in (
            (picker_anchor, picker_helpers + "\n" + picker_anchor),
            (advanced_before, advanced_after),
            (classic_before, classic_after),
            (react_before, react_after),
        )
    )
    return (WINDOWS_26915_LAYOUT_NAME, central_diff, picker_diff)
