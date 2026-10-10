// Run with: node tests/gui_diagnostics_check.cjs
const fs = require('fs');
const vm = require('vm');
const assert = require('assert');
const elements = new Map();
const el = id => {
  if (!elements.has(id)) elements.set(id, {disabled:false, hidden:true, textContent:'', style:{}});
  return elements.get(id);
};
let calls = 0, release;
const errors = [];
const bridge = {
  pick_pptx: () => { calls++; return new Promise(resolve => release = resolve); },
  load_deck: async () => { throw new Error('load failure'); },
  report_ui_error: async message => errors.push(message),
  convert: async () => { throw new Error('conversion failure'); }
};
const context = vm.createContext({
  document:{getElementById:el}, window:{pywebview:{api:bridge},addEventListener(){}},
  alert(){}, console, setTimeout, clearTimeout
});
vm.runInContext(fs.readFileSync('src/pptx2web/gui/assets/app.js','utf8'),context);
(async () => {
  const first = vm.runInContext('pickPptx()',context);
  await vm.runInContext('pickPptx()',context);
  assert.equal(calls,1);
  release(null); await first;
  assert.equal(el('pick-pptx').disabled,false);
  bridge.pick_pptx = async () => {throw new Error('dialog failure');};
  await vm.runInContext('pickPptx()',context);
  assert.equal(el('pick-pptx').disabled,false);
  await vm.runInContext('loadDeck("test.pptx")',context);
  assert.equal(el('preview-loading').hidden,true);
  await vm.runInContext('convert()',context);
  assert.equal(el('convert-btn').disabled,false);
  assert.equal(el('progress-wrap').hidden,true);
  assert(errors.includes('dialog failure') && errors.includes('load failure') && errors.includes('conversion failure'));
  bridge.convert = async () => ({ok:false, error:'busy'});
  await vm.runInContext('convert()',context);
  assert.equal(el('pick-pptx').disabled,false);
  bridge.convert = async () => ({started:true});
  await vm.runInContext('convert()',context);
  assert.equal(el('pick-pptx').disabled,true);
  assert.equal(el('convert-btn').disabled,true);
  vm.runInContext('window.guiEvent("error", {message:"test failure"})',context);
  assert.equal(el('pick-pptx').disabled,false);
  assert.equal(el('convert-btn').disabled,false);
  await vm.runInContext('convert()',context);
  vm.runInContext('window.guiEvent("done", {outDir:"out", slideCount:20, imageBytes:100, warnings:[]})',context);
  assert.equal(el('pick-pptx').disabled,false);
  assert.equal(el('convert-btn').disabled,false);
  bridge.read_diagnostics = async () => ({ok:true, session:'test-session', text:'<script>literal</script>', truncated:true});
  await vm.runInContext('refreshDiagnostics()',context);
  assert.equal(el('diagnostics-content').value,'<script>literal</script>');
  assert(el('diagnostics-status').textContent.includes('256 KB'));
  bridge.read_diagnostics = async () => {throw new Error('read failure');};
  await vm.runInContext('refreshDiagnostics()',context);
  assert.equal(el('refresh-diagnostics').disabled,false);
  assert(el('diagnostics-status').textContent.includes('No se pudieron leer'));
  console.log('JS: duplicate clicks, cancellation, errors and UI restoration passed');
})().catch(error => {console.error(error);process.exitCode=1;});
