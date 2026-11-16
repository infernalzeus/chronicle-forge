import test from 'node:test';
import assert from 'node:assert/strict';
import {researchTopic, draftNarration, safeUrl} from '../bundle/workflow.mjs';

const sources = [{id: 'S1', title: 'History', url: 'https://example.org/history', content: 'Netflix was founded in 1997.'}];
const complete = text => ({stopReason: 'endTurn', content: {text}});
const valid = JSON.stringify({sentences: [{text: 'Netflix was founded in 1997.', source_ids: ['S1']}]});

test('invalid and executable URLs are excluded', () => {
  assert.equal(safeUrl('javascript:alert(1)'), null);
  assert.equal(safeUrl('not a URL'), null);
});
test('empty source selection makes no LLM calls', async () => {
  await assert.rejects(draftNarration({}, 'Netflix', 60, []), /Select at least/);
});
test('unreadable sources stop research', async () => {
  const anna = {web: {search: async () => ({results: [{url: 'https://example.org'}]}),
    fetch: async () => ({pages: [{url: 'https://example.org', ok: false, error: 'TIMEOUT'}]})}};
  await assert.rejects(researchTopic(anna, 'Netflix'), /No readable/);
});
test('partial fetch failure retains usable source and truncation flag', async () => {
  const anna = {web: {search: async () => ({results: [{url: 'https://example.org'}]}),
    fetch: async () => ({pages: [{url: 'https://example.org', ok: false},
      {url: 'https://example.org/history', title: 'History', ok: true, content: 'Evidence', truncated: true}]})}};
  const result = await researchTopic(anna, ' Netflix ');
  assert.deepEqual(result, {topic: 'Netflix', sources: [{id:'S1', title:'History', url:'https://example.org/history', content:'Evidence', truncated:true}]});
});
test('unknown citations are rejected before audit', async () => {
  const anna = {llm: {complete: async () => complete(valid.replace('S1', 'S99'))}};
  await assert.rejects(draftNarration(anna, 'Netflix', 60, sources), /unknown source/);
});
test('truncated model output is rejected', async () => {
  const anna = {llm: {complete: async () => ({...complete(valid), stopReason:'maxTokens'})}};
  await assert.rejects(draftNarration(anna, 'Netflix', 60, sources), /did not finish normally/);
});
test('malformed JSON is rejected', async () => {
  await assert.rejects(draftNarration({llm:{complete:async()=>complete('{')}}, 'Netflix', 60, sources), /Narration rejected/);
});
test('complete JSON in a Markdown code fence is accepted', async () => {
  let calls = 0;
  const anna = {llm: {complete: async () => complete(calls++ === 0 ? '```json\n' + valid + '\n```' : 'Audit')}};
  assert.equal((await draftNarration(anna, 'Netflix', 60, sources)).narration, 'Netflix was founded in 1997.');
});
test('incomplete code fence remains rejected', async () => {
  const anna = {llm: {complete: async () => complete('```json\n' + valid)}};
  await assert.rejects(draftNarration(anna, 'Netflix', 60, sources), /Narration rejected/);
});
test('valid draft preserves evidence and requires human review', async () => {
  let calls = 0;
  const anna = {llm: {complete: async () => complete(calls++ === 0 ? valid : 'No issues detected in these excerpts.')}};
  const result = await draftNarration(anna, 'Netflix', 60, sources);
  assert.equal(calls, 2);
  assert.equal(result.review_status, 'human_review_required');
  assert.deepEqual(result.sources, sources);
  assert.equal(result.narration, 'Netflix was founded in 1997.');
});
test('failed audit cannot produce a ready export', async () => {
  let calls = 0;
  const anna = {llm: {complete: async () => {if (calls++) throw new Error('APP_QUOTA_EXCEEDED'); return complete(valid);}}};
  await assert.rejects(draftNarration(anna, 'Netflix', 60, sources), /APP_QUOTA_EXCEEDED/);
});
test('five-second test uses small completion budgets', async () => {
  const requests=[];
  const anna={llm:{complete:async args=>{requests.push(args);return complete(requests.length===1?valid:'No issues detected in these excerpts.');}}};
  await draftNarration(anna,'Netflix',5,sources);
  assert.deepEqual(requests.map(x=>x.maxTokens),[256,384]);
});
test('low-cost research makes only one source request',async()=>{
  const requests=[];const anna={web:{search:async args=>{requests.push(args);return {results:[{url:'https://example.org'},{url:'https://example.net'}]};},fetch:async args=>{requests.push(args);return {pages:[{ok:true,url:'https://example.org',content:'Evidence'}]};}}};
  await researchTopic(anna,'Test',1);
  assert.equal(requests[0].max_results,1);assert.equal(requests[1].urls.length,1);
});
