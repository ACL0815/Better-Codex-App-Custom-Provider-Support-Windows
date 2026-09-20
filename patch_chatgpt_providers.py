#!/usr/bin/env python3
"""Build a portable Windows Codex app with the custom provider picker.

The patch is intentionally version-sensitive: it only edits JavaScript bundles
whose expected source hunks match exactly. App updates that change those bundles
cause a clean failure before the installed app is modified.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import ctypes
from ctypes import wintypes
import re
import shlex
import shutil
import struct
import subprocess
import sys
import tempfile
import textwrap
import time
from typing import Any, NoReturn

from patch_windows_26915 import build_windows_26915_variant


PATCH_MARKER = b"__codexDesktopModelProvidersPatchV3"
LEGACY_PATCH_MARKER = b"__codexDesktopModelProvidersPatchV2"
ASAR_PACKAGE = "@electron/asar@3.2.10"
PRETTIER_PACKAGE = "prettier@3.6.2"

DEFAULT_PROVIDER_CONFIG: dict[str, Any] = {
    "version": 1,
    "default_provider": "openai",
    "providers": [
        {
            "id": "openai",
            "label": "ChatGPT / OpenAI",
            "description": (
                "Built-in provider; uses your signed-in ChatGPT account"
            ),
        },
        {
            "id": "openrouter",
            "label": "OpenRouter",
            "description": (
                "Custom provider; uses [model_providers.openrouter] from config.toml"
            ),
        },
    ],
    "model_providers": {
        "moonshotai/kimi-k3": "openrouter",
        "x-ai/grok-4.5": "openrouter",
        "anthropic/claude-fable-5": "openrouter",
    },
}


CENTRAL_DIFF = r"""@@ -4631,6 +4631,146 @@
   if (`data` in e) return e;
   let t = oe(e);
   return t == null ? e : { ...e, data: t };
+}
+function codexProviderRoutingFallback() {
+  return {
+    version: 1,
+    defaultProvider: `openai`,
+    providers: [
+      {
+        id: `openai`,
+        label: `ChatGPT / OpenAI`,
+        description: `Uses your signed-in ChatGPT account`,
+      },
+      {
+        id: `openrouter`,
+        label: `OpenRouter`,
+        description: `Uses the OpenRouter provider from config.toml`,
+      },
+    ],
+    modelProviders: {
+      "moonshotai/kimi-k3": `openrouter`,
+      "x-ai/grok-4.5": `openrouter`,
+      "anthropic/claude-fable-5": `openrouter`,
+    },
+  };
+}
+function codexNormalizeProviderRoutingConfig(e) {
+  if (e == null || typeof e !== `object` || Array.isArray(e))
+    throw Error(`Expected a JSON object`);
+  if (e.version !== 1) throw Error(`Unsupported version`);
+  if (!Array.isArray(e.providers) || e.providers.length === 0)
+    throw Error(`providers must be a non-empty array`);
+  let t = [],
+    n = new Set();
+  for (let r of e.providers) {
+    if (r == null || typeof r !== `object` || Array.isArray(r))
+      throw Error(`Every provider must be an object`);
+    let e = typeof r.id === `string` ? r.id.trim() : ``;
+    if (e.length === 0 || n.has(e))
+      throw Error(`Provider ids must be unique non-empty strings`);
+    n.add(e);
+    let i = typeof r.label === `string` ? r.label.trim() : ``;
+    t.push({
+      id: e,
+      label: i.length > 0 ? i : e,
+      description:
+        typeof r.description === `string` ? r.description.trim() : ``,
+    });
+  }
+  let r =
+    typeof e.default_provider === `string` ? e.default_provider.trim() : ``;
+  if (!n.has(r))
+    throw Error(`default_provider must reference a configured provider`);
+  let i = {};
+  if (
+    e.model_providers == null ||
+    typeof e.model_providers !== `object` ||
+    Array.isArray(e.model_providers)
+  )
+    throw Error(`model_providers must be an object`);
+  for (let [t, r] of Object.entries(e.model_providers)) {
+    let e = t.trim();
+    if (e.length === 0 || typeof r !== `string` || !n.has(r))
+      throw Error(`Every model mapping must reference a configured provider`);
+    i[e] = r;
+  }
+  return {
+    version: 1,
+    defaultProvider: r,
+    providers: t,
+    modelProviders: i,
+  };
+}
+function codexProviderRoutingState() {
+  return (window.__codexDesktopModelProvidersPatchV3 ??= {
+    config: codexProviderRoutingFallback(),
+    configPath: null,
+    error: null,
+    loaded: !1,
+    promise: null,
+  });
+}
+async function codexLoadProviderRoutingConfig(e = !1) {
+  let t = codexProviderRoutingState();
+  if (!e && t.loaded) return t.config;
+  if (t.promise != null) return t.promise;
+  return (
+    (t.promise = (async () => {
+      try {
+        let { codexHome: e } = await Xe(`codex-home`, {
+            params: { hostId: `local` },
+          }),
+          n = e.includes(`\\`) && !e.includes(`/`) ? `\\` : `/`,
+          r = `${e.replace(/[\\/]+$/u, ``)}${n}desktop-model-providers.json`,
+          { contents: i } = await Xe(`read-file`, {
+            params: { hostId: `local`, path: r },
+          }),
+          a = codexNormalizeProviderRoutingConfig(JSON.parse(i));
+        return (
+          (t.config = a),
+          (t.configPath = r),
+          (t.error = null),
+          (t.loaded = !0),
+          a
+        );
+      } catch (e) {
+        return (
+          (t.config = codexProviderRoutingFallback()),
+          (t.error = e instanceof Error ? e.message : String(e)),
+          (t.loaded = !0),
+          t.config
+        );
+      } finally {
+        t.promise = null;
+      }
+    })()),
+    t.promise
+  );
+}
+function codexCustomProviderChoice(e) {
+  try {
+    let t = window.localStorage.getItem(`codex.customProviderSelection.v1`);
+    return t === `auto` || e.providers.some((e) => e.id === t) ? t : `auto`;
+  } catch {
+    return `auto`;
+  }
+}
+async function codexProviderForThreadStart(e) {
+  let t = await codexLoadProviderRoutingConfig(!0),
+    n = codexCustomProviderChoice(t);
+  return n === `auto` ? (t.modelProviders[e?.model] ?? t.defaultProvider) : n;
+}
+async function codexPatchAppServerParams(e, t) {
+  if (e === `thread/list`) {
+    let e = t != null && typeof t === `object` ? t : {};
+    return e.modelProviders == null ? { ...e, modelProviders: [] } : e;
+  }
+  if (e === `thread/start` && t != null && typeof t === `object`)
+    return t.modelProvider == null
+      ? { ...t, modelProvider: await codexProviderForThreadStart(t) }
+      : t;
+  return t;
 }
 var jf,
   Mf,
@@ -4800,6 +4940,7 @@
             throw Error(
               `AppServerRequestClient is missing a message dispatcher`,
             );
+          t = await codexPatchAppServerParams(e, t);
           return e === `config/read`
             ? this.sendConfigReadRequest(t, n)
             : this.enqueueRequest(e, t, n);
@@ -4809,6 +4950,7 @@
             throw Error(
               `AppServerRequestClient is missing a message dispatcher`,
             );
+          e = await codexPatchAppServerParams(`thread/start`, e);
           return this.enqueueRequest(
             `thread/start`,
             e,
"""


PICKER_DIFF = r"""@@ -10162,6 +10162,204 @@
       };
 }
 var jO = e(() => {});
+function codexPickerProviderRoutingFallback() {
+  return {
+    version: 1,
+    defaultProvider: `openai`,
+    providers: [
+      {
+        id: `openai`,
+        label: `ChatGPT / OpenAI`,
+        description: `Uses your signed-in ChatGPT account`,
+      },
+      {
+        id: `openrouter`,
+        label: `OpenRouter`,
+        description: `Uses the OpenRouter provider from config.toml`,
+      },
+    ],
+    modelProviders: {
+      "moonshotai/kimi-k3": `openrouter`,
+      "x-ai/grok-4.5": `openrouter`,
+      "anthropic/claude-fable-5": `openrouter`,
+    },
+  };
+}
+function codexPickerNormalizeProviderRoutingConfig(e) {
+  if (e == null || typeof e !== `object` || Array.isArray(e))
+    throw Error(`Expected a JSON object`);
+  if (e.version !== 1) throw Error(`Unsupported version`);
+  if (!Array.isArray(e.providers) || e.providers.length === 0)
+    throw Error(`providers must be a non-empty array`);
+  let t = [],
+    n = new Set();
+  for (let r of e.providers) {
+    if (r == null || typeof r !== `object` || Array.isArray(r))
+      throw Error(`Every provider must be an object`);
+    let e = typeof r.id === `string` ? r.id.trim() : ``;
+    if (e.length === 0 || n.has(e))
+      throw Error(`Provider ids must be unique non-empty strings`);
+    n.add(e);
+    let i = typeof r.label === `string` ? r.label.trim() : ``;
+    t.push({
+      id: e,
+      label: i.length > 0 ? i : e,
+      description:
+        typeof r.description === `string` ? r.description.trim() : ``,
+    });
+  }
+  let r =
+    typeof e.default_provider === `string` ? e.default_provider.trim() : ``;
+  if (!n.has(r))
+    throw Error(`default_provider must reference a configured provider`);
+  let i = {};
+  if (
+    e.model_providers == null ||
+    typeof e.model_providers !== `object` ||
+    Array.isArray(e.model_providers)
+  )
+    throw Error(`model_providers must be an object`);
+  for (let [t, r] of Object.entries(e.model_providers)) {
+    let e = t.trim();
+    if (e.length === 0 || typeof r !== `string` || !n.has(r))
+      throw Error(`Every model mapping must reference a configured provider`);
+    i[e] = r;
+  }
+  return {
+    version: 1,
+    defaultProvider: r,
+    providers: t,
+    modelProviders: i,
+  };
+}
+function codexPickerProviderRoutingState() {
+  return (window.__codexDesktopModelProvidersPatchV3 ??= {
+    config: codexPickerProviderRoutingFallback(),
+    configPath: null,
+    error: null,
+    loaded: !1,
+    promise: null,
+  });
+}
+async function codexPickerLoadProviderRoutingConfig(e = !1) {
+  let t = codexPickerProviderRoutingState();
+  if (!e && t.loaded) return t.config;
+  if (t.promise != null) return t.promise;
+  return (
+    (t.promise = (async () => {
+      try {
+        let { codexHome: e } = await ye(`codex-home`, {
+            params: { hostId: `local` },
+          }),
+          n = e.includes(`\\`) && !e.includes(`/`) ? `\\` : `/`,
+          r = `${e.replace(/[\\/]+$/u, ``)}${n}desktop-model-providers.json`;
+        t.configPath = r;
+        let { contents: i } = await ye(`read-file`, {
+            params: { hostId: `local`, path: r },
+          }),
+          a = codexPickerNormalizeProviderRoutingConfig(JSON.parse(i));
+        return ((t.config = a), (t.error = null), (t.loaded = !0), a);
+      } catch (e) {
+        return (
+          (t.config = codexPickerProviderRoutingFallback()),
+          (t.error = e instanceof Error ? e.message : String(e)),
+          (t.loaded = !0),
+          t.config
+        );
+      } finally {
+        t.promise = null;
+      }
+    })()),
+    t.promise
+  );
+}
+function codexReadCustomProviderChoice(e) {
+  try {
+    let t = window.localStorage.getItem(`codex.customProviderSelection.v1`);
+    return t === `auto` || e.providers.some((e) => e.id === t) ? t : `auto`;
+  } catch {
+    return `auto`;
+  }
+}
+function codexWriteCustomProviderChoice(e) {
+  try {
+    window.localStorage.setItem(`codex.customProviderSelection.v1`, e);
+  } catch {}
+}
+function CodexCustomProviderPickerSection() {
+  let r = codexPickerProviderRoutingState(),
+    [e, t] = CodexProviderPatchReact.useState(r.config),
+    [n, i] = CodexProviderPatchReact.useState(r.error),
+    [a, o] = CodexProviderPatchReact.useState(() =>
+      codexReadCustomProviderChoice(r.config),
+    );
+  CodexProviderPatchReact.useEffect(() => {
+    let e = !0;
+    return (
+      codexPickerLoadProviderRoutingConfig(!0).then((n) => {
+        e &&
+          (t(n),
+          i(codexPickerProviderRoutingState().error),
+          o((e) =>
+            e === `auto` || n.providers.some((t) => t.id === e) ? e : `auto`,
+          ));
+      }),
+      () => {
+        e = !1;
+      }
+    );
+  }, []);
+  let s = (e) => (t) => {
+      (t?.preventDefault(), codexWriteCustomProviderChoice(e), o(e));
+    },
+    c =
+      e.providers.find((t) => t.id === e.defaultProvider)?.label ??
+      e.defaultProvider,
+    l = e.providers.map((e) =>
+      (0, FO.jsx)(
+        zy.Item,
+        {
+          RightIcon: a === e.id ? ct : void 0,
+          SubText:
+            e.description.length === 0
+              ? null
+              : (0, FO.jsx)(`span`, {
+                  className: `text-token-description-foreground`,
+                  children: e.description,
+                }),
+          onSelect: s(e.id),
+          children: e.label,
+        },
+        e.id,
+      ),
+    );
+  return (0, FO.jsxs)(FO.Fragment, {
+    children: [
+      (0, FO.jsx)(zy.Title, { children: `Provider for new tasks` }),
+      n == null
+        ? null
+        : (0, FO.jsx)(zy.Item, {
+            disabled: !0,
+            SubText: (0, FO.jsx)(`span`, {
+              className: `text-token-description-foreground`,
+              children: n,
+            }),
+            children: `Provider config error — using fallback`,
+          }),
+      (0, FO.jsx)(zy.Item, {
+        RightIcon: a === `auto` ? ct : void 0,
+        SubText: (0, FO.jsx)(`span`, {
+          className: `text-token-description-foreground`,
+          children: `Uses the mapped provider for each model; ${c} when unmapped`,
+        }),
+        onSelect: s(`auto`),
+        children: `Automatic`,
+      }),
+      l,
+      (0, FO.jsx)(zy.Separator, {}),
+    ],
+  });
+}
 function MO(e) {
   let t = (0, PO.c)(169),
     {
@@ -10312,6 +10510,7 @@
       ? (s = t[48])
       : ((s = (0, FO.jsxs)(FO.Fragment, {
           children: [
+            (0, FO.jsx)(CodexCustomProviderPickerSection, {}),
             a,
             (0, FO.jsx)(`div`, {
               className: `vertical-scroll-fade-mask flex max-h-[250px] flex-col overflow-y-auto`,
@@ -10984,8 +11183,10 @@
 }
 var PO,
   FO,
+  CodexProviderPatchReact,
   IO = e(() => {
     ((PO = w()),
+      (CodexProviderPatchReact = t(m(), 1)),
       T(),
       Q(),
       Pg(),
"""


# ChatGPT 26.721 moved both targets into app-initial, renamed the minified
# bindings, and introduced the Power Picker. Keep a separate exact-hunk variant
# so unsupported future builds still fail before the installed app is touched.
def derive_versioned_diff(base: str, replacements: tuple[tuple[str, str, int], ...]) -> str:
    """Derive an exact-hunk build variant while verifying every fragile rename.

    Electron's bundler changes short identifiers between releases even when the
    surrounding behavior is unchanged. Expected occurrence counts deliberately
    turn an accidental partial replacement into an installer-development error.
    """
    derived = base
    for old, new, expected_count in replacements:
        actual_count = derived.count(old)
        if actual_count != expected_count:
            message = f"Versioned patch replacement count changed for {old!r}: expected {expected_count}, found {actual_count}"
            raise RuntimeError(message)
        derived = derived.replace(old, new)
    return derived


CENTRAL_RENAMES_26721 = (
    ("   let t = oe(e);", "   let t = abe(e);", 1),
    ("await Xe(`codex-home`", "await tp(`codex-home`", 1),
    ("await Xe(`read-file`", "await tp(`read-file`", 1),
    (" var jf,\n   Mf,", " var s9t,\n   c9t,", 1),
    (
        """@@ -4809,6 +4950,7 @@
             throw Error(
               `AppServerRequestClient is missing a message dispatcher`,
             );
+          e = await codexPatchAppServerParams(`thread/start`, e);
           return this.enqueueRequest(
             `thread/start`,
             e,
""",
        """@@ -137758,6 +137899,7 @@
             throw Error(
               `AppServerRequestClient is missing a message dispatcher`,
             );
+          e = await codexPatchAppServerParams(`thread/start`, e);
           let n = t?.priority ?? `critical`,
             r = Q7t(`thread/start`, t?.source),
             i =
""",
        1,
    ),
)
CENTRAL_DIFF_26721 = derive_versioned_diff(CENTRAL_DIFF, CENTRAL_RENAMES_26721)


PICKER_DIFF_26721 = r"""@@ -520849,7 +520849,7 @@
 }
 function Scs(e) {
-  let t = (0, wcs.c)(12),
+  let t = (0, wcs.c)(13),
     { submenu: n } = e,
     r = n.ariaLabel,
     i = n.contentClassName,
@@ -520871,10 +520871,15 @@
     t[7] !== n.label ||
     t[8] !== n.value ||
     t[9] !== o ||
-    t[10] !== l
+    t[10] !== l ||
+    t[11] !== n.extras
       ? ((u = (0, QX.jsx)(Kos, {
           ariaLabel: r,
           contentClassName: i,
           disabled: a,
           flyoutHeader: o,
           label: s,
           value: c,
-          children: l,
+          children:
+            n.extras == null
+              ? l
+              : (0, QX.jsxs)(QX.Fragment, { children: [n.extras, l] }),
         })),
         (t[4] = n.ariaLabel),
         (t[5] = n.contentClassName),
@@ -520887,8 +520892,9 @@
         (t[8] = n.value),
         (t[9] = o),
         (t[10] = l),
-        (t[11] = u))
-      : (u = t[11]),
+        (t[11] = n.extras),
+        (t[12] = u))
+      : (u = t[12]),
     u
   );
 }
@@ -549520,6 +549525,202 @@
       (xMs = Aa(Q, (e, { get: t }) =>
         bMs({
           conversationId: e,
           resumeState: t(PD, e) ?? void 0,
           turnCount: t(LD, e),
         }),
       )));
   });
+function codexPickerProviderRoutingFallback() {
+  return {
+    version: 1,
+    defaultProvider: `openai`,
+    providers: [
+      {
+        id: `openai`,
+        label: `ChatGPT / OpenAI`,
+        description: `Uses your signed-in ChatGPT account`,
+      },
+      {
+        id: `openrouter`,
+        label: `OpenRouter`,
+        description: `Uses the OpenRouter provider from config.toml`,
+      },
+    ],
+    modelProviders: {
+      "moonshotai/kimi-k3": `openrouter`,
+      "x-ai/grok-4.5": `openrouter`,
+      "anthropic/claude-fable-5": `openrouter`,
+    },
+  };
+}
+function codexPickerNormalizeProviderRoutingConfig(e) {
+  if (e == null || typeof e !== `object` || Array.isArray(e))
+    throw Error(`Expected a JSON object`);
+  if (e.version !== 1) throw Error(`Unsupported version`);
+  if (!Array.isArray(e.providers) || e.providers.length === 0)
+    throw Error(`providers must be a non-empty array`);
+  let t = [],
+    n = new Set();
+  for (let r of e.providers) {
+    if (r == null || typeof r !== `object` || Array.isArray(r))
+      throw Error(`Every provider must be an object`);
+    let e = typeof r.id === `string` ? r.id.trim() : ``;
+    if (e.length === 0 || n.has(e))
+      throw Error(`Provider ids must be unique non-empty strings`);
+    n.add(e);
+    let i = typeof r.label === `string` ? r.label.trim() : ``;
+    t.push({
+      id: e,
+      label: i.length > 0 ? i : e,
+      description:
+        typeof r.description === `string` ? r.description.trim() : ``,
+    });
+  }
+  let r =
+    typeof e.default_provider === `string` ? e.default_provider.trim() : ``;
+  if (!n.has(r))
+    throw Error(`default_provider must reference a configured provider`);
+  let i = {};
+  if (
+    e.model_providers == null ||
+    typeof e.model_providers !== `object` ||
+    Array.isArray(e.model_providers)
+  )
+    throw Error(`model_providers must be an object`);
+  for (let [t, r] of Object.entries(e.model_providers)) {
+    let e = t.trim();
+    if (e.length === 0 || typeof r !== `string` || !n.has(r))
+      throw Error(`Every model mapping must reference a configured provider`);
+    i[e] = r;
+  }
+  return {
+    version: 1,
+    defaultProvider: r,
+    providers: t,
+    modelProviders: i,
+  };
+}
+function codexPickerProviderRoutingState() {
+  return (window.__codexDesktopModelProvidersPatchV3 ??= {
+    config: codexPickerProviderRoutingFallback(),
+    configPath: null,
+    error: null,
+    loaded: !1,
+    promise: null,
+  });
+}
+async function codexPickerLoadProviderRoutingConfig(e = !1) {
+  let t = codexPickerProviderRoutingState();
+  if (!e && t.loaded) return t.config;
+  if (t.promise != null) return t.promise;
+  return (
+    (t.promise = (async () => {
+      try {
+        let { codexHome: e } = await tp(`codex-home`, {
+            params: { hostId: `local` },
+          }),
+          n = e.includes(`\\`) && !e.includes(`/`) ? `\\` : `/`,
+          r = `${e.replace(/[\\/]+$/u, ``)}${n}desktop-model-providers.json`;
+        t.configPath = r;
+        let { contents: i } = await tp(`read-file`, {
+            params: { hostId: `local`, path: r },
+          }),
+          a = codexPickerNormalizeProviderRoutingConfig(JSON.parse(i));
+        return ((t.config = a), (t.error = null), (t.loaded = !0), a);
+      } catch (e) {
+        return (
+          (t.config = codexPickerProviderRoutingFallback()),
+          (t.error = e instanceof Error ? e.message : String(e)),
+          (t.loaded = !0),
+          t.config
+        );
+      } finally {
+        t.promise = null;
+      }
+    })()),
+    t.promise
+  );
+}
+function codexReadCustomProviderChoice(e) {
+  try {
+    let t = window.localStorage.getItem(`codex.customProviderSelection.v1`);
+    return t === `auto` || e.providers.some((e) => e.id === t) ? t : `auto`;
+  } catch {
+    return `auto`;
+  }
+}
+function codexWriteCustomProviderChoice(e) {
+  try {
+    window.localStorage.setItem(`codex.customProviderSelection.v1`, e);
+  } catch {}
+}
+function CodexCustomProviderPickerSection() {
+  let r = codexPickerProviderRoutingState(),
+    [e, t] = CodexProviderPatchReact.useState(r.config),
+    [n, i] = CodexProviderPatchReact.useState(r.error),
+    [a, o] = CodexProviderPatchReact.useState(() =>
+      codexReadCustomProviderChoice(r.config),
+    );
+  CodexProviderPatchReact.useEffect(() => {
+    let e = !0;
+    return (
+      codexPickerLoadProviderRoutingConfig(!0).then((n) => {
+        e &&
+          (t(n),
+          i(codexPickerProviderRoutingState().error),
+          o((e) =>
+            e === `auto` || n.providers.some((t) => t.id === e) ? e : `auto`,
+          ));
+      }),
+      () => {
+        e = !1;
+      }
+    );
+  }, []);
+  let s = (e) => (t) => {
+      (t?.preventDefault(), codexWriteCustomProviderChoice(e), o(e));
+      void Rf(`clear-prewarmed-threads-for-host`, { hostId: `local` }).catch(
+        () => {},
+      );
+    },
+    c =
+      e.providers.find((t) => t.id === e.defaultProvider)?.label ??
+      e.defaultProvider,
+    l = e.providers.map((e) =>
+      (0, wQ.jsx)(
+        yz.Item,
+        {
+          RightIcon: a === e.id ? Ym : void 0,
+          SubText:
+            e.description.length === 0
+              ? null
+              : (0, wQ.jsx)(`span`, {
+                  className: `text-token-description-foreground`,
+                  children: e.description,
+                }),
+          onSelect: s(e.id),
+          children: e.label,
+        },
+        e.id,
+      ),
+    );
+  return (0, wQ.jsxs)(wQ.Fragment, {
+    children: [
+      (0, wQ.jsx)(yz.Title, { children: `Provider for new tasks` }),
+      n == null
+        ? null
+        : (0, wQ.jsx)(yz.Item, {
+            disabled: !0,
+            SubText: (0, wQ.jsx)(`span`, {
+              className: `text-token-description-foreground`,
+              children: n,
+            }),
+            children: `Provider config error — using fallback`,
+          }),
+      (0, wQ.jsx)(yz.Item, {
+        RightIcon: a === `auto` ? Ym : void 0,
+        SubText: (0, wQ.jsx)(`span`, {
+          className: `text-token-description-foreground`,
+          children: `Uses the mapped provider for each model; ${c} when unmapped`,
+        }),
+        onSelect: s(`auto`),
+        children: `Automatic`,
+      }),
+      l,
+      (0, wQ.jsx)(yz.Separator, {}),
+    ],
+  });
+}
 function CMs(e) {
   let t = (0, TMs.c)(164),
@@ -549693,6 +549895,7 @@
           value: s,
         },
         model: {
+          extras: (0, wQ.jsx)(CodexCustomProviderPickerSection, {}),
           ariaLabel: U.formatMessage(
             {
               id: `composer.intelligenceDropdown.model.rowAriaLabel`,
@@ -549782,6 +549985,7 @@
       : ((g = (0, wQ.jsxs)(wQ.Fragment, {
           children: [
+            (0, wQ.jsx)(CodexCustomProviderPickerSection, {}),
             m,
             (0, wQ.jsx)(`div`, {
               className: `vertical-scroll-fade-mask flex max-h-[250px] flex-col overflow-y-auto`,
@@ -550438,11 +550642,13 @@
 }
 var TMs,
   wQ,
+  CodexProviderPatchReact,
   EMs = e(() => {
     ((TMs = c()),
+      (CodexProviderPatchReact = r(o(), 1)),
       pd(),
       ad(),
       gls(),
"""


# Build 6067 preserves the 26.721 behavior and menu structure, but the bundler
# renamed the surrounding symbols. Derive this layout from the verified 26.721
# patch so the shared routing and picker implementation cannot drift.
CENTRAL_RENAMES_26727 = (
    ("   let t = abe(e);", "   let t = rSe(e);", 1),
    ("await tp(`codex-home`", "await rp(`codex-home`", 1),
    ("await tp(`read-file`", "await rp(`read-file`", 1),
    (" var s9t,\n   c9t,", " var xdn,\n   Sdn,", 1),
    (
        "            r = Q7t(`thread/start`, t?.source),",
        "            r = fdn(`thread/start`, t?.source),",
        1,
    ),
)
CENTRAL_DIFF_26727 = derive_versioned_diff(CENTRAL_DIFF_26721, CENTRAL_RENAMES_26727)


PICKER_RENAMES_26727 = (
    ("function Scs(e) {", "function Mws(e) {", 1),
    ("wcs.c", "Pws.c", 2),
    ("QX", "JY", 3),
    ("Kos", "nCs", 1),
    ("xMs", "XJs", 1),
    ("Aa", "Ca", 1),
    ("bMs", "YJs", 1),
    ("PD", "aD", 1),
    ("LD", "lD", 1),
    ("await tp(`codex-home`", "await rp(`codex-home`", 1),
    ("await tp(`read-file`", "await rp(`read-file`", 1),
    (
        "void Rf(`clear-prewarmed-threads-for-host`",
        "void rp(`clear-prewarmed-threads-for-host`",
        1,
    ),
    ("wQ", "CZ", 16),
    ("yz", "_z", 5),
    ("Ym", "ch", 2),
    ("function CMs(e) {", "function QJs(e) {", 1),
    ("TMs", "eYs", 3),
    ("  EMs = e(() => {", "  tYs = n(() => {", 1),
    ("     ((eYs = c()),", "     ((eYs = l()),", 1),
    (
        "(CodexProviderPatchReact = r(o(), 1))",
        "(CodexProviderPatchReact = r(s(), 1))",
        1,
    ),
    (
        "       pd(),\n       ad(),\n       gls(),",
        "       ld(),\n       td(),\n       ETs(),",
        1,
    ),
)
PICKER_DIFF_26727 = derive_versioned_diff(PICKER_DIFF_26721, PICKER_RENAMES_26727)


CENTRAL_DIFF_V2_TO_V3 = r"""@@ -137601,7 +137601,7 @@
   };
 }
 function codexProviderRoutingState() {
-  return (window.__codexDesktopModelProvidersPatchV2 ??= {
+  return (window.__codexDesktopModelProvidersPatchV3 ??= {
     config: codexProviderRoutingFallback(),
     configPath: null,
     error: null,
"""


PICKER_DIFF_26721_V2_TO_V3 = r"""@@ -520849,7 +520849,7 @@
 }
 function Scs(e) {
-  let t = (0, wcs.c)(12),
+  let t = (0, wcs.c)(13),
     { submenu: n } = e,
     r = n.ariaLabel,
     i = n.contentClassName,
@@ -520871,10 +520871,15 @@
     t[7] !== n.label ||
     t[8] !== n.value ||
     t[9] !== o ||
-    t[10] !== l
+    t[10] !== l ||
+    t[11] !== n.extras
       ? ((u = (0, QX.jsx)(Kos, {
           ariaLabel: r,
           contentClassName: i,
           disabled: a,
           flyoutHeader: o,
           label: s,
           value: c,
-          children: l,
+          children:
+            n.extras == null
+              ? l
+              : (0, QX.jsxs)(QX.Fragment, { children: [n.extras, l] }),
         })),
         (t[4] = n.ariaLabel),
         (t[5] = n.contentClassName),
@@ -520887,8 +520892,9 @@
         (t[8] = n.value),
         (t[9] = o),
         (t[10] = l),
-        (t[11] = u))
-      : (u = t[11]),
+        (t[11] = n.extras),
+        (t[12] = u))
+      : (u = t[12]),
     u
   );
 }
@@ -549630,7 +549636,7 @@
   };
 }
 function codexPickerProviderRoutingState() {
-  return (window.__codexDesktopModelProvidersPatchV2 ??= {
+  return (window.__codexDesktopModelProvidersPatchV3 ??= {
     config: codexPickerProviderRoutingFallback(),
     configPath: null,
     error: null,
@@ -549886,7 +549892,6 @@
         (t[39] = f))
       : (f = t[39]),
       (G = {
-        extras: (0, wQ.jsx)(CodexCustomProviderPickerSection, {}),
         effort: {
           ariaLabel: U.formatMessage(
             {
@@ -549921,6 +549926,7 @@
           value: s,
         },
         model: {
+          extras: (0, wQ.jsx)(CodexCustomProviderPickerSection, {}),
           ariaLabel: U.formatMessage(
             {
               id: `composer.intelligenceDropdown.model.rowAriaLabel`,
@@ -550013,6 +550019,7 @@
       ? (g = t[52])
       : ((g = (0, wQ.jsxs)(wQ.Fragment, {
           children: [
+            (0, wQ.jsx)(CodexCustomProviderPickerSection, {}),
             m,
             (0, wQ.jsx)(`div`, {
               className: `vertical-scroll-fade-mask flex max-h-[250px] flex-col overflow-y-auto`,
@@ -550148,7 +550155,6 @@
       : (k = t[77]),
       (K = (0, wQ.jsxs)(wQ.Fragment, {
         children: [
-          (0, wQ.jsx)(CodexCustomProviderPickerSection, {}),
           (0, wQ.jsx)(Kos, {
             ariaLabel: U.formatMessage(
               {
@@ -550354,7 +550360,6 @@
   t[90] !== le || t[91] !== pe || t[92] !== me
     ? ((he = (0, wQ.jsxs)(wQ.Fragment, {
         children: [
-          (0, wQ.jsx)(CodexCustomProviderPickerSection, {}),
           le,
           pe,
           me,
"""


PICKER_DIFF_LEGACY_V2_TO_V3 = r"""@@ -10242,7 +10242,7 @@
   };
 }
 function codexPickerProviderRoutingState() {
-  return (window.__codexDesktopModelProvidersPatchV2 ??= {
+  return (window.__codexDesktopModelProvidersPatchV3 ??= {
     config: codexPickerProviderRoutingFallback(),
     configPath: null,
     error: null,
@@ -10360,6 +10360,6 @@
 function MO(e) {
   let t = (0, PO.c)(169),
     {
"""


PATCH_VARIANTS: tuple[tuple[str, str, str], ...] = (
    build_windows_26915_variant(CENTRAL_DIFF, PICKER_DIFF),
    ("ChatGPT 26.727 Power Picker", CENTRAL_DIFF_26727, PICKER_DIFF_26727),
    ("ChatGPT 26.721 Power Picker", CENTRAL_DIFF_26721, PICKER_DIFF_26721),
    ("ChatGPT 26.715 legacy picker", CENTRAL_DIFF, PICKER_DIFF),
    (
        "ChatGPT 26.721 provider-picker V2 upgrade",
        CENTRAL_DIFF_V2_TO_V3,
        PICKER_DIFF_26721_V2_TO_V3,
    ),
    (
        "ChatGPT 26.715 provider-picker V2 marker upgrade",
        CENTRAL_DIFF_V2_TO_V3,
        PICKER_DIFF_LEGACY_V2_TO_V3,
    ),
)


class PatchError(RuntimeError):
    """A safe, expected patch failure."""


def colors_enabled(stream: Any = sys.stdout) -> bool:
    return "NO_COLOR" not in os.environ and (
        getattr(stream, "isatty", lambda: False)()
        or os.environ.get("FORCE_COLOR") not in (None, "", "0")
    )


def color(text: object, *codes: str, stream: Any = sys.stdout) -> str:
    rendered = str(text)
    if not colors_enabled(stream) or not codes:
        return rendered
    return f"\033[{';'.join(codes)}m{rendered}\033[0m"


def terminal_width() -> int:
    return max(64, min(shutil.get_terminal_size((96, 24)).columns, 110))


def terminal_status(
    label: str,
    message: object,
    code: str,
    *,
    detail: object | None = None,
    stream: Any = sys.stdout,
) -> None:
    badge_width = 10
    plain_badge = f"[{label}]"
    badge = color(plain_badge, "1", code, stream=stream)
    badge_padding = " " * max(1, badge_width - len(plain_badge))
    available = max(30, terminal_width() - badge_width)
    lines = textwrap.wrap(
        str(message),
        width=available,
        break_long_words=False,
        break_on_hyphens=False,
    ) or [""]
    print(f"{badge}{badge_padding}{lines[0]}", file=stream)
    for line in lines[1:]:
        print(f"{'':{badge_width}}{line}", file=stream)
    if detail is not None:
        detail_lines = textwrap.wrap(
            str(detail),
            width=max(30, terminal_width() - badge_width - 2),
            break_long_words=False,
            break_on_hyphens=False,
        ) or [""]
        for index, line in enumerate(detail_lines):
            marker = "> " if index == 0 else "  "
            print(
                f"{'':{badge_width}}{color(marker + line, '2', stream=stream)}",
                file=stream,
            )
    stream.flush()


def terminal_heading(title: str, code: str = "36") -> None:
    visible_title = f" {title.upper()} "
    rule_length = max(2, terminal_width() - len(visible_title))
    print()
    print(
        color(f"{visible_title}{'=' * rule_length}", "1", code),
    )
    sys.stdout.flush()


def terminal_panel(
    title: str,
    message: object,
    code: str,
    *,
    stream: Any = sys.stderr,
) -> None:
    width = terminal_width()
    title_text = f" {title.upper()} "
    top = f"+-{title_text}{'-' * max(1, width - len(title_text) - 2)}"
    bottom = f"+{'-' * (width - 1)}"
    print(file=stream)
    print(color(top, "1", code, stream=stream), file=stream)
    paragraphs = str(message).splitlines() or [""]
    for paragraph in paragraphs:
        wrapped = textwrap.wrap(
            paragraph,
            width=max(30, width - 4),
            break_long_words=False,
            break_on_hyphens=False,
        ) or [""]
        for line in wrapped:
            border = color("|", code, stream=stream)
            print(f"{border} {color(line, '1', stream=stream)}", file=stream)
    print(color(bottom, "1", code, stream=stream), file=stream)
    print(file=stream)
    stream.flush()


def terminal_bullet(label: str, description: str) -> None:
    bullet = color("*", "1", "36")
    key = color(label, "1", "33")
    prefix_width = 29
    prefix = f"  {bullet} {key}"
    padding = " " * max(1, prefix_width - 4 - len(label))
    available = max(30, terminal_width() - prefix_width)
    lines = textwrap.wrap(
        description,
        width=available,
        break_long_words=False,
        break_on_hyphens=False,
    ) or [""]
    print(f"{prefix}{padding}{lines[0]}")
    for line in lines[1:]:
        print(f"{'':{prefix_width}}{line}")
    sys.stdout.flush()


def print_completion_summary(
    config: Path,
    *,
    backup: Path | None = None,
    output: Path | None = None,
    modified_pe: bool = False,
    already_installed: bool = False,
    upgraded: bool = False,
) -> None:
    codex_config = config.parent / "config.toml"
    if already_installed:
        terminal_status(
            "READY",
            "Patch already installed; no app files were changed.",
            "32",
        )
    else:
        terminal_status(
            "SUCCESS",
            "Patch upgraded successfully."
            if upgraded
            else "Patch installed successfully.",
            "32",
        )

    terminal_heading("Custom provider config")
    terminal_status("CONFIG", "Edit this file to customize provider routing:", "36", detail=config)
    terminal_bullet("providers", "Providers displayed in the app menu.")
    terminal_bullet(
        "model_providers",
        "Maps each exact model slug to the provider used by Automatic mode.",
    )
    terminal_bullet(
        "default_provider",
        "Provider used by Automatic mode when a model has no explicit mapping.",
    )
    terminal_status(
        "LINK",
        "Custom provider IDs must match a [model_providers.<id>] section.",
        "35",
        detail=codex_config,
    )
    terminal_status(
        "KEYS",
        "Do not put API keys in the provider-routing JSON file.",
        "33",
        detail="Keep credentials in the provider authentication configuration or environment.",
    )

    terminal_heading("After editing", "35")
    terminal_status(
        "RELOAD",
        "Save valid JSON, then close and reopen the model/provider menu.",
        "35",
        detail="No repatching or app restart is needed.",
    )

    if backup is not None:
        terminal_heading("Recovery", "34")
        terminal_status("BACKUP", "Previous portable copy backup:", "34", detail=backup)

    if output is not None:
        terminal_status("OUTPUT", "Portable app directory:", "36", detail=output)
        if (output / "resources" / "owl-app.ini").exists():
            terminal_status(
                "IDENTITY",
                "This Owl build requires a Windows package identity before it can start.",
                "33",
                detail="Run Register-Codex-PatchIdentity.ps1 for this copy; see README.md.",
            )

    terminal_heading("Important", "33")
    terminal_status(
        "NOTICE",
        ("The updated EXE has an invalid publisher signature. Windows may warn or block it. "
         if modified_pe else "The copied app is modified and may trigger Windows warnings. ")
        + "An MSIX app copied out of WindowsApps may require package identity at runtime.",
        "33",
    )
    print()


def fail(message: str, exit_code: int = 1) -> NoReturn:
    terminal_panel("Error", message, "31", stream=sys.stderr)
    raise SystemExit(exit_code)


def run(
    command: list[str],
    *,
    cwd: Path | None = None,
    label: str | None = None,
) -> subprocess.CompletedProcess[str]:
    terminal_status(
        "STEP",
        label or f"Running {Path(command[0]).name}",
        "36",
        detail=shlex.join(command),
    )
    try:
        executable = shutil.which(command[0])
        if executable is None:
            raise PatchError(f"Command not found: {command[0]}")
        actual_command = [executable, *command[1:]]
        if command[0] == "npx":
            node = shutil.which("node")
            npx_cli = Path(executable).parent / "node_modules" / "npm" / "bin" / "npx-cli.js"
            if node is None or not npx_cli.is_file():
                raise PatchError("Node.js npm/npx installation not found in the standard layout")
            actual_command = [node, str(npx_cli), *command[1:]]
        return subprocess.run(
            actual_command,
            cwd=cwd,
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
    except subprocess.CalledProcessError as exc:
        output = exc.stdout.strip() if exc.stdout else ""
        if output:
            terminal_panel("Command output", output, "31", stream=sys.stderr)
        raise PatchError(f"Command failed with exit status {exc.returncode}") from exc


class FancyArgumentParser(argparse.ArgumentParser):
    def _print_message(self, message: str, file: Any = None) -> None:
        if not message:
            return
        stream = file or sys.stdout
        width = terminal_width()
        title = " COMMAND HELP "
        top = f"+-{title}{'-' * max(1, width - len(title) - 2)}"
        bottom = f"+{'-' * (width - 1)}"
        print(file=stream)
        print(color(top, "1", "36", stream=stream), file=stream)
        for raw_line in message.rstrip().splitlines():
            border = color("|", "36", stream=stream)
            stripped = raw_line.strip()
            if not stripped:
                print(border, file=stream)
                continue
            if raw_line.startswith("usage:"):
                label, remainder = raw_line.split(":", 1)
                rendered = (
                    color(label.upper(), "1", "35", stream=stream)
                    + color(":", "35", stream=stream)
                    + color(remainder, "1", stream=stream)
                )
            elif stripped in {"options:", "optional arguments:"}:
                rendered = color(stripped.upper(), "1", "36", stream=stream)
            elif raw_line.startswith("  -"):
                option_and_help = re.split(r"(\s{2,})", stripped, maxsplit=1)
                option = option_and_help[0]
                remainder = "".join(option_and_help[1:])
                rendered = (
                    "  "
                    + color(option, "1", "33", stream=stream)
                    + color(remainder, stream=stream)
                )
            else:
                rendered = color(raw_line, stream=stream)
            print(f"{border} {rendered}", file=stream)
        print(color(bottom, "1", "36", stream=stream), file=stream)
        print(file=stream)
        stream.flush()

    def error(self, message: str) -> NoReturn:
        terminal_panel("Argument error", message, "31", stream=sys.stderr)
        terminal_status(
            "HELP",
            "Show all installer options with:",
            "33",
            detail=f"{self.prog} --help",
            stream=sys.stderr,
        )
        self.exit(2)


def invoking_user_home() -> Path:
    return Path(os.environ["USERPROFILE"]) if os.environ.get("USERPROFILE") else Path.home()


def parse_args() -> argparse.Namespace:
    home = invoking_user_home()
    configured_codex_home = os.environ.get("CODEX_HOME")
    codex_home = (
        Path(configured_codex_home).expanduser()
        if configured_codex_home
        else home / ".codex"
    )
    parser = FancyArgumentParser(
        description=(
            "Add a dynamic provider selector and per-model provider routing to the "
            "Windows Codex/ChatGPT desktop app. The installed app is never modified."
        )
    )
    parser.add_argument(
        "--app",
        type=Path,
        default=None,
        help="Source app directory (default: discover an installed Codex/ChatGPT app)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(os.environ.get("LOCALAPPDATA", str(home / "AppData" / "Local")))
        / "Programs" / "Codex-Provider-Patch",
        help="Writable portable app directory to create",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=codex_home / "desktop-model-providers.json",
        help="Provider-routing JSON file in the effective Codex home",
    )
    parser.add_argument(
        "--backup-dir",
        type=Path,
        default=Path(os.environ.get("LOCALAPPDATA", str(home / "AppData" / "Local")))
        / "Codex Provider Patch Backups",
        help="Directory for backups of previous portable outputs",
    )
    parser.add_argument(
        "--overwrite-config",
        action="store_true",
        help="Replace the provider-routing JSON with the built-in template",
    )
    parser.add_argument("--check", action="store_true", help="Inspect source compatibility without writing files")
    parser.add_argument("--dry-run", action="store_true", help="Build and verify patch in a temporary directory without installing")
    return parser.parse_args()


def validate_provider_config(data: Any) -> None:
    if not isinstance(data, dict):
        raise PatchError("Provider config must be a JSON object")
    if data.get("version") != 1:
        raise PatchError("Provider config version must be 1")
    providers = data.get("providers")
    if not isinstance(providers, list) or not providers:
        raise PatchError("Provider config 'providers' must be a non-empty array")

    provider_ids: set[str] = set()
    for provider in providers:
        if not isinstance(provider, dict):
            raise PatchError("Every provider must be an object")
        provider_id = provider.get("id")
        if not isinstance(provider_id, str) or not provider_id.strip():
            raise PatchError("Every provider id must be a non-empty string")
        provider_id = provider_id.strip()
        if provider_id in provider_ids:
            raise PatchError(f"Duplicate provider id: {provider_id}")
        provider_ids.add(provider_id)
        label = provider.get("label")
        if not isinstance(label, str) or not label.strip():
            raise PatchError(f"Provider '{provider_id}' needs a non-empty label")
        description = provider.get("description", "")
        if not isinstance(description, str):
            raise PatchError(f"Provider '{provider_id}' description must be a string")

    default_provider = data.get("default_provider")
    if default_provider not in provider_ids:
        raise PatchError("default_provider must reference a configured provider")

    mappings = data.get("model_providers")
    if not isinstance(mappings, dict):
        raise PatchError("model_providers must be an object")
    for model, provider_id in mappings.items():
        if not isinstance(model, str) or not model.strip():
            raise PatchError("Every model mapping key must be a non-empty string")
        if provider_id not in provider_ids:
            raise PatchError(
                f"Model '{model}' references unknown provider '{provider_id}'"
            )


def atomic_write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary_path, 0o600)
        os.replace(temporary_path, path)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def ensure_provider_config(path: Path, overwrite: bool) -> str:
    if overwrite or not path.exists() or path.stat().st_size == 0:
        validate_provider_config(DEFAULT_PROVIDER_CONFIG)
        atomic_write_json(path, DEFAULT_PROVIDER_CONFIG)
        return "written"
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise PatchError(f"Cannot read valid JSON from {path}: {exc}") from exc
    validate_provider_config(data)
    return "kept"


def asar_header_hash(path: Path) -> str:
    return hashlib.sha256(asar_header_json(path)).hexdigest()


def asar_header_json(path: Path) -> bytes:
    try:
        with path.open("rb") as handle:
            size_pickle = handle.read(8)
            if len(size_pickle) != 8:
                raise PatchError("ASAR archive is too short to contain a header")
            size_payload, header_pickle_size = struct.unpack("<II", size_pickle)
            if size_payload != 4 or header_pickle_size < 8:
                raise PatchError("ASAR archive has an invalid header-size pickle")

            header_pickle = handle.read(header_pickle_size)
            if len(header_pickle) != header_pickle_size:
                raise PatchError("ASAR archive contains a truncated header")
    except OSError as exc:
        raise PatchError(f"Cannot read ASAR header from {path}: {exc}") from exc

    header_payload_size, header_string_size = struct.unpack("<II", header_pickle[:8])
    if header_payload_size > header_pickle_size - 4:
        raise PatchError("ASAR header payload size is invalid")
    header_start = 8
    header_end = header_start + header_string_size
    if header_end > len(header_pickle):
        raise PatchError("ASAR header string is truncated")

    header_json = header_pickle[header_start:header_end]
    try:
        json.loads(header_json.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PatchError("ASAR header does not contain valid UTF-8 JSON") from exc
    return header_json


def asar_unpacked_files(path: Path) -> set[str]:
    header = json.loads(asar_header_json(path))
    unpacked: set[str] = set()

    def visit(node: dict[str, Any], prefix: str = "") -> None:
        for name, child in node.get("files", {}).items():
            relative = f"{prefix}/{name}" if prefix else name
            if child.get("unpacked") is True:
                unpacked.add(relative)
            if isinstance(child.get("files"), dict):
                visit(child, relative)

    visit(header)
    return unpacked


def asar_unpack_patterns(path: Path) -> tuple[list[str], list[str]]:
    header = json.loads(asar_header_json(path))
    directories: list[str] = []
    files: list[str] = []

    def visit(node: dict[str, Any], prefix: str = "") -> None:
        for name, child in node.get("files", {}).items():
            relative = f"{prefix}/{name}" if prefix else name
            if child.get("unpacked") is True:
                (directories if isinstance(child.get("files"), dict) else files).append(relative)
            elif isinstance(child.get("files"), dict):
                visit(child, relative)

    visit(header)
    return directories, files


def asar_pack_command(source: Path, target: Path, original: Path) -> list[str]:
    directories, files = asar_unpack_patterns(original)
    command = ["npx", "--yes", ASAR_PACKAGE, "pack", str(source), str(target)]
    if directories:
        command.extend(("--unpack-dir", directories[0] if len(directories) == 1
                        else "{" + ",".join(directories) + "}"))
    if files:
        # @electron/asar's --unpack matcher tests basenames. Exact ASAR metadata
        # is verified after packing so an over-broad match is rejected safely.
        basenames = sorted({Path(file).name for file in files})
        command.extend(("--unpack", basenames[0] if len(basenames) == 1
                        else "{" + ",".join(basenames) + "}"))
    return command


def contains_marker(path: Path, marker: bytes = PATCH_MARKER) -> bool:
    overlap = len(marker) - 1
    previous = b""
    with path.open("rb") as handle:
        while chunk := handle.read(4 * 1024 * 1024):
            data = previous + chunk
            if marker in data:
                return True
            previous = data[-overlap:] if overlap else b""
    return False


def parse_pe_asar_integrity_payload(payload: bytes) -> list[dict[str, str]]:
    """Validate Electron's Windows Integrity/ElectronAsar resource."""
    try:
        entries = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PatchError("Invalid ElectronAsar PE resource JSON") from exc
    if not isinstance(entries, list):
        raise PatchError("ElectronAsar PE resource must be a JSON array")
    for entry in entries:
        if not isinstance(entry, dict) or not all(
            isinstance(entry.get(key), str) for key in ("file", "alg", "value")
        ):
            raise PatchError("ElectronAsar PE resource has an invalid entry")
        if entry["alg"].lower() != "sha256" or not re.fullmatch(r"[0-9a-fA-F]{64}", entry["value"]):
            raise PatchError("ElectronAsar PE resource has an unsupported algorithm or hash")
    return entries


def _kernel32() -> Any:
    if sys.platform != "win32":
        raise PatchError("Windows PE resources can only be inspected on Windows")
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.LoadLibraryExW.argtypes = [wintypes.LPCWSTR, wintypes.HANDLE, wintypes.DWORD]
    kernel.LoadLibraryExW.restype = wintypes.HMODULE
    kernel.FindResourceW.argtypes = [wintypes.HMODULE, wintypes.LPCWSTR, wintypes.LPCWSTR]
    kernel.FindResourceW.restype = wintypes.HRSRC
    kernel.SizeofResource.argtypes = [wintypes.HMODULE, wintypes.HRSRC]
    kernel.SizeofResource.restype = wintypes.DWORD
    kernel.LoadResource.argtypes = [wintypes.HMODULE, wintypes.HRSRC]
    kernel.LoadResource.restype = wintypes.HGLOBAL
    kernel.LockResource.argtypes = [wintypes.HGLOBAL]
    kernel.LockResource.restype = ctypes.c_void_p
    kernel.FreeLibrary.argtypes = [wintypes.HMODULE]
    kernel.EnumResourceLanguagesW.argtypes = [wintypes.HMODULE, wintypes.LPCWSTR,
                                              wintypes.LPCWSTR, ctypes.c_void_p, ctypes.c_ssize_t]
    kernel.EnumResourceLanguagesW.restype = wintypes.BOOL
    kernel.BeginUpdateResourceW.argtypes = [wintypes.LPCWSTR, wintypes.BOOL]
    kernel.BeginUpdateResourceW.restype = wintypes.HANDLE
    kernel.UpdateResourceW.argtypes = [wintypes.HANDLE, wintypes.LPCWSTR, wintypes.LPCWSTR,
                                       wintypes.WORD, ctypes.c_void_p, wintypes.DWORD]
    kernel.UpdateResourceW.restype = wintypes.BOOL
    kernel.EndUpdateResourceW.argtypes = [wintypes.HANDLE, wintypes.BOOL]
    kernel.EndUpdateResourceW.restype = wintypes.BOOL
    return kernel


def pe_asar_resource_language(path: Path) -> int | None:
    kernel = _kernel32()
    module = kernel.LoadLibraryExW(str(path), None, 0x2)
    if not module:
        raise PatchError(f"Cannot inspect PE resources in {path}: Win32 error {ctypes.get_last_error()}")
    try:
        if not kernel.FindResourceW(module, "ElectronAsar", "Integrity"):
            error = ctypes.get_last_error()
            if error in (1813, 1814):
                return None
            raise PatchError(f"Cannot find ElectronAsar resource: Win32 error {error}")
        languages: list[int] = []
        callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HMODULE,
                                           wintypes.LPCWSTR, wintypes.LPCWSTR,
                                           wintypes.WORD, ctypes.c_ssize_t)
        callback = callback_type(lambda _m, _t, _n, language, _p:
                                 (languages.append(language) or True))
        if not kernel.EnumResourceLanguagesW(module, "Integrity", "ElectronAsar", callback, 0):
            raise PatchError(f"Cannot enumerate ElectronAsar languages: Win32 error {ctypes.get_last_error()}")
        if len(languages) != 1:
            raise PatchError(f"Expected exactly one ElectronAsar resource language in {path}")
        return languages[0]
    finally:
        kernel.FreeLibrary(module)


def read_pe_asar_integrity(path: Path) -> list[dict[str, str]] | None:
    kernel = _kernel32()
    module = kernel.LoadLibraryExW(str(path), None, 0x2)  # LOAD_LIBRARY_AS_DATAFILE
    if not module:
        raise PatchError(f"Cannot inspect PE resources in {path}: Win32 error {ctypes.get_last_error()}")
    try:
        resource = kernel.FindResourceW(module, "ElectronAsar", "Integrity")
        if not resource:
            if ctypes.get_last_error() == 1813:  # ERROR_RESOURCE_TYPE_NOT_FOUND
                return None
            if ctypes.get_last_error() == 1814:  # ERROR_RESOURCE_NAME_NOT_FOUND
                return None
            raise PatchError(f"Cannot read ElectronAsar resource: Win32 error {ctypes.get_last_error()}")
        size = kernel.SizeofResource(module, resource)
        data = kernel.LoadResource(module, resource)
        pointer = kernel.LockResource(data) if data else None
        if not size or not pointer:
            raise PatchError(f"Cannot load ElectronAsar resource from {path}")
        return parse_pe_asar_integrity_payload(ctypes.string_at(pointer, size))
    finally:
        kernel.FreeLibrary(module)


def write_pe_asar_integrity(path: Path, entries: list[dict[str, str]]) -> None:
    payload = json.dumps(entries, separators=(",", ":")).encode("utf-8")
    parse_pe_asar_integrity_payload(payload)
    language = pe_asar_resource_language(path)
    if language is None:
        raise PatchError(f"No existing ElectronAsar resource in {path}")
    kernel = _kernel32()
    handle = kernel.BeginUpdateResourceW(str(path), False)
    if not handle:
        raise PatchError(f"Cannot update PE resources in {path}: Win32 error {ctypes.get_last_error()}")
    committed = False
    try:
        buffer = ctypes.create_string_buffer(payload)
        if not kernel.UpdateResourceW(handle, "Integrity", "ElectronAsar", language,
                                      ctypes.cast(buffer, ctypes.c_void_p), len(payload)):
            raise PatchError(f"Cannot write ElectronAsar resource: Win32 error {ctypes.get_last_error()}")
        if not kernel.EndUpdateResourceW(handle, False):
            raise PatchError(f"Cannot commit PE resource: Win32 error {ctypes.get_last_error()}")
        committed = True
    finally:
        if not committed:
            kernel.EndUpdateResourceW(handle, True)


def app_resources(app: Path) -> Path:
    resources = app / "resources"
    if (resources / "app.asar").is_file():
        return resources
    raise PatchError(f"No Windows app/resources/app.asar found at {app}")


def discover_app() -> Path:
    local = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local")))
    candidates = [local / "Programs" / name for name in ("Codex", "ChatGPT")]
    program_files = [Path(os.environ.get("ProgramFiles", r"C:\Program Files"))]
    if os.environ.get("ProgramFiles(x86)"):
        program_files.append(Path(os.environ["ProgramFiles(x86)"]))
    for base in program_files:
        candidates.extend(base / name for name in ("Codex", "ChatGPT"))
    # MSIX packages may be readable, but are never written by this tool.
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "Get-AppxPackage | Where-Object { $_.Name -in @('OpenAI.Codex','OpenAI.ChatGPT-Desktop') } | "
             "Select-Object Name,InstallLocation | ConvertTo-Json -Compress"],
            check=True, capture_output=True, text=True,
        )
        packages = json.loads(result.stdout or "[]")
        if isinstance(packages, dict):
            packages = [packages]
        packages.sort(key=lambda package: package.get("Name") != "OpenAI.Codex")
        candidates.extend(Path(package["InstallLocation"]) / "app"
                          for package in packages if package.get("InstallLocation"))
    except (OSError, subprocess.CalledProcessError, json.JSONDecodeError):
        pass
    for candidate in candidates:
        try:
            if (candidate / "resources" / "app.asar").is_file():
                return candidate.resolve()
        except PermissionError:
            continue
    raise PatchError("No supported Windows Codex/ChatGPT source found; pass --app PATH")


def find_target_app_processes(app: Path) -> list[tuple[int, str]]:
    """Find processes launched from an output directory; never terminate them."""
    if sys.platform != "win32":
        return []
    script = "Get-CimInstance Win32_Process | Select-Object ProcessId,ExecutablePath | ConvertTo-Json -Compress"
    try:
        result = subprocess.run(["powershell", "-NoProfile", "-Command", script],
                                check=True, capture_output=True, text=True)
        items = json.loads(result.stdout or "[]")
    except (OSError, subprocess.CalledProcessError, json.JSONDecodeError) as exc:
        raise PatchError(f"Could not inspect running Windows processes: {exc}") from exc
    if isinstance(items, dict):
        items = [items]
    prefix = str(app.resolve()).rstrip("\\/").casefold() + "\\"
    return [(int(item["ProcessId"]), item["ExecutablePath"])
            for item in items if isinstance(item, dict)
            and isinstance(item.get("ExecutablePath"), str)
            and item["ExecutablePath"].casefold().startswith(prefix)]


def unique_candidate(
    assets: Path,
    content_needles: tuple[str, ...],
    role: str,
) -> Path:
    candidates = sorted(
        path
        for path in assets.glob("*.js")
        if not path.name.endswith(".map.js")
    )
    matches = []
    for path in candidates:
        source = path.read_text(encoding="utf-8")
        if all(needle in source for needle in content_needles):
            matches.append(path)
    if len(matches) != 1:
        raise PatchError(
            f"Expected exactly one {role} JavaScript bundle containing all "
            f"required source markers, found {len(matches)} among "
            f"{len(candidates)} JavaScript bundles"
        )
    return matches[0]


def parse_hunks(unified_diff: str) -> list[list[str]]:
    lines = unified_diff.splitlines()
    hunks: list[list[str]] = []
    current: list[str] | None = None
    for line in lines:
        if line.startswith("@@ "):
            current = []
            hunks.append(current)
        elif current is not None:
            if not line or line[0] not in " +-":
                raise PatchError(f"Malformed embedded diff line: {line!r}")
            current.append(line)
    if not hunks:
        raise PatchError("Embedded patch contains no hunks")
    return hunks


def render_unified_diff(source: str, unified_diff: str, source_name: str) -> str:
    had_trailing_newline = source.endswith("\n")
    source_lines = source.splitlines()
    search_start = 0

    for hunk_number, hunk in enumerate(parse_hunks(unified_diff), start=1):
        old_lines = [line[1:] for line in hunk if line[0] in " -"]
        new_lines = [line[1:] for line in hunk if line[0] in " +"]
        matches = [
            index
            for index in range(search_start, len(source_lines) - len(old_lines) + 1)
            if source_lines[index : index + len(old_lines)] == old_lines
        ]
        if len(matches) != 1:
            raise PatchError(
                f"{source_name}: hunk {hunk_number} matched {len(matches)} times; "
                "the app build is unsupported or already modified"
            )
        index = matches[0]
        source_lines[index : index + len(old_lines)] = new_lines
        search_start = index + len(new_lines)

    return "\n".join(source_lines) + ("\n" if had_trailing_newline else "")


def apply_supported_patch_variant(central: Path, picker: Path) -> str:
    originals = {
        path: path.read_text(encoding="utf-8") for path in {central, picker}
    }
    compatible: list[tuple[str, dict[Path, str]]] = []

    for name, central_diff, picker_diff in PATCH_VARIANTS:
        rendered = originals.copy()
        try:
            rendered[central] = render_unified_diff(
                rendered[central], central_diff, central.name
            )
            rendered[picker] = render_unified_diff(
                rendered[picker], picker_diff, picker.name
            )
        except PatchError:
            continue
        compatible.append((name, rendered))

    if len(compatible) != 1:
        raise PatchError(
            "Expected exactly one supported JavaScript patch layout, found "
            f"{len(compatible)}. This app build is unsupported or already modified."
        )

    name, rendered = compatible[0]
    for path, source in rendered.items():
        path.write_text(source, encoding="utf-8")
    return name


def integrity_targets(app: Path, asar_path: Path) -> dict[Path, list[dict[str, str]]]:
    expected = asar_header_hash(asar_path)
    targets: dict[Path, list[dict[str, str]]] = {}
    for executable in app.glob("*.exe"):
        entries = read_pe_asar_integrity(executable)
        if entries is None:
            continue
        matching = [entry for entry in entries if entry["file"].replace("/", "\\").lower() == r"resources\app.asar"]
        if len(matching) != 1:
            raise PatchError(f"Expected one app.asar integrity entry in {executable}")
        if matching[0]["value"].lower() != expected:
            raise PatchError(f"ASAR header does not match PE integrity metadata in {executable}")
        targets[executable] = entries
    return targets


def ensure_safe_output(source: Path, output: Path, backup_dir: Path) -> None:
    source = source.resolve()
    output = output.resolve()
    backup_dir = backup_dir.resolve()
    if source == output or source in output.parents or output in source.parents:
        raise PatchError("--output must be separate from the installed source app")
    if backup_dir == source or source in backup_dir.parents or backup_dir in source.parents:
        raise PatchError("--backup-dir must be separate from the source app")
    if backup_dir == output or output in backup_dir.parents or backup_dir in output.parents:
        raise PatchError("--backup-dir must be separate from --output")
    if "windowsapps" in (part.casefold() for part in output.parts):
        raise PatchError("--output cannot be inside WindowsApps")


def backup_name(output: Path, backup_dir: Path) -> Path:
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    candidate = backup_dir / f"{output.name}-{stamp}"
    suffix = 1
    while candidate.exists():
        candidate = backup_dir / f"{output.name}-{stamp}-{suffix}"
        suffix += 1
    return candidate


def updated_integrity_entries(entries: list[dict[str, str]], new_hash: str) -> list[dict[str, str]]:
    updated = [entry.copy() for entry in entries]
    for entry in updated:
        if entry["file"].replace("/", "\\").lower() == r"resources\app.asar":
            entry["value"] = new_hash
    return updated


def verify_patched_pe_resources(targets: dict[Path, list[dict[str, str]]],
                                patched_asar: Path, directory: Path) -> None:
    new_hash = asar_header_hash(patched_asar)
    for executable, entries in targets.items():
        copy = directory / executable.name
        shutil.copy2(executable, copy)
        updated = updated_integrity_entries(entries, new_hash)
        write_pe_asar_integrity(copy, updated)
        if read_pe_asar_integrity(copy) != updated:
            raise PatchError(f"PE integrity update failed for {executable}")


def install_portable(source: Path, output: Path, backup_dir: Path,
                     patched_asar: Path, targets: dict[Path, list[dict[str, str]]]) -> Path | None:
    ensure_safe_output(source, output, backup_dir)
    if output.exists() and not (output / "codex-provider-patch.json").is_file():
        raise PatchError(f"Existing --output is not a copy made by this tool: {output}")
    running = find_target_app_processes(output) if output.exists() else []
    if running:
        pids = ", ".join(str(pid) for pid, _ in running)
        raise PatchError(f"Portable output is running (PIDs: {pids}); close it and retry")
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{output.name}.stage-", dir=output.parent))
    backup: Path | None = None
    staged = False
    try:
        # copytree into a sibling so no live app file is changed until validation passes
        shutil.rmtree(staging)
        shutil.copytree(source, staging, symlinks=False)
        resources = app_resources(staging)
        shutil.copy2(patched_asar, resources / "app.asar")
        patched_unpacked = patched_asar.with_name(patched_asar.name + ".unpacked")
        if patched_unpacked.exists():
            old_unpacked = resources / "app.asar.unpacked"
            if old_unpacked.exists():
                shutil.rmtree(old_unpacked)
            shutil.copytree(patched_unpacked, old_unpacked)
        for executable, entries in targets.items():
            copied = staging / executable.name
            updated = updated_integrity_entries(entries, asar_header_hash(patched_asar))
            write_pe_asar_integrity(copied, updated)
            verified = read_pe_asar_integrity(copied)
            if verified != updated:
                raise PatchError(f"PE integrity update failed for {copied}")
        if asar_header_hash(resources / "app.asar") != asar_header_hash(patched_asar):
            raise PatchError("Staged ASAR integrity verification failed")
        if not contains_marker(resources / "app.asar"):
            raise PatchError("Staged ASAR has no provider patch marker")
        (staging / "codex-provider-patch.json").write_text(
            json.dumps({"format": 1, "source": str(source),
                        "asar_header_sha256": asar_header_hash(patched_asar)}, indent=2) + "\n",
            encoding="utf-8",
        )
        if output.exists():
            backup_dir.mkdir(parents=True, exist_ok=True)
            backup = backup_name(output, backup_dir)
            output.rename(backup)
        try:
            staging.rename(output)
            staged = True
        except Exception:
            if backup is not None and backup.exists():
                backup.rename(output)
            raise
    finally:
        if not staged and staging.exists():
            shutil.rmtree(staging)
    return backup


def patch_app(app: Path, config: Path, backup_dir: Path, overwrite_config: bool,
              *, output: Path | None = None, check_only: bool = False,
              dry_run: bool = False) -> None:
    if sys.platform != "win32":
        raise PatchError("This installer only supports Windows")
    app = app.resolve()
    effective_codex_home = Path(os.environ.get("CODEX_HOME") or (invoking_user_home() / ".codex"))
    runtime_config = (effective_codex_home / "desktop-model-providers.json").resolve()
    if not check_only and not dry_run and config != runtime_config:
        terminal_status("WARNING", "The app reads provider routing from the effective Codex home. "
                        "This --config path may not be used at runtime.", "33",
                        detail=f"Runtime path: {runtime_config}")
    resources = app_resources(app)
    asar_path = resources / "app.asar"
    if shutil.which("npx") is None:
        raise PatchError("npx is required. Install Node.js and retry")
    if output is not None:
        ensure_safe_output(app, output, backup_dir)
    targets = integrity_targets(app, asar_path)
    if targets:
        terminal_status("VERIFY", "Original Windows PE ASAR integrity is valid.", "32",
                        detail=", ".join(path.name for path in targets))
    else:
        terminal_status("NOTICE", "No ElectronAsar PE resource exists in this build.", "33")
    if contains_marker(asar_path):
        raise PatchError("Source app is already patched; use a clean installed app as --app")
    is_upgrade = contains_marker(asar_path, LEGACY_PATCH_MARKER)
    with tempfile.TemporaryDirectory(prefix="codex-provider-patch-") as temporary:
        work = Path(temporary)
        extracted = work / "app"
        patched_asar = work / "app.asar"
        run(["npx", "--yes", ASAR_PACKAGE, "extract", str(asar_path), str(extracted)],
            label="Extracting application resources")
        assets = extracted / "webview" / "assets"
        if not assets.is_dir():
            raise PatchError("Extracted app has no webview/assets directory")
        central = unique_candidate(assets, ("async prewarmThreadStart(", "async sendConfigReadRequest("),
                                   "App Server client")
        picker = unique_candidate(assets, ("composer.intelligenceDropdown.tooltip", "modelOptionsDisabled"),
                                  "model picker")
        patch_targets = list(dict.fromkeys((central, picker)))
        run(["npx", "--yes", PRETTIER_PACKAGE, "--write", *(str(path) for path in patch_targets)],
            label="Preparing JavaScript bundles")
        layout = apply_supported_patch_variant(central, picker)
        terminal_status("LAYOUT", "Matched a supported application bundle.", "32", detail=layout)
        if PATCH_MARKER.decode() not in central.read_text(encoding="utf-8"):
            raise PatchError("Routing marker missing after patch")
        if "CodexCustomProviderPickerSection" not in picker.read_text(encoding="utf-8"):
            raise PatchError("Provider picker missing after patch")
        if check_only:
            terminal_status("CHECK", "Source is compatible; source, output and config were not changed.", "32")
            return
        run(["npx", "--yes", PRETTIER_PACKAGE, "--write", *(str(path) for path in patch_targets)],
            label="Validating patched JavaScript")
        run(asar_pack_command(extracted, patched_asar, asar_path),
            label="Packing patched application resources")
        if not contains_marker(patched_asar) or contains_marker(patched_asar, LEGACY_PATCH_MARKER):
            raise PatchError("Packed ASAR patch markers are invalid")
        original_unpacked = asar_unpacked_files(asar_path)
        packed_unpacked = asar_unpacked_files(patched_asar)
        if original_unpacked != packed_unpacked:
            raise PatchError(f"Packed ASAR unpacked-file layout changed ({len(original_unpacked)} original, "
                             f"{len(packed_unpacked)} patched); refusing to install")
        verify_patched_pe_resources(targets, patched_asar, work)
        if dry_run:
            terminal_status("DRY RUN", "Patch packed and verified; no app or config files were changed.", "32")
            return
        if output is None:
            raise PatchError("An output path is required for installation")
        previous_config = config.read_bytes() if config.exists() else None
        config_changed = False
        try:
            config_changed = ensure_provider_config(config, overwrite_config) == "written"
            backup = install_portable(app, output, backup_dir, patched_asar, targets)
        except Exception:
            if config_changed:
                if previous_config is None:
                    config.unlink(missing_ok=True)
                else:
                    config.write_bytes(previous_config)
            raise
    print_completion_summary(config, backup=backup, output=output,
                             upgraded=is_upgrade, modified_pe=bool(targets))


def main() -> int:
    args = parse_args()
    try:
        if args.check and args.dry_run:
            raise PatchError("Choose either --check or --dry-run")
        app = (args.app.expanduser().resolve() if args.app else discover_app())
        patch_app(app, args.config.expanduser().resolve(), args.backup_dir.expanduser().resolve(),
                  args.overwrite_config, output=args.output.expanduser().resolve(),
                  check_only=args.check, dry_run=args.dry_run)
    except (PatchError, PermissionError, OSError) as exc:
        fail(str(exc))
    except KeyboardInterrupt:
        fail("Interrupted", 130)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
