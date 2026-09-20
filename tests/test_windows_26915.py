"""Execute the generated current-build routing helpers without an app account."""

import shutil
import subprocess
import unittest

import patch_chatgpt_providers as patch
from patch_windows_26915 import build_windows_26915_variant


class CurrentWindowsRoutingTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("node"), "Node.js is required for JavaScript behavior checks")
    def test_generated_routing_handles_local_and_remote_requests(self):
        _, central, _ = build_windows_26915_variant(patch.CENTRAL_DIFF, patch.PICKER_DIFF)
        additions = "\n".join(
            line[1:] for line in central.splitlines() if line.startswith("+")
        )
        start = additions.index("function codexProviderRoutingFallback() {")
        end = additions.index("\nvar xen,", start)
        helpers = additions[start:end]
        harness = r"""
const assert = require('node:assert/strict');
let choice = 'auto';
let reads = [];
let config = {
  version: 1, default_provider: 'openai',
  providers: [{id:'openai',label:'OpenAI'}, {id:'custom',label:'Custom'}],
  model_providers: {'custom/model':'custom'}
};
global.window = {localStorage: {getItem: () => choice}};
async function Wv(method, options) {
  reads.push([method,options]);
  if (method === 'codex-home') return {codexHome: 'C:\\Users\\Example\\.codex'};
  if (method === 'read-file') return {contents: JSON.stringify(config)};
  throw new Error('Unexpected bridge request');
}
""" + helpers + r"""
(async () => {
  let mapped = await codexPatchAppServerParams('thread/start', {model:'custom/model'}, 'local');
  assert.equal(mapped.modelProvider, 'custom');
  assert.equal(reads[1][1].params.path, 'C:\\Users\\Example\\.codex\\desktop-model-providers.json');
  let ordinary = await codexPatchAppServerParams('thread/start', {model:'gpt'}, 'local');
  assert.equal(ordinary.modelProvider, 'openai');
  choice = 'custom';
  assert.equal((await codexPatchAppServerParams('thread/start', {model:'gpt'}, 'local')).modelProvider, 'custom');
  let explicit = {model:'gpt', modelProvider:'already-specified'};
  assert.equal(await codexPatchAppServerParams('thread/start', explicit, 'local'), explicit);
  let remote = {model:'custom/model'};
  let count = reads.length;
  for (let host of ['durable','remote-control:test']) {
    assert.equal(await codexPatchAppServerParams('thread/start', remote, host), remote);
    assert.equal(await codexPatchAppServerParams('thread/list', remote, host), remote);
  }
  assert.equal(reads.length, count);
  assert.deepEqual(await codexPatchAppServerParams('thread/list', null, 'local'), {modelProviders:[]});
  let filtered = {modelProviders:['openai']};
  assert.equal(await codexPatchAppServerParams('thread/list', filtered, 'local'), filtered);
  let turn = {threadId:'existing',model:'custom/model'};
  assert.equal(await codexPatchAppServerParams('turn/addUserMessage', turn, 'local'), turn);
  choice = 'removed-provider';
  assert.equal((await codexPatchAppServerParams('thread/start', {model:'gpt'}, 'local')).modelProvider, 'openai');
  config.version = 99;
  assert.equal((await codexPatchAppServerParams('thread/start', {model:'gpt'}, 'local')).modelProvider, 'openai');
  assert.match(codexProviderRoutingState().error, /Unsupported version/);
})().catch(error => { console.error(error); process.exitCode = 1; });
"""
        result = subprocess.run(
            [shutil.which("node"), "-"], input=harness, text=True,
            capture_output=True, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
