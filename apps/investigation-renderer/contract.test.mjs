import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import {localAsset, validateProps} from './contract.mjs';

const publicDir = fs.mkdtempSync(path.join(os.tmpdir(), 'investigation-contract-'));
fs.writeFileSync(path.join(publicDir, 'evidence.png'), 'test');
const props = () => ({title: 'Sample', durationInFrames: 60, scenes: [{id: 's1', startFrame: 0,
  durationInFrames: 60, kind: 'evidence', media: 'evidence.png'}], captions: [{start: 0, end: 30, text: 'First'}]});
test('accepts the complete data-only contract and normalizes points', () => {
  const input = props(); input.scenes[0].points = ['claim'];
  assert.deepEqual(validateProps(input, publicDir).scenes[0].points, [{title: 'claim', text: ''}]);
});
test('rejects missing files, absolute paths, traversal and URL media', () => {
  for (const media of ['missing.png', '../evidence.png', '/evidence.png', 'https://host/a.png', 'C:/evidence.png', 'a\\b.png']) {
    assert.throws(() => localAsset(media, publicDir));
  }
});
test('rejects scene gaps and out-of-bounds durations', () => {
  const input = props(); input.scenes[0].startFrame = 1;
  assert.throws(() => validateProps(input, publicDir), /continuous/);
  input.scenes[0].startFrame = 0; input.scenes[0].durationInFrames = 59;
  assert.throws(() => validateProps(input, publicDir), /coverage/);
});
test('rejects overlapping captions and unsupported diagram types', () => {
  const input = props(); input.captions.push({start: 29, end: 50, text: 'Overlap'});
  assert.throws(() => validateProps(input, publicDir), /Captions/);
  input.captions.pop(); input.scenes[0].kind = 'diagram';
  assert.throws(() => validateProps(input, publicDir), /explicit points/);
});
test('accepts source text evidence and text-only mechanism explanation', () => {
  const input = props(); delete input.scenes[0].media;
  input.scenes[0].text = 'A verbatim excerpt';
  assert.equal(validateProps(input, publicDir).scenes[0].media, null);
  input.scenes[0].kind = 'diagram';
  assert.equal(validateProps(input, publicDir).scenes[0].text, 'A verbatim excerpt');
});
test('matches the saved manuscript text, badge and date limits without truncation', () => {
  const input = props();
  input.scenes[0].text = '证'.repeat(1200);
  input.scenes[0].badge = '标'.repeat(80);
  input.scenes[0].sourceDate = '日'.repeat(100);
  const scene = validateProps(input, publicDir).scenes[0];
  assert.equal(scene.text.length, 1200); assert.equal(scene.badge.length, 80); assert.equal(scene.sourceDate.length, 100);
  input.scenes[0].text += '过'; assert.throws(() => validateProps(input, publicDir), /1200/);
});
test('rejects empty content instead of generating a blank evidence or mechanism scene', () => {
  const input = props(); delete input.scenes[0].media;
  assert.throws(() => validateProps(input, publicDir), /verbatim text/);
  input.scenes[0].kind = 'diagram'; input.scenes[0].points = [' '];
  assert.throws(() => validateProps(input, publicDir), /cannot be empty/);
});
test('normalizes caption whitespace and rejects empty cues', () => {
  const input = props(); input.captions[0].text = ' one\n two ';
  assert.equal(validateProps(input, publicDir).captions[0].text, 'one two');
  input.captions[0].text = ' \n ';
  assert.throws(() => validateProps(input, publicDir), /cannot be empty/);
});
test('splits only the first point separator and preserves the supplied explanation', () => {
  const input = props(); input.scenes[0].kind = 'diagram';
  input.scenes[0].points = ['来源｜找回原文｜保留原始语境', '日期 | 查看发生时间', '核实'];
  const points = validateProps(input, publicDir).scenes[0].points;
  assert.deepEqual(points, [{title: '来源', text: '找回原文｜保留原始语境'},
    {title: '日期', text: '查看发生时间'}, {title: '核实', text: ''}]);
});
test('accepts all four diagram layouts and defaults to flow', () => {
  const input = props(); input.scenes[0].kind = 'diagram'; input.scenes[0].points = ['First', 'Second'];
  assert.equal(validateProps(input, publicDir).scenes[0].diagramLayout, 'flow');
  for (const layout of ['flow', 'compare', 'timeline', 'checklist']) {
    input.scenes[0].diagramLayout = layout;
    assert.equal(validateProps(input, publicDir).scenes[0].diagramLayout, layout);
  }
  input.scenes[0].diagramLayout = 'pie';
  assert.throws(() => validateProps(input, publicDir), /diagramLayout/);
});
test('keeps the prototype diagramStyle compatible while preferring explicit diagramLayout', () => {
  const input = props(); input.scenes[0].points = ['Step']; input.scenes[0].diagramStyle = 'list';
  assert.equal(validateProps(input, publicDir).scenes[0].diagramLayout, 'checklist');
  input.scenes[0].diagramLayout = 'timeline';
  assert.equal(validateProps(input, publicDir).scenes[0].diagramLayout, 'timeline');
});
