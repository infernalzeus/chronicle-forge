import test from 'node:test';
import assert from 'node:assert/strict';
import {createDiagnostics} from '../bundle/diagnostics.mjs';
import {mediaIdentity} from '../bundle/project.mjs';
test('diagnostics exclude content and accept only safe numeric fields',()=>{const d=createDiagnostics();d.record('research','failed',{duration_ms:12,topic:'PRIVATE_TOPIC',prompt:'PRIVATE_PROMPT',url:'https://private.example',error_code:'PRIVATE_PROVIDER_MESSAGE'});const text=JSON.stringify(d.export());assert.ok(!text.includes('PRIVATE'));assert.equal(d.export().content_capture,false);assert.equal(d.export().automatic_transmission,false);assert.equal(d.export().events[0].error_code,'operation_failed');});
test('changing export framing never changes the paid-media identity',()=>{const options={imageModel:'image',ttsModel:'speech',style:'refined',sceneCount:3};assert.equal(mediaIdentity('A fact.',{...options,fit:'cover',motion:true}),mediaIdentity('A fact.',{...options,fit:'contain',motion:false}));});
test('changing scene count changes the paid-media plan',()=>{assert.notEqual(mediaIdentity('A fact.',{sceneCount:2}),mediaIdentity('A fact.',{sceneCount:3}));});
